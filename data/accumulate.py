"""
Daily data accumulation for all Polymarket crypto Up/Down markets.

Data sources:
  - HuggingFace:  market metadata (coin, timeframe, timestamps)
  - Binance API:  1-minute klines (price + volume, cached permanently)

Note: entry_price (Polymarket crowd probability) is not available historically —
Polymarket does not store CLOB price history for resolved short-lived markets.
It will be added when the live trading system is built.

Saves to: ~/.cache/polymarket-research/history.csv
Logs to:  ~/.cache/polymarket-research/accumulate.log

Usage:
    uv run data/accumulate.py
"""

import os
import time
import datetime
import pandas as pd
import numpy as np
import requests

CACHE_DIR    = os.path.join(os.path.expanduser("~"), ".cache", "polymarket-research")
HISTORY_FILE = os.path.join(CACHE_DIR, "history.csv")
LOG_FILE     = os.path.join(CACHE_DIR, "accumulate.log")
BINANCE_DIR  = os.path.join(CACHE_DIR, "binance")

HF_DATASET = "aliplayer1/polymarket-crypto-updown"

ALL_COINS      = ["SOL", "BTC", "ETH", "XRP", "DOGE", "BNB", "HYPE"]
ALL_TIMEFRAMES = ["5-minute", "15-minute", "1-hour", "4-hour"]

DURATION_SEC    = {"5-minute": 300, "15-minute": 900, "1-hour": 3600, "4-hour": 14400}
BINANCE_SYMBOL  = {
    "SOL":  "SOLUSDT",  "BTC":  "BTCUSDT",  "ETH":  "ETHUSDT",
    "XRP":  "XRPUSDT",  "DOGE": "DOGEUSDT", "BNB":  "BNBUSDT",
    "HYPE": "HYPEUSDT",  # not on Binance — skipped gracefully
}
ANALYSIS_OFFSET_MIN = 1   # 1 minute before window — freshest realistic data


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def log(msg):
    line = f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ---------------------------------------------------------------------------
# Binance klines  (price + volume, permanent local cache)
# ---------------------------------------------------------------------------

def _fetch_klines(symbol, start_ms, end_ms):
    """Fetch 1-minute klines from Binance for a time range. Returns DataFrame."""
    url  = "https://api.binance.com/api/v3/klines"
    rows = []
    t    = start_ms
    while t < end_ms:
        r = requests.get(url, params={
            "symbol": symbol, "interval": "1m",
            "startTime": t, "endTime": end_ms, "limit": 1000,
        }, timeout=15)
        if r.status_code == 400:
            break   # symbol not found on Binance
        r.raise_for_status()
        chunk = r.json()
        if not chunk:
            break
        rows.extend(chunk)
        t = chunk[-1][6] + 1        # closeTime + 1 ms
        if len(chunk) < 1000:
            break
        time.sleep(0.05)

    if not rows:
        return pd.DataFrame(columns=["ts_ms", "price", "volume"])

    df = pd.DataFrame(rows, columns=[
        "ts_ms", "open", "high", "low", "price", "volume",
        "close_ts", "qvol", "trades", "tb_base", "tb_quote", "ignore",
    ])[["ts_ms", "price", "volume"]]
    return df.astype({"ts_ms": int, "price": float, "volume": float})


def load_coin_klines(coin, start_ms, end_ms):
    """
    Return 1-minute klines for a coin in [start_ms, end_ms].
    Fetches missing ranges from Binance and caches permanently.
    """
    os.makedirs(BINANCE_DIR, exist_ok=True)
    symbol     = BINANCE_SYMBOL.get(coin.upper())
    cache_file = os.path.join(BINANCE_DIR, f"{symbol}_1m.csv")

    def _ms_fmt(ms):
        return datetime.datetime.utcfromtimestamp(ms / 1000).strftime("%Y-%m-%d")

    if os.path.exists(cache_file):
        df          = pd.read_csv(cache_file, dtype={"ts_ms": int, "price": float, "volume": float})
        cached_min  = int(df["ts_ms"].min())
        cached_max  = int(df["ts_ms"].max())
        parts       = [df]

        if start_ms < cached_min:
            log(f"    {coin}: fetching {_ms_fmt(start_ms)} -> {_ms_fmt(cached_min)} from Binance")
            older = _fetch_klines(symbol, start_ms, cached_min - 1)
            if not older.empty:
                parts.insert(0, older)

        if cached_max < end_ms - 60_000:
            log(f"    {coin}: fetching {_ms_fmt(cached_max)} -> {_ms_fmt(end_ms)} from Binance")
            newer = _fetch_klines(symbol, cached_max + 1, end_ms)
            if not newer.empty:
                parts.append(newer)

        if len(parts) > 1:
            df = pd.concat(parts).drop_duplicates("ts_ms").sort_values("ts_ms").reset_index(drop=True)
            df.to_csv(cache_file, index=False)
    else:
        log(f"    {coin}: fetching full history {_ms_fmt(start_ms)} -> {_ms_fmt(end_ms)}")
        df = _fetch_klines(symbol, start_ms, end_ms)
        if not df.empty:
            df.to_csv(cache_file, index=False)

    return df[(df["ts_ms"] >= start_ms) & (df["ts_ms"] <= end_ms)].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Feature + outcome computation
# ---------------------------------------------------------------------------

def compute_rows(coin_m, coin_p, coin):
    """Compute outcomes and features for one coin. Returns a list of dicts."""
    rows = []

    coin_p    = coin_p.sort_values("ts_ms").reset_index(drop=True)
    ts_arr    = coin_p["ts_ms"].values
    price_arr = coin_p["price"].values
    vol_arr   = coin_p["volume"].values

    coin_m = coin_m.sort_values("analysis_ts_ms").reset_index(drop=True)

    def price_at_offset(offset_ms, suffix):
        keys = coin_m[["market_id", "analysis_ts_ms"]].copy()
        keys["_ts"] = keys["analysis_ts_ms"] - offset_ms
        return pd.merge_asof(
            keys.sort_values("_ts"),
            coin_p[["ts_ms", "price"]].rename(columns={"ts_ms": "_ts", "price": f"p_{suffix}"}),
            on="_ts", direction="backward", tolerance=10 * 60 * 1000
        ).set_index("market_id")[f"p_{suffix}"]

    def price_at_ts(ts_series_ms, suffix):
        keys = coin_m[["market_id"]].copy()
        keys["_ts"] = ts_series_ms.values
        return pd.merge_asof(
            keys.sort_values("_ts"),
            coin_p[["ts_ms", "price"]].rename(columns={"ts_ms": "_ts", "price": f"p_{suffix}"}),
            on="_ts", direction="nearest", tolerance=5 * 60 * 1000
        ).set_index("market_id")[f"p_{suffix}"]

    p_now          = price_at_offset(0,               "now")
    p_15m          = price_at_offset(15  * 60 * 1000, "15m")
    p_1h           = price_at_offset(60  * 60 * 1000, "1h")
    p_4h           = price_at_offset(240 * 60 * 1000, "4h")
    p_window_start = price_at_ts(coin_m["window_start_ts"] * 1000, "ws")
    p_window_end   = price_at_ts(coin_m["end_ts"]          * 1000, "we")

    for _, m in coin_m.iterrows():
        mid = m["market_id"]

        # Outcome — skip if no Binance coverage for this window
        pw_start = p_window_start.get(mid)
        pw_end   = p_window_end.get(mid)
        if pd.isna(pw_start) or pd.isna(pw_end) or pw_start == 0:
            continue
        outcome = 1 if pw_end > pw_start else 0

        # Price momentum features
        pn  = p_now.get(mid)
        p15 = p_15m.get(mid)
        p1  = p_1h.get(mid)
        p4  = p_4h.get(mid)
        pc_15m = (pn - p15) / p15 if pn and p15 and p15 > 0 else None
        pc_1h  = (pn - p1)  / p1  if pn and p1  and p1  > 0 else None
        pc_4h  = (pn - p4)  / p4  if pn and p4  and p4  > 0 else None

        # Volatility + volume ratio (binary search over sorted klines)
        t2 = int(m["analysis_ts_ms"])
        t1 = t2 - 60  * 60 * 1000
        t0 = t2 - 120 * 60 * 1000

        i0 = int(np.searchsorted(ts_arr, t0))
        i1 = int(np.searchsorted(ts_arr, t1))
        i2 = int(np.searchsorted(ts_arr, t2, side="right"))

        window = price_arr[i1:i2]
        vol_1h = float(np.std(np.diff(window) / window[:-1])) if len(window) > 2 else None

        vol_prev  = vol_arr[i0:i1].sum()
        vol_last  = vol_arr[i1:i2].sum()
        vol_ratio = float(vol_last / vol_prev) if vol_prev > 0 else None

        dt = m["resolution_end_dt"]
        rows.append({
            "market_id":        mid,
            "coin":             coin,
            "timeframe":        m["timeframe"],
            "resolution_end":   dt.isoformat(),
            "resolution_hour":  dt.hour,
            "resolution_minute":dt.minute,
            "day_of_week":      dt.weekday(),
            "outcome":          outcome,
            "volume":           m["volume"],
            "fee_rate_bps":     m["fee_rate_bps"],
            "price_change_15m": round(pc_15m,   6) if pc_15m   is not None else None,
            "price_change_1h":  round(pc_1h,    6) if pc_1h    is not None else None,
            "price_change_4h":  round(pc_4h,    6) if pc_4h    is not None else None,
            "volatility_1h":    round(vol_1h,   6) if vol_1h   is not None else None,
            "volume_ratio_1h":  round(vol_ratio, 4) if vol_ratio is not None else None,
        })

    return rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    os.makedirs(CACHE_DIR, exist_ok=True)
    log("=" * 60)
    log("Starting accumulation run")

    # Load existing history
    if os.path.exists(HISTORY_FILE):
        df_existing  = pd.read_csv(HISTORY_FILE)
        existing_ids = set(df_existing["market_id"].astype(str))
        log(f"Existing history: {len(df_existing):,} markets")
    else:
        df_existing  = pd.DataFrame()
        existing_ids = set()
        log("No existing history — starting fresh")

    # Load market metadata from HuggingFace (cached, metadata doesn't change)
    log("Loading market metadata from HuggingFace...")
    from datasets import load_dataset
    ds   = load_dataset(HF_DATASET, "markets", split="train")
    df_m = ds.to_pandas()
    df_m.columns = [c.lower().strip() for c in df_m.columns]
    if "crypto" in df_m.columns and "coin" not in df_m.columns:
        df_m = df_m.rename(columns={"crypto": "coin"})
    df_m = df_m[df_m["timeframe"].isin(ALL_TIMEFRAMES)].copy()
    log(f"Markets: {len(df_m):,} rows across {len(ALL_COINS)} coins")

    df_m["resolution_end_dt"] = pd.to_datetime(df_m["end_ts"], unit="s")
    df_m["duration_sec"]      = df_m["timeframe"].map(DURATION_SEC).fillna(300).astype(int)
    df_m["window_start_ts"]   = df_m["end_ts"] - df_m["duration_sec"]
    df_m["analysis_ts"]       = df_m["window_start_ts"] - ANALYSIS_OFFSET_MIN * 60
    df_m["analysis_ts_ms"]    = df_m["analysis_ts"] * 1000

    # Time range for Binance kline cache (add buffer on each end)
    t_min_ms = int(df_m["analysis_ts_ms"].min()) - 4 * 60 * 60 * 1000
    t_max_ms = int(df_m["end_ts"].max())  * 1000 + 60 * 1000

    # Compute outcomes and features per coin
    all_rows = []
    for coin in ALL_COINS:
        if coin.upper() not in BINANCE_SYMBOL:
            log(f"  SKIP {coin}: no Binance symbol")
            continue
        coin_m = df_m[df_m["coin"].str.upper() == coin.upper()].copy()
        if coin_m.empty:
            log(f"  SKIP {coin}: no markets in dataset")
            continue

        coin_p = load_coin_klines(coin, t_min_ms, t_max_ms)
        if coin_p.empty:
            log(f"  SKIP {coin}: Binance returned no data")
            continue

        log(f"  {coin}: {len(coin_m):,} markets, {len(coin_p):,} klines")
        rows = compute_rows(coin_m, coin_p, coin)
        log(f"    -> {len(rows):,} with valid outcomes")
        all_rows.extend(rows)

    if not all_rows:
        log("No rows computed.")
        return

    # Merge with existing history (deduplicate by market_id)
    df_new    = pd.DataFrame(all_rows)
    df_new["market_id"] = df_new["market_id"].astype(str)
    df_to_add = df_new[~df_new["market_id"].isin(existing_ids)]

    log(f"New markets this run: {len(df_to_add):,}")
    log(f"Already in history:   {len(df_new) - len(df_to_add):,} (skipped)")

    if not df_to_add.empty:
        df_history = pd.concat([df_existing, df_to_add], ignore_index=True) \
                     if not df_existing.empty else df_to_add
        df_history.to_csv(HISTORY_FILE, index=False)
        dt_col = pd.to_datetime(df_history["resolution_end"])
        up   = int((df_history["outcome"] == 1).sum())
        down = int((df_history["outcome"] == 0).sum())
        log(f"Total: {len(df_history):,} markets  "
            f"{dt_col.min().date()} -> {dt_col.max().date()}")
        log(f"Outcome: Up={up:,}  Down={down:,}  ({100*up/(up+down):.1f}% Up)")
    else:
        log("Nothing new to add.")

    log("Done.")


if __name__ == "__main__":
    main()

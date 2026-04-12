"""
Evaluation harness for Polymarket event-betting research.

Framing: bankroll-simulated, segmented, rolling-OOS event-betting policy.
This is NOT a "realistic trading policy" — see Known Simulation Limitations below.

Reads from ~/.cache/polymarket-research/history.csv (built by data/accumulate.py).
Do not modify — this is the fixed ground truth for all experiments.

Known Simulation Limitations
─────────────────────────────
- entry_price ≈ 0.505: historical Polymarket CLOB prices are unavailable.
  All payout calculations use this heuristic placeholder.
- Stake cap = liquidity_usd * 0.01: a heuristic market-impact guard, not a
  real order book model.
- Fee deduction uses fee_rate_bps from the CSV when present; 0 when absent.
- Outcome is binary (price up vs. down in a short window). Not identical to
  Polymarket's actual settlement logic.
"""

import os
import math
from collections import defaultdict

import pandas as pd
import numpy as np

CACHE_DIR    = os.path.join(os.path.expanduser("~"), ".cache", "polymarket-research")
HISTORY_FILE = os.path.join(CACHE_DIR, "history.csv")

TRAIN_DAYS = 80   # first ~80 days (Dec 27 – Mar 17)
VAL_DAYS   = 20   # held-out validation (Mar 17 – Apr 6)

TIMEFRAME_MIN = {"5-minute": 5, "15-minute": 15, "1-hour": 60, "4-hour": 240}

# Features the strategy function is allowed to see
ALLOWED_FEATURES = {
    "coin", "resolution_hour", "resolution_minute", "day_of_week",
    "duration_min", "entry_price", "liquidity_usd",
    "price_change_15m", "price_change_1h", "price_change_4h",
    "volatility_1h", "volume_ratio_1h",
}

# Columns never passed to strategy_fn
_FORBIDDEN = {"outcome", "market_id", "condition_id", "up_token_id",
              "down_token_id", "fee_rate_bps", "resolution_end", "timeframe"}

_MIN_THIN_TRADES = 30   # folds / segments below this are flagged as thin


# ── Data loading ──────────────────────────────────────────────────────────────

def load_markets(split="train"):
    """
    Load markets from history.csv and return the requested split.

    split="train"  first TRAIN_DAYS of data
    split="val"    next VAL_DAYS of data (held out — only touch at the end)
    split="all"    everything
    """
    if not os.path.exists(HISTORY_FILE):
        raise FileNotFoundError(
            f"No data found at {HISTORY_FILE}\nRun:  uv run data/accumulate.py"
        )

    df = pd.read_csv(HISTORY_FILE)

    if "timeframe" in df.columns:
        df["duration_min"] = df["timeframe"].map(TIMEFRAME_MIN).fillna(5).astype(int)
    if "volume" in df.columns:
        df = df.rename(columns={"volume": "liquidity_usd"})

    # entry_price is historically unavailable; placeholder documented in Known Limitations
    df["entry_price"] = None

    if split == "all":
        return df.reset_index(drop=True)

    df["resolution_end"] = pd.to_datetime(df["resolution_end"], errors="coerce")
    df = df.dropna(subset=["resolution_end"])

    t_min     = df["resolution_end"].min()
    train_end = t_min + pd.Timedelta(days=TRAIN_DAYS)
    val_end   = train_end + pd.Timedelta(days=VAL_DAYS)

    if split == "train":
        return df[df["resolution_end"] < train_end].reset_index(drop=True)
    if split == "val":
        return df[(df["resolution_end"] >= train_end) &
                  (df["resolution_end"] < val_end)].reset_index(drop=True)

    return df.reset_index(drop=True)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _normalize_response(raw):
    """Convert strategy return value to a decision dict or None (skip trade)."""
    if isinstance(raw, int):
        if raw == 0:
            return None
        return {"side": raw, "size": 1.0}
    if isinstance(raw, dict):
        side = raw.get("side", 0)
        if side not in (-1, 1):
            return None
        size = float(raw.get("size", 1.0))
        size = max(0.0, min(1.0, size))
        if size == 0.0:
            return None
        return {"side": side, "size": size}
    return None


def _seg_metrics(records):
    """
    Compute segment metrics from a list of (net_pnl, stake, win) tuples.
    segment_return is volume-weighted: aggregate PnL / aggregate stake.
    """
    if not records:
        return {"num_trades": 0, "segment_return": 0.0, "win_rate": 0.0}
    pnls   = [r[0] for r in records]
    stakes = [r[1] for r in records]
    wins   = [r[2] for r in records]
    total_stake = sum(stakes)
    seg_return  = sum(pnls) / total_stake if total_stake > 0 else 0.0
    return {
        "num_trades":     len(records),
        "segment_return": round(seg_return, 6),
        "win_rate":       round(sum(wins) / len(wins), 6),
    }


def _empty_result():
    """Return an all-zero/None result for empty inputs."""
    return {
        "final_bankroll":        0.0,
        "total_return":          0.0,
        "max_drawdown":          0.0,
        "trade_sharpe":          0.0,
        "sortino":               None,
        "sortino_defined":       False,
        "win_rate":              0.0,
        "profit_factor":         None,
        "profit_factor_defined": False,
        "num_trades":            0,
        "participation_rate":    0.0,
        "segments": {
            "by_coin":         {},
            "by_duration":     {},
            "by_hour":         {},
            "by_weekday":      {},
            "by_volatility":   {},
            "by_volume_ratio": {},
        },
    }


# ── Core evaluation ───────────────────────────────────────────────────────────

def _evaluate_df(strategy_fn, df, initial_bankroll=10_000.0, risk_per_trade=0.01):
    """
    Run strategy_fn against a DataFrame of markets with bankroll simulation.

    Uses iterrows() intentionally — bankroll is stateful, so each trade's stake
    depends on the running balance. Vectorization would break this dependency.
    """
    if df.empty:
        return _empty_result()

    feature_cols = [c for c in df.columns
                    if c not in _FORBIDDEN and c in ALLOWED_FEATURES]

    bankroll     = float(initial_bankroll)
    equity_curve = []
    trade_pnls   = []
    trade_stakes = []

    seg_coin   = defaultdict(list)
    seg_dur    = defaultdict(list)
    seg_hour   = defaultdict(list)
    seg_dow    = defaultdict(list)
    seg_vol    = defaultdict(list)
    seg_volrat = defaultdict(list)

    for _, row in df.iterrows():
        # Build masked market dict — strategy sees only ALLOWED_FEATURES
        market = {c: row[c] for c in feature_cols}
        market = {k: (None if isinstance(v, float) and math.isnan(v) else v)
                  for k, v in market.items()}

        try:
            raw = strategy_fn(market)
        except Exception:
            continue

        decision = _normalize_response(raw)
        if decision is None:
            continue

        side = decision["side"]
        size = decision["size"]

        # Stake: fraction of bankroll, optionally capped by liquidity heuristic
        stake = bankroll * risk_per_trade * size
        liq   = market.get("liquidity_usd")
        if liq is not None and not (isinstance(liq, float) and math.isnan(liq)):
            stake = min(stake, float(liq) * 0.01)
        stake = max(0.0, stake)
        if stake == 0.0:
            continue

        # Fee from raw row — NOT from masked market dict (strategy can't see it)
        fee_bps = row.get("fee_rate_bps")
        fee = (stake * float(fee_bps) / 10_000.0
               if fee_bps is not None and not (isinstance(fee_bps, float) and math.isnan(fee_bps))
               else 0.0)

        # Payout (entry_price is None historically → heuristic placeholder 0.505)
        actual_up = int(row["outcome"])
        up_price  = max(0.01, min(0.99, float(market.get("entry_price") or 0.505)))

        if side > 0:   # bet Up
            gross = stake * ((1.0 - up_price) / up_price) if actual_up == 1 else -stake
        else:          # bet Down
            dn    = 1.0 - up_price
            gross = stake * ((1.0 - dn) / dn) if actual_up == 0 else -stake

        net_pnl  = gross - fee
        bankroll += net_pnl
        win       = net_pnl > 0

        equity_curve.append(bankroll)
        trade_pnls.append(net_pnl)
        trade_stakes.append(stake)

        # Segment accumulators
        record = (net_pnl, stake, win)
        coin   = market.get("coin")
        dur    = market.get("duration_min")
        hour   = market.get("resolution_hour")
        dow    = market.get("day_of_week")
        vol    = market.get("volatility_1h")
        volrat = market.get("volume_ratio_1h")
        if coin is not None: seg_coin[coin].append(record)
        if dur  is not None: seg_dur[int(dur)].append(record)
        if hour is not None: seg_hour[int(hour)].append(record)
        if dow  is not None: seg_dow[int(dow)].append(record)
        if vol is not None:
            vb = "low" if vol < 0.00025 else ("high" if vol >= 0.00055 else "mid")
            seg_vol[vb].append(record)
        if volrat is not None:
            rb = "high" if volrat >= 1.5 else ("low" if volrat < 0.8 else "avg")
            seg_volrat[rb].append(record)

    num_trades = len(trade_pnls)
    if num_trades == 0:
        return _empty_result()

    # Max drawdown — computed over full equity curve (initial bankroll prepended)
    equity_arr = np.array([initial_bankroll] + equity_curve)
    peak       = np.maximum.accumulate(equity_arr)
    max_drawdown = float(((peak - equity_arr) / np.maximum(peak, 1e-9)).max())

    # Trade-level return ratios (pnl / stake)
    pnl_arr   = np.array(trade_pnls)
    stake_arr = np.array(trade_stakes)
    ratios    = pnl_arr / stake_arr
    mean_r    = float(ratios.mean())
    std_r     = float(ratios.std())

    # trade_sharpe — NOT annualized (these are event trades, not daily returns)
    trade_sharpe = (mean_r / std_r) if std_r > 1e-9 else 0.0

    # sortino — downside deviation only; None when undefined
    # Note: in binary event markets, losing trades all give ratio ≈ -1.0,
    # making downside.std() ≈ 0. Guard against near-zero denominator.
    downside = ratios[ratios < 0]
    if len(downside) > 1:
        ds = float(downside.std())
        if ds > 1e-9:
            sortino         = mean_r / ds
            sortino_defined = True
        else:
            sortino         = None   # all losses identical (binary market artefact)
            sortino_defined = False
    else:
        sortino         = None
        sortino_defined = False

    win_rate = float((pnl_arr > 0).mean())

    # profit_factor — None when no losing trades
    gross_wins   = float(pnl_arr[pnl_arr > 0].sum()) if (pnl_arr > 0).any() else 0.0
    gross_losses = float(-pnl_arr[pnl_arr < 0].sum()) if (pnl_arr < 0).any() else 0.0
    if gross_losses > 1e-9:
        profit_factor = gross_wins / gross_losses
        pf_defined    = True
    else:
        profit_factor = None
        pf_defined    = False

    total_return      = (bankroll - initial_bankroll) / initial_bankroll
    participation_rate = num_trades / len(df)

    return {
        "final_bankroll":        round(bankroll, 4),
        "total_return":          round(total_return, 6),
        "max_drawdown":          round(max_drawdown, 6),
        "trade_sharpe":          round(trade_sharpe, 6),
        "sortino":               round(sortino, 6) if sortino_defined else None,
        "sortino_defined":       sortino_defined,
        "win_rate":              round(win_rate, 6),
        "profit_factor":         round(profit_factor, 6) if pf_defined else None,
        "profit_factor_defined": pf_defined,
        "num_trades":            num_trades,
        "participation_rate":    round(participation_rate, 6),
        "segments": {
            "by_coin":         {k: _seg_metrics(v) for k, v in seg_coin.items()},
            "by_duration":     {k: _seg_metrics(v) for k, v in seg_dur.items()},
            "by_hour":         {k: _seg_metrics(v) for k, v in seg_hour.items()},
            "by_weekday":      {k: _seg_metrics(v) for k, v in seg_dow.items()},
            "by_volatility":   {k: _seg_metrics(v) for k, v in seg_vol.items()},
            "by_volume_ratio": {k: _seg_metrics(v) for k, v in seg_volrat.items()},
        },
    }


# ── Public API ────────────────────────────────────────────────────────────────

def evaluate_strategy(strategy_fn, split="train",
                      initial_bankroll=10_000.0, risk_per_trade=0.01):
    """
    Evaluate strategy_fn against resolved markets.

    strategy_fn(market: dict) -> dict | int
        dict: {"side": int, "size": float, "confidence": float, "reason": str}
        int:  +1 = bet Up,  -1 = bet Down,  0 = skip  (backward-compatible)

    Returns a bankroll-simulation result dict including per-segment breakdown.
    """
    df = load_markets(split=split)
    if df.empty:
        return _empty_result()
    return _evaluate_df(strategy_fn, df,
                        initial_bankroll=initial_bankroll,
                        risk_per_trade=risk_per_trade)


def evaluate_oos(strategy_fn, lookback_buffer_days=45, test_days=15, step_days=15,
                 initial_bankroll=10_000.0, risk_per_trade=0.01):
    """
    Rolling out-of-sample (OOS) evaluation of a fixed strategy.

    This is NOT walk-forward training. strategy_fn is unchanged across all folds.

    lookback_buffer_days is not training data — the evaluator does not use the
    lookback period for any computation. It only shifts the test window forward
    to avoid overlap with the data the agent used during strategy development.

    Folds with fewer than 30 trades are flagged as "thin" and excluded from
    the oos_pass gate (but still printed for transparency).

    oos_pass = True  when:
      - All substantial folds have worst_score > -0.10
      - At least 2/3 of substantial folds have a positive score
    """
    df_all = load_markets("all")
    if df_all.empty:
        return {"num_folds": 0, "avg_score": 0.0, "worst_score": 0.0,
                "folds": [], "oos_pass": False}

    df_all["resolution_end"] = pd.to_datetime(df_all["resolution_end"], errors="coerce")
    df_all = (df_all.dropna(subset=["resolution_end"])
              .sort_values("resolution_end")
              .reset_index(drop=True))

    t_min = df_all["resolution_end"].min()
    t_max = df_all["resolution_end"].max()

    window_start = t_min
    fold_results = []

    while True:
        test_start = window_start + pd.Timedelta(days=lookback_buffer_days)
        test_end   = test_start   + pd.Timedelta(days=test_days)
        if test_end > t_max:
            break

        test_df = df_all[
            (df_all["resolution_end"] >= test_start) &
            (df_all["resolution_end"] <  test_end)
        ].reset_index(drop=True)

        if len(test_df) < 10:
            window_start += pd.Timedelta(days=step_days)
            continue

        metrics = _evaluate_df(strategy_fn, test_df,
                               initial_bankroll=initial_bankroll,
                               risk_per_trade=risk_per_trade)
        score = (metrics["total_return"]
                 - 0.5 * metrics["max_drawdown"]
                 + 0.1 * metrics["trade_sharpe"]
                 + 0.15 * (metrics["win_rate"] - 0.5))
        thin = metrics["num_trades"] < _MIN_THIN_TRADES

        fold_results.append({
            "test_start":  test_start.date().isoformat(),
            "test_end":    test_end.date().isoformat(),
            "score":       round(score, 6),
            "total_return":  metrics["total_return"],
            "max_drawdown":  metrics["max_drawdown"],
            "num_trades":    metrics["num_trades"],
            "thin":          thin,
        })

        window_start += pd.Timedelta(days=step_days)

    if not fold_results:
        return {"num_folds": 0, "avg_score": 0.0, "worst_score": 0.0,
                "folds": [], "oos_pass": False}

    # Thin folds excluded from oos_pass; use them as fallback only if all folds are thin
    substantial = [f for f in fold_results if not f["thin"]]
    scored      = substantial if substantial else fold_results
    scores      = [f["score"] for f in scored]
    n_positive  = sum(1 for s in scores if s > 0)
    oos_pass    = (
        len(scores) > 0
        and min(scores) > -0.10
        and n_positive >= math.ceil(len(scores) * 2 / 3)
    )

    return {
        "num_folds":   len(fold_results),
        "avg_score":   round(float(np.mean(scores)), 6),
        "worst_score": round(float(min(scores)), 6),
        "folds":       fold_results,
        "oos_pass":    oos_pass,
    }

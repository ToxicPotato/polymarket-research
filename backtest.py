"""
Polymarket event-betting strategy — THIS IS THE FILE YOU (AND THE AGENT) MODIFY.

Framing: bankroll-simulated event-betting policy for discrete crypto Up/Down markets.
NOT a "realistic trading policy" — historical Polymarket entry prices are unavailable.
See evaluate.py for full Known Simulation Limitations.

Markets: 5–15 minute price-direction bets on crypto (SOL, BTC, ETH, XRP, DOGE, BNB).
Goal:    maximize score on the TRAIN split.
NEVER evaluate on split="val" during the agent loop — that is held-out data.

Available features in strategy(market):
    market['coin']               - "SOL", "BTC", "ETH", "XRP", "DOGE", "BNB"
    market['resolution_hour']    - UTC hour when window opens (0–23)
    market['resolution_minute']  - UTC minute (0–59)
    market['day_of_week']        - 0=Monday … 6=Sunday
    market['duration_min']       - window length: 5, 10, or 15
    market['entry_price']        - always None historically (heuristic ~0.505 used internally)
    market['liquidity_usd']      - market liquidity (USD)
    market['price_change_15m']   - Binance: % price change in 15 min before analysis
    market['price_change_1h']    - Binance: % price change in 60 min before analysis
    market['price_change_4h']    - Binance: % price change in 4h before analysis
    market['volatility_1h']      - Binance: std of 1-min returns over last 60 min
    market['volume_ratio_1h']    - Binance: volume last 60 min / previous 60 min

Return: dict with keys:
    side        int    -1 = DOWN, 0 = skip, +1 = UP
    size        float  0.0–1.0, fraction of risk_per_trade to apply
    confidence  float  optional, 0.0–1.0
    reason      str    optional, for logging/debug

  OR return an int (+1/-1/0) for backward compatibility.

DO NOT access market['outcome'] — it is not passed to you.
DO NOT call evaluate_strategy(split="val") during the agent loop.
DO NOT modify evaluate.py.
"""

from evaluate import evaluate_strategy, evaluate_oos

_MIN_SAMPLE = 30   # segments below this are marked *low sample* in output


# ── Strategy (modify this function) ──────────────────────────────────────────

def strategy(market):
    hour = market.get("resolution_hour")
    if hour not in {7, 17, 19, 20, 21}:
        return {"side": 0, "size": 0.0, "confidence": 0.0, "reason": "hour filter"}
    coin = market.get("coin")
    duration_min = market.get("duration_min")
    day_of_week = market.get("day_of_week")
    if coin == "ETH" and hour == 20:
        return {"side": 0, "size": 0.0, "confidence": 0.0, "reason": "coin-hour filter"}
    if coin == "ETH" and hour == 19 and duration_min == 5:
        return {"side": 0, "size": 0.0, "confidence": 0.0, "reason": "coin-hour-duration filter"}
    if day_of_week == 0:
        return {"side": 0, "size": 0.0, "confidence": 0.0, "reason": "weekday filter"}
    if day_of_week == 5:
        return {"side": 0, "size": 0.0, "confidence": 0.0, "reason": "weekday filter"}
    if duration_min == 240:
        return {"side": 0, "size": 0.0, "confidence": 0.0, "reason": "duration filter"}
    if hour == 7 and duration_min == 60:
        return {"side": 0, "size": 0.0, "confidence": 0.0, "reason": "hour-duration filter"}
    if hour == 7 and day_of_week == 3 and duration_min == 5:
        return {"side": 0, "size": 0.0, "confidence": 0.0, "reason": "hour-weekday-duration filter"}
    if hour == 7 and day_of_week == 2 and coin == "SOL" and duration_min == 5:
        return {"side": 0, "size": 0.0, "confidence": 0.0, "reason": "hour-weekday-coin-duration filter"}
    if hour == 7 and day_of_week == 3 and coin == "ETH" and duration_min == 15:
        return {"side": 0, "size": 0.0, "confidence": 0.0, "reason": "hour-weekday-coin-duration filter"}

    signal = market.get("price_change_1h")
    if signal is None:
        return {"side": 0, "size": 0.0, "confidence": 0.0, "reason": "no price data"}

    threshold = 0.0150
    if hour == 7:
        threshold = 0.0000
    if hour == 17:
        threshold = 0.0225
    if hour == 19:
        threshold = 0.0150
    if hour == 20:
        threshold = 0.0175
    if hour == 21:
        threshold = 0.0200
        threshold += 0.0025
    if coin == "BTC":
        threshold -= 0.0050
    threshold = max(0.0, threshold)
    if day_of_week == 6 and coin == "BTC":
        threshold += 0.0050
    if signal > threshold:
        return {"side": -1, "size": 1.0, "confidence": abs(signal), "reason": "mean-reversion down"}
    if signal < -threshold:
        return {"side": 1,  "size": 1.0, "confidence": abs(signal), "reason": "mean-reversion up"}

    return {"side": 0, "size": 0.0, "confidence": 0.0, "reason": "no signal"}

# ── Output helpers ────────────────────────────────────────────────────────────

def _dash(v, decimals=4):
    return f"{v:.{decimals}f}" if v is not None else "N/A"


def _fmt_seg(name, m):
    tag = "  *low sample*" if m["num_trades"] < _MIN_SAMPLE else ""
    return (f"  {str(name):<7}| trades={m['num_trades']:<5} "
            f"ret={m['segment_return']:+.4f}  win={m['win_rate']:.4f}{tag}")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    results = evaluate_strategy(strategy, split="train")
    oos     = evaluate_oos(strategy)

    score = (results["total_return"]
             - 0.5 * results["max_drawdown"]
             + 0.1 * results["trade_sharpe"]
             + 0.15 * (results["win_rate"] - 0.5))

    print("---")
    print(f"score:              {score:.4f}   # heuristic: total_return - 0.5*max_dd + 0.1*trade_sharpe + 0.15*(win_rate-0.5)")
    print(f"final_bankroll:     {results['final_bankroll']:.2f}")
    print(f"total_return:       {results['total_return']:.4f}")
    print(f"max_drawdown:       {results['max_drawdown']:.4f}")
    print(f"trade_sharpe:       {results['trade_sharpe']:.4f}")
    print(f"sortino:            {_dash(results['sortino'])}")
    print(f"win_rate:           {results['win_rate']:.4f}")
    print(f"profit_factor:      {_dash(results['profit_factor'])}")
    print(f"num_trades:         {results['num_trades']}")
    print(f"participation_rate: {results['participation_rate']:.4f}")

    segs = results["segments"]
    print()
    print(f"--- segments (min {_MIN_SAMPLE} trades to trust) ---")
    for label, seg_dict in [
        ("by_coin",         segs["by_coin"]),
        ("by_duration",     segs["by_duration"]),
        ("by_hour",         segs["by_hour"]),
        ("by_weekday",      segs["by_weekday"]),
        ("by_volatility",   segs["by_volatility"]),
        ("by_volume_ratio", segs["by_volume_ratio"]),
    ]:
        if not seg_dict:
            continue
        print(f"{label}:")
        # Sufficient-sample segments first, then thin (sorted by trade count within each group)
        items = sorted(
            seg_dict.items(),
            key=lambda kv: (-(kv[1]["num_trades"] >= _MIN_SAMPLE), -kv[1]["num_trades"]),
        )
        for name, m in items:
            print(_fmt_seg(name, m))

    print()
    print(f"--- out-of-sample ({oos['num_folds']} folds) ---")
    print(f"avg_score:   {oos['avg_score']:.4f}")
    print(f"worst_score: {oos['worst_score']:.4f}")
    print(f"oos_pass:    {oos['oos_pass']}")
    for fold in oos["folds"]:
        thin_tag = "  *thin*" if fold.get("thin") else ""
        print(f"  {fold['test_start']} -> {fold['test_end']}  "
              f"score={fold['score']:+.4f}  trades={fold['num_trades']}{thin_tag}")

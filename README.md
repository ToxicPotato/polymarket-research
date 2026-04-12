# polymarket-research

Autonomous Polymarket prediction market strategy research. An AI agent modifies a trading strategy, backtests it against real historical markets, keeps what works, discards what doesn't, and repeats — completing hundreds of experiments overnight.

---

## How it works

Three files that matter:

- **`evaluate.py`** — fixed harness. Loads market data, splits train/val, evaluates a strategy. Do not modify.
- **`backtest.py`** — the single file the agent edits. Contains the `strategy()` function. Everything is fair game: thresholds, filters, coin selection, time-of-day patterns, momentum, volatility.
- **`program.md`** — instructions for the agent. Point your agent here and let it go.

The agent loop: edit `backtest.py` → commit → run → log score/metrics to `results_v2.tsv` → keep if improved and all hard filters pass, `git reset --hard HEAD~1` if not → repeat.

---

## Data

75,000+ resolved Polymarket Up/Down crypto markets with Binance price features.

- **Coins**: SOL, BTC, ETH, XRP, DOGE, BNB
- **Timeframes**: 5-minute, 15-minute, 1-hour, 4-hour
- **Date range**: Dec 27, 2025 → present (grows daily)
- **Train split**: first 80 days — used during experiments
- **Val split**: next 20 days — held out, only touch at the very end

Features available to the strategy (computed at T-1min, no lookahead):
`price_change_15m`, `price_change_1h`, `price_change_4h`, `volatility_1h`, `volume_ratio_1h`, `coin`, `duration_min`, `resolution_hour`, `day_of_week`, `liquidity_usd`

---

## Quick start

**Requirements:** Python 3.10+, [uv](https://docs.astral.sh/uv/). No GPU needed.

```bash
# 1. Install dependencies
uv sync

# 2. Download data (one-time, ~5 min)
uv run data/accumulate.py

# 3. Run a backtest
uv run backtest.py
```

---

## Dashboard

Monitor experiment progress in real time:

```bash
uv run dashboard/run.py
# → http://localhost:8000
```

Shows score over time, all iterations plotted by status (keep/discard/crash), win rate, OOS pass rate, and live run output. Updates automatically via SSE as the agent writes results.

---

## Running the agent

Point Claude Code (or any agent) at this repo and say:

```
Have a look at program.md and let's kick off a new experiment.
```

The agent will propose a `research/<tag>` branch, establish a baseline, then loop autonomously.

---

## Project structure

```
evaluate.py          — fixed harness (do not modify)
backtest.py          — strategy (agent modifies this)
program.md           — agent instructions
data/
  accumulate.py      — daily data collection from HuggingFace + Binance
  run_accumulate.bat — Windows Task Scheduler wrapper (runs daily at 4 AM)
dashboard/
  run.py             — start the dashboard (uv run dashboard/run.py, port 8000)
  api/               — FastAPI backend, SSE live updates
  frontend/          — vanilla JS + Chart.js, no build step
pyproject.toml       — dependencies
```

---

## Design choices

- **Single file to modify.** The agent only touches `backtest.py`. Diffs are small and reviewable.
- **No lookahead.** All features are computed at T-1min (1 minute before the window opens), matching what would be available in live trading.
- **Real data only.** Outcomes computed from Binance spot prices. No synthetic data.
- **Held-out val split.** 20 days of markets never seen during experiments — the final sanity check before deploying a strategy.
- **Fast iterations.** A full backtest over 50k markets runs in ~5 seconds on CPU.
- **Live dashboard.** A local web UI tracks all experiments, score progression, and agent log output in real time — no manual log parsing needed.

---

## License

MIT

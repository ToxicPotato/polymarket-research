# polymarket-research

Autonomous Polymarket prediction market strategy research.

## Framing

This system builds a **bankroll-simulated event-betting policy** for discrete crypto
Up/Down markets. It is NOT a "realistic trading policy" — historical Polymarket entry
prices (CLOB order book) are unavailable, so we cannot verify whether we are buying
value. We only know whether the direction was correct.

### Known Simulation Limitations

- `entry_price ≈ 0.505`: heuristic placeholder. Real edge vs. crowd probability unknown.
- Stake cap `= liquidity_usd * 0.01`: heuristic market-impact guard, not a real order book.
- Fees deducted from `fee_rate_bps` in the CSV when present; 0 when absent.
- Outcome is binary price direction — not identical to Polymarket's actual settlement.

These limitations should inform how you interpret results. High training score does not
guarantee real-world profitability.

---

## Setup

To set up a new experiment, work with the user to:

1. **Agree on a run tag**: propose a tag based on today's date (e.g. `apr12`). The branch
   `research/<tag>` must not already exist.
2. **Create the branch**: `git checkout -b research/<tag>` from current master.
3. **Read the in-scope files**: Read these files for full context:
   - `evaluate.py` — fixed evaluation harness. Do not modify.
   - `backtest.py` — the file you modify. Strategy logic only.
4. **Verify data exists**: Check that `~/.cache/polymarket-research/history.csv` exists
   with at least a few hundred rows. If not, tell the human to run `uv run data/accumulate.py`.
5. **Initialize results_v2.tsv**: Create with the header row only:
   ```
   commit	score	total_return	max_drawdown	trade_sharpe	win_rate	num_trades	oos_pass	status	description
   ```
   Note: old `results.tsv` values are NOT comparable to `results_v2.tsv` — different metrics,
   different payout model, different logging convention.
6. **Confirm and go**.

---

## Experimentation

Run a backtest: `uv run backtest.py`

**What you CAN do:**
- Modify `backtest.py` — the only file you edit. Change `strategy()` freely: filtering
  logic, feature combinations, segment-specific rules, simple heuristics.

**What you CANNOT do:**
- Modify `evaluate.py`. It is read-only.
- Access `market['outcome']` inside `strategy()`. That is the future.
- Call `evaluate_strategy(split="val")` during the experiment loop. Val is held out.
- Install new packages.

### Score (ranking heuristic)

```
score = total_return - 0.5 * max_drawdown + 0.1 * trade_sharpe + 0.15 * (win_rate - 0.5)
```

**Score is a ranking heuristic only.** Hard filters decide keep/discard. Score ranks
candidates that have already passed all filters.

Hard filters — a result only counts as `keep` if ALL of:
- `num_trades >= 100`
- `max_drawdown <= 0.25`
- `oos_pass: True`

### Out-of-sample (OOS) evaluation

`evaluate_oos()` rolls a test window over the dataset and evaluates the fixed strategy
on each unseen window.

**Important:** `lookback_buffer_days` is NOT training data. The evaluator does not use
the lookback period for any computation. It only shifts the test window forward to avoid
testing on data the agent used during strategy development. There is no fitting per fold.

`oos_pass: True` requires: worst fold score > -0.10 AND at least 2/3 of substantial
folds (30+ trades) have a positive score.

Thin folds (< 30 trades) are printed for transparency but excluded from `oos_pass`.

---

## Segment-first workflow

This is the correct order of operations. Do NOT skip steps.

**Step 1 — Find a segment with edge.**
Run the baseline. Read the segment output carefully.
Look for a `by_coin`, `by_hour`, or `by_duration` segment with:
- 50+ trades (ignore `*low sample*` segments)
- positive `ret` and `win` > 0.52

**Step 2 — Build a simple rule for that ONE segment.**
Filter to that segment only. Do not try to generalize yet.
Example: `if market['coin'] != 'ETH' or market['resolution_hour'] != 19: skip`

**Step 3 — Check hard filters.**
Run the backtest. Check in order:
1. `num_trades >= 100` — if not, the rule is too narrow. Widen or change segment.
2. `max_drawdown <= 0.25` — if not, the drawdown is too high. Tighten the rule.
3. `oos_pass: True` — if not, the edge is in-sample only. Discard.

**Step 4 — Start with flat sizing.**
Always use `size = 1.0` until edge is confirmed. Do NOT experiment with variable
`size` until a strategy passes all hard filters with flat sizing.

**Step 5 — Generalize only if evidence supports it.**
Add a second coin or time segment only if:
- Score stays at least as high as before
- max_drawdown does not increase
- oos_pass remains True

Never add complexity without evidence from the segment report.

**Step 6 — Add sizing (optional, after Step 5).**
Only after edge is proven on flat sizing: experiment with `size` proportional to
`confidence` or edge signal strength. This should improve score, not just total_return.

---

## Output format

```
---
score:              0.1234   # heuristic: total_return - 0.5*max_dd + 0.1*trade_sharpe
final_bankroll:     11234.00
total_return:       0.1800
max_drawdown:       0.0420
trade_sharpe:       1.2300
sortino:            N/A
win_rate:           0.5400
profit_factor:      1.4200
num_trades:         847
participation_rate: 0.0169

--- segments (min 30 trades to trust) ---
by_coin:
  BTC    | trades=234   ret=+0.2100  win=0.5700
  ETH    | trades=189   ret=+0.1500  win=0.5200
  SOL    | trades=28    ret=+0.0400  win=0.5000  *low sample*
by_duration:
  ...
by_hour:
  ...
by_weekday:
  ...

--- out-of-sample (3 folds) ---
avg_score:   0.0980
worst_score: 0.0210
oos_pass:    True
  2026-02-10 -> 2026-02-25  score=+0.0340  trades=147
  2026-02-25 -> 2026-03-12  score=+0.0180  trades=477
  2026-03-12 -> 2026-03-27  score=+0.0210  trades=83
```

Extract key metrics:
```bash
grep "^score:\|^total_return:\|^win_rate:\|^max_drawdown:\|^num_trades:\|^oos_pass:" run.log
```

Crash detection: if the above grep returns nothing → the run crashed.
Check the full log: `tail -n 50 run.log`

---

## Logging results

Log to `results_v2.tsv` (tab-separated). Do NOT commit it.

Header:
```
commit	score	total_return	max_drawdown	trade_sharpe	win_rate	num_trades	oos_pass	status	description
```

Columns:
1. `commit` — git commit hash (7 chars)
2. `score` — composite score
3. `total_return` — bankroll total return
4. `max_drawdown` — peak-to-trough drawdown
5. `trade_sharpe` — trade-level Sharpe (not annualized)
6. `win_rate` — fraction of trades that were profitable (0.0–1.0)
7. `num_trades` — total trades
8. `oos_pass` — True/False
9. `status` — `keep`, `discard`, or `crash`
10. `description` — short description of what was tried

Only log `status: keep` if ALL hard filters pass (num_trades >= 100, max_drawdown <= 0.25,
oos_pass: True). Log `discard` otherwise — it is still useful data.

---

## The experiment loop

Branch: `research/<tag>`

LOOP FOREVER:

1. Check git state (current branch/commit).
2. Read segment report from last run. Identify the best untested segment.
3. Tune `backtest.py` using the segment-first workflow above.
4. `git commit`
5. Run: `uv run backtest.py > run.log 2>&1`
6. Parse results: `grep "^score:\|^total_return:\|^max_drawdown:\|^num_trades:\|^oos_pass:" run.log`
7. If grep is empty → crash. Run `tail -n 50 run.log`. Fix if trivial, skip otherwise.
8. Check hard filters: `num_trades >= 100`, `max_drawdown <= 0.25`, `oos_pass: True`.
9. Log to `results_v2.tsv`.
10. If score improved AND all hard filters pass → keep. Otherwise → `git reset --hard HEAD~1`.

**Timeout**: Each backtest run should finish in under 30 seconds. If exceeded, kill it
and treat as a crash.

**Statistical significance**: If `num_trades < 100`, do not treat the result as reliable.
Widen the strategy or accept that this segment doesn't have enough data.

**Segment sample size**: Do not build rules around segments marked `*low sample*`
(fewer than 30 trades). These are unreliable regardless of the reported `ret`.

**NEVER STOP**: Once the loop begins, do NOT ask the human if you should continue.
You are autonomous. If you run out of ideas, re-read the full segment output — including
`by_volatility` and `by_volume_ratio` — and look for untested dimensions with edge.
If recent iterations have not improved score by at least 0.01, stop refining the current
approach and try a different feature or signal entirely.
The loop runs until the human interrupts you.

**NEVER pre-test**: Do NOT run `uv run backtest.py` before committing. Always commit
first, then run. Every run must be logged to `results_v2.tsv` — both keep and discard.

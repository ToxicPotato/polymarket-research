import { fetchExperiments, fetchRunlog, fetchGitInfo } from "./api.js";
import { initCharts, updateCharts } from "./charts.js";
import { renderTable } from "./table.js";
import { renderRunlog } from "./runlog.js";
import { startSSE } from "./sse.js";

// ── Best experiment summary card ─────────────────────────
function updateBestCard(experiments, bestCommit) {
  const best = experiments.find(e => e.commit === bestCommit);
  if (!best) return;

  const fmt = (v, d = 4) => (v !== null && v !== undefined) ? Number(v).toFixed(d) : "—";

  document.getElementById("best-score").textContent    = fmt(best.score);
  document.getElementById("best-totalret").textContent = fmt(best.total_return);
  document.getElementById("best-maxdd").textContent    = fmt(best.max_drawdown);
  document.getElementById("best-winrate").textContent  = best.win_rate !== null && best.win_rate !== undefined
    ? (best.win_rate * 100).toFixed(2) + "%"
    : "—";
  document.getElementById("best-sharpe").textContent   = fmt(best.trade_sharpe);
  document.getElementById("best-trades").textContent   = best.num_trades !== null
    ? best.num_trades.toLocaleString()
    : "—";
  document.getElementById("best-desc").textContent     = best.description || "—";
}

// ── Iteration stats ───────────────────────────────────────
function updateIterStats(experiments) {
  const keep    = experiments.filter(e => e.status === "keep").length;
  const discard = experiments.filter(e => e.status === "discard").length;
  const crash   = experiments.filter(e => e.status === "crash").length;
  const total   = experiments.length;

  const keepWithOos  = experiments.filter(e => e.status === "keep" && e.oos_pass === true).length;
  const oosRate = keep > 0 ? `${Math.round((keepWithOos / keep) * 100)}%` : "—";

  document.getElementById("iter-total").textContent   = total;
  document.getElementById("stat-keep").textContent    = keep;
  document.getElementById("stat-discard").textContent = discard;
  document.getElementById("stat-crash").textContent   = crash;
  document.getElementById("stat-oos-rate").textContent = oosRate;
}

// ── Data refresh helpers ─────────────────────────────────
async function refreshExperiments() {
  const { experiments, best_commit } = await fetchExperiments();
  updateBestCard(experiments, best_commit);
  updateIterStats(experiments);
  updateCharts(experiments);
  renderTable(experiments, best_commit);
}

async function refreshRunlog() {
  const { lines } = await fetchRunlog();
  renderRunlog(lines);
}

async function refreshGitInfo() {
  const { current_branch } = await fetchGitInfo();
  document.getElementById("current-branch").textContent = current_branch || "—";
}

// ── Boot ─────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", async () => {
  initCharts();

  await Promise.all([
    refreshGitInfo(),
    refreshExperiments(),
    refreshRunlog(),
  ]);

  startSSE();

  window.addEventListener("experiments_updated", refreshExperiments);
  window.addEventListener("runlog_updated", refreshRunlog);
});

import { showDiff } from "./diff.js";

const tbody    = document.getElementById("exp-tbody");
const expCount = document.getElementById("exp-count");

// Always return "—" for null/undefined — never cast to 0
function fmt(val, decimals = 4) {
  if (val === null || val === undefined) return "—";
  return Number(val).toFixed(decimals);
}

function fmtPct(val) {
  if (val === null || val === undefined) return "—";
  return (Number(val) * 100).toFixed(2) + "%";
}

function statusBadge(status) {
  const cls = `badge badge-${status || "discard"}`;
  return `<span class="${cls}">${status || "?"}</span>`;
}

function oosBadge(oos_pass) {
  if (oos_pass === null || oos_pass === undefined) return "";
  return oos_pass
    ? `<span class="badge badge-keep" style="font-size:10px;margin-left:4px">OOS</span>`
    : `<span class="badge badge-discard" style="font-size:10px;margin-left:4px;opacity:0.6">OOS</span>`;
}

export function renderTable(experiments, bestCommit) {
  expCount.textContent = experiments.length;
  tbody.innerHTML = "";

  // Newest-first so the table reads like a live feed
  const rows = [...experiments].reverse();

  for (const exp of rows) {
    const tr = document.createElement("tr");
    if (exp.commit === bestCommit) tr.classList.add("best-row");

    // Flag keep rows that didn't pass OOS
    if (exp.status === "keep" && exp.oos_pass === false) {
      tr.classList.add("wf-fail");
    }

    tr.innerHTML = `
      <td><span class="commit-hash">${exp.commit.slice(0, 7)}</span></td>
      <td>${escapeHtml(exp.description)}</td>
      <td>${fmt(exp.score)}</td>
      <td>${fmt(exp.total_return)}</td>
      <td>${fmt(exp.max_drawdown)}</td>
      <td>${fmtPct(exp.win_rate)}</td>
      <td>${fmt(exp.trade_sharpe)}</td>
      <td>${exp.num_trades !== null ? exp.num_trades.toLocaleString() : "—"}</td>
      <td>${statusBadge(exp.status)}${oosBadge(exp.oos_pass)}</td>
    `;

    tr.addEventListener("click", () => showDiff(exp.commit));
    tbody.appendChild(tr);
  }
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

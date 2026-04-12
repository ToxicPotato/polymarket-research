const panel = document.getElementById("log-panel");

const METRIC_RE = /^(win_rate|roi|sharpe|num_trades):/;

export function renderRunlog(lines) {
  if (!lines || lines.length === 0) {
    panel.textContent = "No run output yet.";
    return;
  }

  panel.innerHTML = lines
    .map(line => {
      const safe = escapeHtml(line);
      return METRIC_RE.test(line)
        ? `<span class="log-metric">${safe}</span>`
        : safe;
    })
    .join("\n");

  // Scroll to bottom so the latest output is visible
  panel.scrollTop = panel.scrollHeight;
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

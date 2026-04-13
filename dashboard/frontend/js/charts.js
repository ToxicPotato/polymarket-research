const STATUS_COLORS = {
  keep:    "#3fb950",
  discard: "#8b949e",
  crash:   "#f85149",
};

const CHART_DEFAULTS = {
  responsive: true,
  animation: false,
  plugins: { legend: { display: false } },
  scales: {
    x: {
      ticks: { color: "#8b949e", font: { family: "monospace", size: 11 } },
      grid:  { color: "#21262d" },
    },
    y: {
      ticks: { color: "#8b949e", font: { size: 11 } },
      grid:  { color: "#21262d" },
    },
  },
};

function makeDataset(label, color) {
  return {
    label,
    data: [],
    borderColor: color,
    borderWidth: 2,
    pointBackgroundColor: [],
    pointRadius: 5,
    pointHoverRadius: 7,
    tension: 0.3,
    fill: false,
  };
}

let chartRoi, chartWinrate, chartSharpe, chartOverview;
let chartWinrateTime, chartTradeSharpe, chartNumTrades;

export function initCharts() {
  const cfg = (id, label, color) => ({
    type: "line",
    data: { labels: [], datasets: [makeDataset(label, color)] },
    options: CHART_DEFAULTS,
  });

  chartRoi          = new Chart(document.getElementById("chart-roi"),           cfg("chart-roi",           "Score",        "#58a6ff"));
  chartWinrate      = new Chart(document.getElementById("chart-winrate"),       cfg("chart-winrate",       "Total Return", "#bc8cff"));
  chartSharpe       = new Chart(document.getElementById("chart-sharpe"),        cfg("chart-sharpe",        "Max Drawdown", "#ffa657"));
  chartWinrateTime  = new Chart(document.getElementById("chart-winrate-time"),  cfg("chart-winrate-time",  "Win Rate",     "#3fb950"));
  chartTradeSharpe  = new Chart(document.getElementById("chart-trade-sharpe"),  cfg("chart-trade-sharpe",  "Trade Sharpe", "#f0883e"));
  chartNumTrades    = new Chart(document.getElementById("chart-num-trades"),    cfg("chart-num-trades",    "Num Trades",   "#a371f7"));

  chartOverview = new Chart(document.getElementById("chart-overview"), {
    type: "scatter",
    data: { datasets: [] },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: {
        legend: {
          display: true,
          labels: { color: "#8b949e", boxWidth: 10, font: { size: 11 } },
        },
        tooltip: {
          callbacks: {
            label: ctx => {
              const p = ctx.raw;
              const desc = p.description ? ` — ${p.description.slice(0, 40)}` : "";
              return `#${p.x} ${p.commit}${desc}  score=${p.y.toFixed(4)}`;
            },
          },
        },
      },
      scales: {
        x: {
          type: "linear",
          ticks: {
            color: "#8b949e",
            font: { family: "monospace", size: 11 },
            stepSize: 1,
            callback: v => Number.isInteger(v) ? `#${v}` : "",
          },
          grid: { color: "#21262d" },
        },
        y: {
          title: { display: true, text: "Score", color: "#8b949e", font: { size: 11 } },
          ticks: { color: "#8b949e", font: { size: 11 } },
          grid: {
            color: ctx => ctx.tick.value === 0 ? "#58a6ff" : "#21262d",
          },
        },
      },
    },
  });
}

export function updateCharts(experiments) {
  const valid = experiments.filter(e => e.score !== null || e.total_return !== null);

  const labels = valid.map((_, i) => `#${i + 1}`);
  const colors = valid.map(e => STATUS_COLORS[e.status] ?? "#8b949e");

  function applyTo(chart, values) {
    chart.data.labels = labels;
    chart.data.datasets[0].data              = values;
    chart.data.datasets[0].pointBackgroundColor = colors;
    chart.update();
  }

  applyTo(chartRoi,         valid.map(e => e.score));
  applyTo(chartWinrate,     valid.map(e => e.total_return));
  applyTo(chartSharpe,      valid.map(e => e.max_drawdown));
  applyTo(chartWinrateTime, valid.map(e => e.win_rate));
  applyTo(chartTradeSharpe, valid.map(e => e.trade_sharpe));
  applyTo(chartNumTrades,   valid.map(e => e.num_trades));

  // Overview — score over time, keep experiments connected by a line
  // Use original index so X = true iteration number even with gaps
  const groups = { keep: [], discard: [], crash: [] };
  experiments.forEach((e, i) => {
    if (e.score === null) return;
    const grp = groups[e.status] ?? groups.discard;
    grp.push({ x: i + 1, y: e.score, commit: e.commit?.slice(0, 7) ?? "?", description: e.description });
  });

  chartOverview.data.datasets = [
    {
      label: "keep",
      data: groups.keep,
      backgroundColor: "#3fb950",
      borderColor: "rgba(63,185,80,0.5)",
      borderWidth: 1.5,
      pointRadius: 6,
      pointHoverRadius: 8,
      showLine: true,
      tension: 0.1,
    },
    {
      label: "discard",
      data: groups.discard,
      backgroundColor: "#8b949e",
      pointRadius: 4,
      pointHoverRadius: 6,
      showLine: false,
    },
    {
      label: "crash",
      data: groups.crash,
      backgroundColor: "#f85149",
      pointRadius: 4,
      pointHoverRadius: 6,
      showLine: false,
    },
  ];
  chartOverview.update();
}

import { fetchDiff } from "./api.js";

const panel       = document.getElementById("diff-panel");
const viewer      = document.getElementById("diff-viewer");
const commitLabel = document.getElementById("diff-commit-label");
const closeBtn    = document.getElementById("diff-close");

closeBtn.addEventListener("click", hideDiff);

export async function showDiff(commit) {
  commitLabel.textContent = commit.slice(0, 7);
  viewer.innerHTML = "<span style='color:var(--text-muted)'>Loading…</span>";
  panel.classList.remove("hidden");
  panel.scrollIntoView({ behavior: "smooth", block: "nearest" });

  const data = await fetchDiff(commit);
  renderDiff(data.diff || "");
}

export function hideDiff() {
  panel.classList.add("hidden");
}

function renderDiff(diffText) {
  if (!diffText.trim()) {
    viewer.innerHTML = "<span style='color:var(--text-muted)'>No diff available.</span>";
    return;
  }

  viewer.innerHTML = diffText
    .split("\n")
    .map(line => {
      const safe = escapeHtml(line);
      if (line.startsWith("+++") || line.startsWith("---")) {
        return `<span class="diff-neutral">${safe}</span>`;
      }
      if (line.startsWith("+"))  return `<span class="diff-add">${safe}</span>`;
      if (line.startsWith("-"))  return `<span class="diff-remove">${safe}</span>`;
      if (line.startsWith("@@")) return `<span class="diff-meta">${safe}</span>`;
      return `<span class="diff-neutral">${safe}</span>`;
    })
    .join("");
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

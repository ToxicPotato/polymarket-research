export async function fetchExperiments() {
  const r = await fetch("/api/experiments");
  return r.json();
}

export async function fetchRunlog() {
  const r = await fetch("/api/runlog");
  return r.json();
}

export async function fetchGitInfo() {
  const r = await fetch("/api/git");
  return r.json();
}

export async function fetchDiff(commit) {
  const r = await fetch(`/api/git/diff/${encodeURIComponent(commit)}`);
  return r.json();
}

import re
import subprocess
from fastapi import APIRouter, HTTPException
from ..config import REPO_ROOT

router = APIRouter()

COMMIT_RE = re.compile(r"^[0-9a-f]{7,40}$")


def _git(*args) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=5,
    )
    return result.stdout.strip()


@router.get("/git")
def get_git_info():
    current_branch = _git("symbolic-ref", "--short", "HEAD")
    all_refs = _git("for-each-ref", "--format=%(refname:short)", "refs/heads/")
    research_branches = [b for b in all_refs.splitlines() if b.startswith("research/")]
    return {
        "current_branch": current_branch,
        "research_branches": research_branches,
    }


@router.get("/git/diff/{commit}")
def get_diff(commit: str):
    if not COMMIT_RE.match(commit):
        raise HTTPException(status_code=400, detail="Invalid commit hash")

    # Check whether the commit has a parent
    parent_check = subprocess.run(
        ["git", "rev-parse", f"{commit}^"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=5,
    )

    if parent_check.returncode == 0:
        diff = _git("diff", f"{commit}^", commit, "--", "backtest.py")
    else:
        diff = _git("show", commit, "--", "backtest.py")

    return {"commit": commit, "diff": diff}

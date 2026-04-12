from pathlib import Path
from fastapi import APIRouter
from ..config import REPO_ROOT

router = APIRouter()

# Prefer results_v2.tsv (new format) over results.tsv (legacy)
_TSV_V2   = "results_v2.tsv"
_TSV_V1   = "results.tsv"

# New column set
_V2_COLS = {"score", "total_return", "max_drawdown", "trade_sharpe", "oos_pass", "win_rate"}


def _safe_float(val) -> float | None:
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _safe_int(val) -> int | None:
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _safe_bool(val) -> bool | None:
    if val is None:
        return None
    s = str(val).strip().lower()
    if s == "true":
        return True
    if s == "false":
        return False
    return None


def _parse_tsv(path: Path) -> list[dict]:
    """Parse a results TSV file, guarding against partial last lines."""
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    if not lines:
        return []
    header = lines[0].strip().split("\t")
    rows = []
    for line in lines[1:]:
        parts = line.strip().split("\t")
        if len(parts) < len(header):
            continue  # skip partial writes
        rows.append(dict(zip(header, parts)))
    return rows, header


def _is_v2_header(header: list[str]) -> bool:
    return bool(_V2_COLS & set(header))


@router.get("/experiments")
def get_experiments():
    # Resolve which file to read
    path_v2 = REPO_ROOT / _TSV_V2
    path_v1 = REPO_ROOT / _TSV_V1

    if path_v2.exists():
        raw_rows, header = _parse_tsv(path_v2)
        is_v2 = True
    elif path_v1.exists():
        raw_rows, header = _parse_tsv(path_v1)
        is_v2 = _is_v2_header(header)
    else:
        return {"experiments": [], "best_commit": None, "format": "none"}

    experiments = []
    for row in raw_rows:
        if is_v2:
            exp = {
                "commit":        row.get("commit", ""),
                "score":         _safe_float(row.get("score")),
                "total_return":  _safe_float(row.get("total_return")),
                "max_drawdown":  _safe_float(row.get("max_drawdown")),
                "trade_sharpe":  _safe_float(row.get("trade_sharpe")),
                "win_rate":      _safe_float(row.get("win_rate")),
                "num_trades":    _safe_int(row.get("num_trades")),
                "oos_pass":      _safe_bool(row.get("oos_pass")),
                "status":        row.get("status", ""),
                "description":   row.get("description", ""),
                # Legacy fields set to None for consistent API shape
                "roi":    None,
                "sharpe": None,
            }
        else:
            # Legacy results.tsv — map old columns to new names where possible
            roi = _safe_float(row.get("roi"))
            exp = {
                "commit":        row.get("commit", ""),
                "score":         roi,          # best approximation available
                "total_return":  roi,
                "max_drawdown":  None,
                "trade_sharpe":  _safe_float(row.get("sharpe")),
                "num_trades":    _safe_int(row.get("num_trades")),
                "oos_pass":      None,
                "status":        row.get("status", ""),
                "description":   row.get("description", ""),
                # Preserve legacy fields for backwards compat
                "roi":       roi,
                "win_rate":  _safe_float(row.get("win_rate")),
                "sharpe":    _safe_float(row.get("sharpe")),
            }
        experiments.append(exp)

    # Best commit = highest score among keep rows (None scores sort last)
    best_commit = None
    best_score  = None
    for exp in experiments:
        if exp["status"] == "keep" and exp["score"] is not None:
            if best_score is None or exp["score"] > best_score:
                best_score  = exp["score"]
                best_commit = exp["commit"]

    return {
        "experiments":  experiments,
        "best_commit":  best_commit,
        "format":       "v2" if is_v2 else "v1",
    }

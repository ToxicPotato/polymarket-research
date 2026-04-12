from fastapi import APIRouter
from ..config import REPO_ROOT

router = APIRouter()


@router.get("/runlog")
def get_runlog():
    log_path = REPO_ROOT / "run.log"
    if not log_path.exists():
        return {"lines": []}

    with open(log_path, "rb") as f:
        raw = f.read()
    if raw[:2] in (b'\xff\xfe', b'\xfe\xff'):
        content = raw.decode("utf-16")
    else:
        content = raw.decode("utf-8", errors="replace")

    return {"lines": content.splitlines()}

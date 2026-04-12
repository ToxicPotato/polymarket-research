from pathlib import Path

# dashboard/api/config.py is at <repo>/dashboard/api/config.py
# so parent.parent.parent = <repo>
REPO_ROOT = Path(__file__).parent.parent.parent.resolve()
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

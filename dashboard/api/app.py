import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .config import REPO_ROOT, FRONTEND_DIR
from .watchers.file_watcher import start_watcher, stop_watcher
from .routes import experiments, runlog, git_info, stream


@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_event_loop()
    start_watcher(REPO_ROOT, loop)
    yield
    stop_watcher()


app = FastAPI(lifespan=lifespan)

app.include_router(experiments.router, prefix="/api")
app.include_router(runlog.router, prefix="/api")
app.include_router(git_info.router, prefix="/api")
app.include_router(stream.router, prefix="/api")

# Static files mount must come last — it catches everything not matched above
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

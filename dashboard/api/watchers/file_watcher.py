import asyncio
from pathlib import Path
from watchdog.observers.polling import PollingObserver
from watchdog.events import FileSystemEventHandler

_observer: PollingObserver | None = None
_loop: asyncio.AbstractEventLoop | None = None
_subscribers: list[asyncio.Queue] = []

WATCHED_FILES = {"results.tsv", "run.log"}


class _Handler(FileSystemEventHandler):
    def _handle(self, path: str):
        name = Path(path).name
        if name in ("results.tsv", "results_v2.tsv"):
            _broadcast({"type": "experiments_updated"})
        elif name == "run.log":
            _broadcast({"type": "runlog_updated"})

    def on_modified(self, event):
        if not event.is_directory:
            self._handle(event.src_path)

    def on_created(self, event):
        if not event.is_directory:
            self._handle(event.src_path)


def _broadcast(event: dict):
    if _loop is None:
        return
    for queue in list(_subscribers):
        _loop.call_soon_threadsafe(queue.put_nowait, event)


def subscribe() -> asyncio.Queue:
    queue: asyncio.Queue = asyncio.Queue()
    _subscribers.append(queue)
    return queue


def unsubscribe(queue: asyncio.Queue):
    try:
        _subscribers.remove(queue)
    except ValueError:
        pass


def start_watcher(repo_root: Path, loop: asyncio.AbstractEventLoop):
    global _observer, _loop
    _loop = loop
    # PollingObserver is more reliable on Windows for files written by external processes
    _observer = PollingObserver(timeout=1)
    _observer.schedule(_Handler(), str(repo_root), recursive=False)
    _observer.start()


def stop_watcher():
    global _observer
    if _observer:
        _observer.stop()
        _observer.join()
        _observer = None

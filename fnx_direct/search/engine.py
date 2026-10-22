"""
Starts the search engine (search/worker.py) in its own process and tracks its loading.
Loading torch / the embedding model inside the website process starved every page render,
so it runs separately; `client` forwards queries to it once `ready` is set.
"""
import atexit
import json
import os
import secrets
import subprocess
import sys
import threading
import time
from multiprocessing.connection import Listener

from fnx_direct.config import ROOT_DIR, WARMUP_TIMES_PATH
from fnx_direct.search.worker import AUTHKEY_ENV

ready = threading.Event()
failed = threading.Event()
_start_lock = threading.Lock()
_thread = None
started_at = None  # time.time() when loading began
client = None      # SearchClient, set when ready

# Loading has three stages; each ends at a real milestone (percent shown in the UI).
MILESTONE_IMPORTED = 45  # chromadb imported
MILESTONE_MODEL = 85     # embedding model loaded, collection opened
_STAGES = (("imported", MILESTONE_IMPORTED), ("model", MILESTONE_MODEL), ("ready", 100))
# The full-screen loading page is shown until here; the rest loads while the user logs in.
SPLASH_UNTIL_PERCENT = 50

# Learned duration of each stage (seconds), so progress moves smoothly on this machine.
_DEFAULT_DURATIONS = {"imported": 3.0, "model": 4.0, "ready": 1.0}
_stage = 0              # index into _STAGES of the stage in progress
_stage_started_at = None
_measured = {}


def _expected_durations():
    try:
        data = json.loads(WARMUP_TIMES_PATH.read_text(encoding="utf-8"))
        return {name: max(1.0, float(data[name])) for name, _ in _STAGES}
    except (OSError, ValueError, KeyError, TypeError):
        return dict(_DEFAULT_DURATIONS)


def _finish_stage():
    global _stage, _stage_started_at
    now = time.time()
    _measured[_STAGES[_stage][0]] = now - _stage_started_at
    _stage, _stage_started_at = _stage + 1, now


def progress():
    """Loading progress 0–100: smooth within a stage, never past a milestone not yet reached."""
    if ready.is_set():
        return 100
    if _stage_started_at is None:
        return 0
    name, stage_end = _STAGES[_stage]
    stage_start = _STAGES[_stage - 1][1] if _stage else 0
    fraction = (time.time() - _stage_started_at) / _expected_durations()[name]
    return int(min(stage_start + fraction * (stage_end - stage_start), stage_end - 1))


def snapshot():
    """State for the loading page's own (client-side) progress animation."""
    durations = _expected_durations()
    return {
        "stage": _stage,
        "stageElapsed": time.time() - _stage_started_at if _stage_started_at else 0,
        "durations": [durations[name] for name, _ in _STAGES],
        "milestones": [end for _, end in _STAGES],
        "cap": SPLASH_UNTIL_PERCENT - 1,
    }


class SearchClient:
    """Same interface the app used on the Chroma collection (query / count), served by the worker."""

    def __init__(self, conn, info):
        self._conn = conn
        self._lock = threading.Lock()  # one request at a time over the shared connection
        self._count = info["count"]
        self.topic_counts = info["topic_counts"]

    def count(self):
        return self._count

    def query(self, **kwargs):
        with self._lock:
            self._conn.send(("query", kwargs))
            status, payload = self._conn.recv()
        if status != "ok":
            raise RuntimeError(f"Search engine error: {payload}")
        return payload


def _save_measured_durations():
    if len(_measured) != len(_STAGES):
        return
    try:
        WARMUP_TIMES_PATH.parent.mkdir(parents=True, exist_ok=True)
        WARMUP_TIMES_PATH.write_text(json.dumps(_measured), encoding="utf-8")
    except OSError:
        pass


def _run():
    global client
    authkey = secrets.token_bytes(32)
    listener = Listener(("127.0.0.1", 0), authkey=authkey)
    worker = subprocess.Popen(
        [sys.executable, "-m", "fnx_direct.search.worker", str(listener.address[1])],
        cwd=ROOT_DIR,
        env={**os.environ, AUTHKEY_ENV: authkey.hex()},
    )
    atexit.register(worker.terminate)

    def watch_worker():
        # If the worker dies before connecting, unblock accept() instead of waiting forever.
        code = worker.wait()
        if not ready.is_set():
            # -9 (SIGKILL) usually means the server ran out of memory.
            print(f"Search worker exited before it was ready (exit code {code})", flush=True)
            failed.set()
            listener.close()

    threading.Thread(target=watch_worker, name="search-worker-watch", daemon=True).start()
    try:
        conn = listener.accept()
        while True:
            kind, payload = conn.recv()
            if kind == "stage":
                _finish_stage()
            elif kind == "ready":
                _finish_stage()
                client = SearchClient(conn, payload)
                ready.set()
                break
            else:
                raise RuntimeError(payload)
        _save_measured_durations()
        print("מודל החיפוש נטען ומוכן.", flush=True)
    except Exception as error:
        failed.set()
        print(f"Search engine failed to start: {type(error).__name__}: {error}", flush=True)
    finally:
        listener.close()


def start():
    """Starts loading in the background (only once per process)."""
    global _thread, started_at, _stage_started_at
    with _start_lock:
        if _thread is None:
            started_at = _stage_started_at = time.time()
            _thread = threading.Thread(target=_run, name="search-model-warmup", daemon=True)
            _thread.start()


def is_ready():
    return ready.is_set()


def has_failed():
    return failed.is_set()


def wait_until_ready():
    """Blocks until the search engine is loaded; returns the client (raises if loading failed)."""
    start()
    while not ready.wait(0.5):
        if failed.is_set():
            raise RuntimeError("מנוע החיפוש לא נטען. נסו להפעיל מחדש את השרת.")
    return client

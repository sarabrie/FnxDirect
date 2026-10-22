import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException, Request

# Per-route limits: (max_requests, window_seconds)
_LIMITS: dict[str, tuple[int, int]] = {
    "/auth/login":   (10, 60),
    "/auth/signup":  (5,  60),
    "/auth/refresh": (20, 60),
}

_store: dict[str, deque] = defaultdict(deque)
_lock = Lock()


def rate_limit(request: Request) -> None:
    path = request.url.path
    limit = _LIMITS.get(path)
    if limit is None:
        return

    max_req, window = limit
    # Use forwarded IP if behind a trusted proxy; fall back to direct client
    client_ip = request.headers.get("X-Forwarded-For", request.client.host).split(",")[0].strip()
    key = f"{path}:{client_ip}"
    now = time.monotonic()

    with _lock:
        dq = _store[key]
        while dq and dq[0] <= now - window:
            dq.popleft()
        if len(dq) >= max_req:
            raise HTTPException(status_code=429, detail="Too many requests. Please slow down.")
        dq.append(now)

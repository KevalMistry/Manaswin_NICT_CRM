"""Small in-memory sliding-window rate limiter for abuse-prone public endpoints.

Per-process only: with several worker processes each keeps its own counters, so the
effective limit is limit x workers. That is still a useful brake on password
guessing; use a gateway/Redis limiter if you need strict global limits.
"""
import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException, Request, status

from app.core.config import TRUST_PROXY_HEADERS

_hits: dict[str, deque[float]] = defaultdict(deque)
_lock = Lock()


def _client_ip(request: Request) -> str:
    if TRUST_PROXY_HEADERS:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(name: str, limit: int, window_seconds: int):
    def dependency(request: Request) -> None:
        key = f"{name}:{_client_ip(request)}"
        now = time.monotonic()
        with _lock:
            bucket = _hits[key]
            while bucket and now - bucket[0] > window_seconds:
                bucket.popleft()
            if len(bucket) >= limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many attempts. Please wait a few minutes and try again.",
                    headers={"Retry-After": str(window_seconds)},
                )
            bucket.append(now)
    return dependency

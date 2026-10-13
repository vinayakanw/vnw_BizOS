"""Small in-memory sliding-window rate limiter.

Fine for one API process. With several instances each keeps its own counts (limits become per instance),
so move this to Redis if you scale out. State is lost on restart, which is acceptable for abuse protection.
"""

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

from app.core.config import settings

_hits: dict[str, deque] = defaultdict(deque)
_lock = threading.Lock()


def reset() -> None:
    with _lock:
        _hits.clear()


def client_ip(request: Request) -> str:
    if settings.trust_forwarded_for:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def hit(key: str, limit: int, window: int) -> int | None:
    """Record a hit. Returns seconds to wait when over the limit, otherwise None."""
    now = time.monotonic()
    with _lock:
        q = _hits[key]
        while q and now - q[0] >= window:
            q.popleft()
        if len(q) >= limit:
            return max(1, int(window - (now - q[0])) + 1)
        q.append(now)
        return None


def _deny(wait: int) -> HTTPException:
    return HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, f"Too many requests. Try again in {wait} seconds.", headers={"Retry-After": str(wait)})


def by_ip(name: str, limit: int, window: int):
    def dep(request: Request) -> None:
        if not settings.rate_limit_enabled:
            return
        wait = hit(f"{name}:ip:{client_ip(request)}", limit, window)
        if wait:
            raise _deny(wait)

    return dep


def by_org(name: str, limit: int, window: int):
    """Per tenant, for endpoints that cost money (LLM calls). Needs the org resolved first, so it reads the auth dependency."""
    from app.api.deps import AuthContext, get_auth
    from fastapi import Depends

    def dep(auth: AuthContext = Depends(get_auth)) -> None:
        if not settings.rate_limit_enabled:
            return
        wait = hit(f"{name}:org:{auth.org_id}", limit, window)
        if wait:
            raise _deny(wait)

    return dep

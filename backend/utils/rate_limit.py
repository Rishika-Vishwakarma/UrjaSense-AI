"""Simple in-memory sliding-window rate limiter.

Fine for a single process / demo. In AWS, put Amazon API Gateway throttling
(usage plans) in front and/or move this to Redis (ElastiCache).
"""
import threading
import time
from collections import defaultdict, deque
from functools import wraps

from flask import current_app, g, jsonify, request

_hits: dict = defaultdict(deque)
_lock = threading.Lock()


def reset():
    with _lock:
        _hits.clear()


def rate_limit(limit: int, window_seconds: int, scope: str = "ip"):
    """scope 'ip' keys by client IP, 'user' keys by authenticated user id."""
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if not current_app.config.get("RATE_LIMIT_ENABLED", True):
                return fn(*a, **kw)
            ident = request.remote_addr
            if scope == "user" and getattr(g, "user", None):
                ident = f"u{g.user['id']}"
            key = (fn.__name__, ident)
            now = time.time()
            with _lock:
                q = _hits[key]
                while q and q[0] <= now - window_seconds:
                    q.popleft()
                if len(q) >= limit:
                    retry = int(window_seconds - (now - q[0])) + 1
                    resp = jsonify(error="Too many requests. Please slow down.", retry_after_seconds=retry)
                    resp.status_code = 429
                    resp.headers["Retry-After"] = str(retry)
                    return resp
                q.append(now)
            return fn(*a, **kw)
        return wrapper
    return deco

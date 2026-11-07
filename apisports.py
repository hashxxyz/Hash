"""Shared rate limiter for API-Sports calls (football + basketball use the same key and the same per-minute limit).

Free plans allow about 10 requests per minute across both sports. Calls are spaced out in-process; if the limit would
make a call wait longer than max_wait seconds, it is skipped (the scan reports it and the cache fills in on the next scan).
"""
import os
import threading
import time

_LOCK = threading.Lock()
_CALLS = []


def _limit():
    try:
        return max(1, int(os.environ.get("APS_PER_MINUTE", "9")))
    except ValueError:
        return 9


def acquire(max_wait=12.0):
    deadline = time.time() + max_wait
    while True:
        with _LOCK:
            now = time.time()
            _CALLS[:] = [t for t in _CALLS if now - t < 60]
            if len(_CALLS) < _limit():
                _CALLS.append(now)
                return
            wait = 60 - (now - _CALLS[0]) + 0.2
        if time.time() + wait > deadline:
            raise RuntimeError("API-Sports per-minute limit reached (free plan: 10 requests/minute for football + basketball)")
        time.sleep(wait)

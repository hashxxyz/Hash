"""Small key-value store shared by the cache and the duplicate-update guard.

If UPSTASH_REDIS_REST_URL / UPSTASH_REDIS_REST_TOKEN (or Vercel KV's KV_REST_API_URL /
KV_REST_API_TOKEN) are set, data lives in Redis and survives Vercel cold starts and is shared
between instances. Otherwise it falls back to in-memory storage (best-effort on serverless).
"""
import json
import os
import time

import requests

_MEM = {}  # key -> (expires_at, value)


def _redis_cfg():
    url = os.environ.get("UPSTASH_REDIS_REST_URL") or os.environ.get("KV_REST_API_URL")
    token = os.environ.get("UPSTASH_REDIS_REST_TOKEN") or os.environ.get("KV_REST_API_TOKEN")
    return (url.rstrip("/"), token) if url and token else (None, None)


def _redis(*command):
    url, token = _redis_cfg()
    r = requests.post(url, headers={"Authorization": f"Bearer {token}"}, json=list(command), timeout=5)
    r.raise_for_status()
    return r.json().get("result")


def _mem_get(key):
    hit = _MEM.get(key)
    if hit and hit[0] > time.time():
        return hit[1]
    _MEM.pop(key, None)
    return None


def get_json(key):
    if _redis_cfg()[0]:
        try:
            raw = _redis("GET", key)
            return json.loads(raw) if raw else None
        except Exception as e:
            print("STORE GET ERROR:", type(e).__name__)
    return _mem_get(key)


def set_json(key, value, ttl):
    _MEM[key] = (time.time() + ttl, value)
    if _redis_cfg()[0]:
        try:
            _redis("SET", key, json.dumps(value), "EX", int(ttl))
        except Exception as e:
            print("STORE SET ERROR:", type(e).__name__)


def claim(key, ttl):
    """True the first time a key is claimed within ttl seconds, False afterwards."""
    if _redis_cfg()[0]:
        try:
            return _redis("SET", key, "1", "NX", "EX", int(ttl)) == "OK"
        except Exception as e:
            print("STORE CLAIM ERROR:", type(e).__name__)
    if _mem_get(key):
        return False
    _MEM[key] = (time.time() + ttl, "1")
    return True

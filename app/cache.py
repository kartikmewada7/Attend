"""Redis-backed cache with JSON serialization and in-memory fallback."""
from __future__ import annotations

import fnmatch
import json
import logging
import threading
import time
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.redis_client import get_redis

logger = logging.getLogger(__name__)


class _JSONEncoder(json.JSONEncoder):
    def default(self, o: object) -> object:
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        if isinstance(o, (Decimal, UUID)):
            return str(o)
        return super().default(o)


class _MemoryCache:
    """Thread-safe in-memory TTL cache used as fallback."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[Any, float]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if expires_at and time.time() > expires_at:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: Any, ttl: int = 300) -> None:
        with self._lock:
            expires_at = time.time() + ttl if ttl > 0 else 0
            self._store[key] = (value, expires_at)

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def delete_pattern(self, pattern: str) -> int:
        with self._lock:
            to_del = [k for k in self._store if fnmatch.fnmatch(k, pattern)]
            for k in to_del:
                del self._store[k]
            return len(to_del)

    def exists(self, key: str) -> bool:
        return self.get(key) is not None

    def incr(self, key: str, ttl: int = 60) -> int:
        with self._lock:
            entry = self._store.get(key)
            if entry is None or (entry[1] and time.time() > entry[1]):
                self._store[key] = (1, time.time() + ttl)
                return 1
            val = entry[0] + 1
            self._store[key] = (val, entry[1])
            return val


class Cache:
    """High-performance Redis cache with automatic in-memory fallback."""

    def __init__(self) -> None:
        self._mem = _MemoryCache()
        self._r = get_redis()

    @staticmethod
    def _ser(value: Any) -> str:
        return json.dumps(value, cls=_JSONEncoder)

    @staticmethod
    def _de(raw: str | None) -> Any | None:
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return raw

    def get(self, key: str) -> Any | None:
        try:
            return self._de(self._r.get(key))
        except Exception:
            return self._mem.get(key)

    def set(self, key: str, value: Any, ttl: int = 300) -> bool:
        self._mem.set(key, value, ttl=ttl)
        try:
            return bool(self._r.set(key, self._ser(value), ex=ttl if ttl > 0 else None))
        except Exception:
            return True

    def delete(self, key: str) -> bool:
        self._mem.delete(key)
        try:
            return bool(self._r.delete(key))
        except Exception:
            return True

    def delete_pattern(self, pattern: str) -> int:
        self._mem.delete_pattern(pattern)
        count = 0
        try:
            keys = []
            for key in self._r.scan_iter(match=pattern, count=200):
                keys.append(key)
                if len(keys) >= 200:
                    self._r.delete(*keys)
                    count += len(keys)
                    keys.clear()
            if keys:
                self._r.delete(*keys)
                count += len(keys)
        except Exception as exc:
            logger.debug("delete_pattern(%s) error: %s", pattern, exc)
        return count

    def exists(self, key: str) -> bool:
        try:
            return bool(self._r.exists(key))
        except Exception:
            return self._mem.exists(key)

    def incr(self, key: str, ttl: int = 60) -> int:
        try:
            val = self._r.incr(key)
            if ttl > 0:
                self._r.expire(key, ttl)
            return int(val)
        except Exception:
            return self._mem.incr(key, ttl=ttl)


cache = Cache()

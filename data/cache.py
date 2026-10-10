"""
Disk-based cache with TTL using diskcache.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import diskcache

from config.settings import settings

logger = logging.getLogger(__name__)


class CacheManager:
    """Simple disk cache with per-key TTL."""

    _instance: Optional["CacheManager"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._cache = diskcache.Cache(str(settings.CACHE_DIR))
        return cls._instance

    def get(self, key: str) -> Optional[Any]:
        try:
            return self._cache.get(key)
        except Exception as exc:
            logger.debug("Cache get error: %s", exc)
            return None

    def set(self, key: str, value: Any, ttl: int = 300):
        try:
            self._cache.set(key, value, expire=ttl)
        except Exception as exc:
            logger.debug("Cache set error: %s", exc)

    def delete(self, key: str):
        try:
            self._cache.delete(key)
        except Exception:
            pass

    def clear_prefix(self, prefix: str):
        try:
            for key in list(self._cache):
                if isinstance(key, str) and key.startswith(prefix):
                    self._cache.delete(key)
        except Exception as exc:
            logger.debug("Cache clear prefix error: %s", exc)

    def clear_all(self):
        try:
            self._cache.clear()
        except Exception:
            pass

    def stats(self) -> dict:
        try:
            return {
                "size": len(self._cache),
                "directory": str(settings.CACHE_DIR),
            }
        except Exception:
            return {}


cache = CacheManager()

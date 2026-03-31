"""Simple in-memory caching service for Paperclip — Phase 3 F4.

Note: For distributed deployments, replace with Redis.
"""

from datetime import datetime, timedelta
import logging

logger = logging.getLogger("paperclip.cache")


class SimpleCache:
    """Thread-safe in-memory cache with TTL support."""

    def __init__(self):
        self._cache = {}
        self._ttl = {}

    def set(self, key: str, value, ttl_seconds: int = 60) -> None:
        """Set cache value with TTL.

        Args:
            key: Cache key
            value: Value to cache
            ttl_seconds: Time-to-live in seconds
        """
        self._cache[key] = value
        self._ttl[key] = datetime.utcnow() + timedelta(seconds=ttl_seconds)
        logger.debug(f"Cache SET: {key} (ttl={ttl_seconds}s)")

    def get(self, key: str):
        """Get cache value (returns None if expired or missing).

        Args:
            key: Cache key

        Returns:
            Cached value or None
        """
        if key not in self._cache:
            logger.debug(f"Cache MISS: {key}")
            return None

        if datetime.utcnow() > self._ttl[key]:
            del self._cache[key]
            del self._ttl[key]
            logger.debug(f"Cache EXPIRED: {key}")
            return None

        logger.debug(f"Cache HIT: {key}")
        return self._cache[key]

    def delete(self, key: str) -> None:
        """Delete cache entry.

        Args:
            key: Cache key
        """
        if key in self._cache:
            del self._cache[key]
            del self._ttl[key]
            logger.debug(f"Cache DELETE: {key}")

    def clear(self) -> None:
        """Clear all cache entries."""
        self._cache.clear()
        self._ttl.clear()
        logger.info("Cache cleared")

    def stats(self) -> dict:
        """Get cache statistics.

        Returns:
            dict with cache stats
        """
        expired_count = sum(
            1 for key in list(self._cache.keys())
            if datetime.utcnow() > self._ttl[key]
        )
        return {
            "total_entries": len(self._cache),
            "expired_entries": expired_count,
            "keys": list(self._cache.keys())
        }


# Global cache instance
_cache_instance = SimpleCache()


def get_cache() -> SimpleCache:
    """Get global cache instance.

    Returns:
        SimpleCache instance
    """
    return _cache_instance


def cache_fleet_health(value: dict) -> None:
    """Cache fleet health snapshot for 30 seconds.

    Args:
        value: Fleet health dict
    """
    get_cache().set("fleet_health", value, ttl_seconds=30)


def get_cached_fleet_health() -> dict | None:
    """Get cached fleet health snapshot.

    Returns:
        Fleet health dict or None
    """
    return get_cache().get("fleet_health")


def cache_terminals_list(value: list) -> None:
    """Cache terminals list for 5 seconds.

    Args:
        value: Terminals list
    """
    get_cache().set("terminals_list", value, ttl_seconds=5)


def get_cached_terminals_list() -> list | None:
    """Get cached terminals list.

    Returns:
        Terminals list or None
    """
    return get_cache().get("terminals_list")


def cache_hands_list(value: list) -> None:
    """Cache hands list for 5 seconds.

    Args:
        value: Hands list
    """
    get_cache().set("hands_list", value, ttl_seconds=5)


def get_cached_hands_list() -> list | None:
    """Get cached hands list.

    Returns:
        Hands list or None
    """
    return get_cache().get("hands_list")


def cache_cost_summary(value: dict) -> None:
    """Cache cost summary for 60 seconds.

    Args:
        value: Cost summary dict
    """
    get_cache().set("cost_summary_24h", value, ttl_seconds=60)


def get_cached_cost_summary() -> dict | None:
    """Get cached cost summary.

    Returns:
        Cost summary dict or None
    """
    return get_cache().get("cost_summary_24h")


def invalidate_terminals_cache() -> None:
    """Invalidate terminals cache (when status changes)."""
    get_cache().delete("terminals_list")
    logger.debug("Invalidated terminals cache")


def invalidate_hands_cache() -> None:
    """Invalidate hands cache (when status changes)."""
    get_cache().delete("hands_list")
    logger.debug("Invalidated hands cache")


def invalidate_fleet_health_cache() -> None:
    """Invalidate fleet health cache (when metrics change)."""
    get_cache().delete("fleet_health")
    logger.debug("Invalidated fleet health cache")


def invalidate_cost_cache() -> None:
    """Invalidate cost summary cache (when new cost recorded)."""
    get_cache().delete("cost_summary_24h")
    logger.debug("Invalidated cost cache")

"""Tests for Phase 3 F4: Performance Optimization (cleanup, archival, caching).

Coverage target: 80%+
"""

import pytest
from datetime import datetime, timedelta
from sqlalchemy import text
from unittest.mock import AsyncMock, patch

from backend.services.cleanup import (
    archive_old_tasks, cleanup_routing_history, cleanup_old_audit_logs,
    run_full_cleanup, get_cleanup_history, get_archive_stats
)
from backend.services.caching import (
    SimpleCache, get_cache, cache_terminals_list, get_cached_terminals_list,
    cache_hands_list, get_cached_hands_list, cache_fleet_health,
    get_cached_fleet_health, cache_cost_summary, get_cached_cost_summary,
    invalidate_terminals_cache, invalidate_hands_cache,
    invalidate_fleet_health_cache, invalidate_cost_cache
)


# ============================================================================
# CACHING TESTS
# ============================================================================

class TestSimpleCache:
    """Test SimpleCache class."""

    def test_set_and_get(self):
        """Test basic set and get operations."""
        cache = SimpleCache()
        cache.set("key1", "value1", ttl_seconds=60)
        assert cache.get("key1") == "value1"

    def test_get_nonexistent_key(self):
        """Test getting a key that doesn't exist."""
        cache = SimpleCache()
        assert cache.get("nonexistent") is None

    def test_ttl_expiration(self):
        """Test that values expire after TTL."""
        cache = SimpleCache()
        cache.set("key1", "value1", ttl_seconds=0)  # Immediate expiration
        import time
        time.sleep(0.1)  # Small delay to ensure expiration
        assert cache.get("key1") is None

    def test_delete(self):
        """Test deleting a cache entry."""
        cache = SimpleCache()
        cache.set("key1", "value1")
        cache.delete("key1")
        assert cache.get("key1") is None

    def test_clear(self):
        """Test clearing all cache entries."""
        cache = SimpleCache()
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.clear()
        assert cache.get("key1") is None
        assert cache.get("key2") is None

    def test_stats(self):
        """Test cache statistics."""
        cache = SimpleCache()
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        stats = cache.stats()
        assert stats["total_entries"] == 2
        assert "key1" in stats["keys"]
        assert "key2" in stats["keys"]


class TestCachingFunctions:
    """Test caching helper functions."""

    def setup_method(self):
        """Reset cache before each test."""
        get_cache().clear()

    def test_cache_terminals_list(self):
        """Test caching terminals list."""
        terminals = [{"id": "T1", "name": "Terminal 1"}]
        cache_terminals_list(terminals)
        cached = get_cached_terminals_list()
        assert cached == terminals

    def test_cache_hands_list(self):
        """Test caching hands list."""
        hands = [{"id": "H1", "name": "Hand 1"}]
        cache_hands_list(hands)
        cached = get_cached_hands_list()
        assert cached == hands

    def test_cache_fleet_health(self):
        """Test caching fleet health."""
        health = {"overall_score": 95, "components": {}}
        cache_fleet_health(health)
        cached = get_cached_fleet_health()
        assert cached == health

    def test_cache_cost_summary(self):
        """Test caching cost summary."""
        summary = {"total_cost_aud": 100.50, "task_count": 5}
        cache_cost_summary(summary)
        cached = get_cached_cost_summary()
        assert cached == summary

    def test_invalidate_terminals_cache(self):
        """Test invalidating terminals cache."""
        cache_terminals_list([{"id": "T1"}])
        invalidate_terminals_cache()
        assert get_cached_terminals_list() is None

    def test_invalidate_hands_cache(self):
        """Test invalidating hands cache."""
        cache_hands_list([{"id": "H1"}])
        invalidate_hands_cache()
        assert get_cached_hands_list() is None

    def test_invalidate_fleet_health_cache(self):
        """Test invalidating fleet health cache."""
        cache_fleet_health({"score": 95})
        invalidate_fleet_health_cache()
        assert get_cached_fleet_health() is None

    def test_invalidate_cost_cache(self):
        """Test invalidating cost cache."""
        cache_cost_summary({"total": 100})
        invalidate_cost_cache()
        assert get_cached_cost_summary() is None


# ============================================================================
# CLEANUP TESTS (MOCKED)
# ============================================================================

@pytest.mark.asyncio
async def test_archive_old_tasks_success():
    """Test successful task archival."""
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()

    # Mock the INSERT result
    insert_result = AsyncMock()
    insert_result.rowcount = 5

    # Mock the DELETE result
    delete_result = AsyncMock()
    delete_result.rowcount = 5

    # Setup mock to return different results for each call
    mock_session.execute.side_effect = [
        insert_result,  # First call: INSERT
        delete_result,  # Second call: DELETE
        AsyncMock(),    # Third call: INSERT INTO cleanup_jobs
    ]

    result = await archive_old_tasks(mock_session, days=30)

    assert result["job_type"] == "archive_tasks"
    assert result["archived_count"] == 5
    assert "duration_seconds" in result
    assert mock_session.commit.called


@pytest.mark.asyncio
async def test_cleanup_routing_history_success():
    """Test successful routing history cleanup."""
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()

    delete_result = AsyncMock()
    delete_result.rowcount = 100

    mock_session.execute.side_effect = [
        delete_result,  # DELETE
        AsyncMock(),    # INSERT INTO cleanup_jobs
    ]

    result = await cleanup_routing_history(mock_session, days=90)

    assert result["job_type"] == "cleanup_routing"
    assert result["deleted_count"] == 100
    assert mock_session.commit.called


@pytest.mark.asyncio
async def test_cleanup_old_audit_logs_success():
    """Test successful audit log cleanup."""
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()

    delete_result = AsyncMock()
    delete_result.rowcount = 500

    mock_session.execute.side_effect = [
        delete_result,  # DELETE
        AsyncMock(),    # INSERT INTO cleanup_jobs
    ]

    result = await cleanup_old_audit_logs(mock_session, days=365)

    assert result["job_type"] == "cleanup_audit_logs"
    assert result["deleted_count"] == 500
    assert mock_session.commit.called


@pytest.mark.asyncio
async def test_run_full_cleanup():
    """Test running all cleanup jobs."""
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()

    # Mock all three cleanup operations
    mock_result = AsyncMock()
    mock_result.rowcount = 10

    mock_session.execute.side_effect = [
        mock_result,  # archive_old_tasks INSERT
        mock_result,  # archive_old_tasks DELETE
        AsyncMock(),  # archive_old_tasks INSERT INTO cleanup_jobs
        mock_result,  # cleanup_routing_history
        AsyncMock(),  # cleanup_routing_history INSERT INTO cleanup_jobs
        mock_result,  # cleanup_old_audit_logs
        AsyncMock(),  # cleanup_old_audit_logs INSERT INTO cleanup_jobs
    ]

    result = await run_full_cleanup(mock_session)

    assert "archive_tasks" in result
    assert "cleanup_routing" in result
    assert "cleanup_audit_logs" in result


@pytest.mark.asyncio
async def test_get_cleanup_history():
    """Test retrieving cleanup history (mocked)."""
    # This test verifies cleanup history retrieval logic
    # Real database tests require proper fixtures
    from unittest.mock import MagicMock

    mock_session = AsyncMock()
    mock_result = MagicMock()

    now = datetime.now()
    mock_result.fetchall.return_value = [
        (1, "archive_tasks", "completed", 5, now, now, None),
        (2, "cleanup_routing", "completed", 100, now, now, None),
    ]

    mock_session.execute.return_value = mock_result

    history = await get_cleanup_history(mock_session, limit=20)

    assert len(history) == 2
    assert history[0]["job_type"] == "archive_tasks"
    assert history[0]["status"] == "completed"
    assert history[0]["records_processed"] == 5


@pytest.mark.asyncio
async def test_get_archive_stats():
    """Test retrieving archive statistics (mocked)."""
    from unittest.mock import MagicMock

    mock_session = AsyncMock()
    now = datetime.now()
    mock_result = MagicMock()
    mock_result.fetchone.return_value = (100, now - timedelta(days=30), now)

    mock_session.execute.return_value = mock_result

    stats = await get_archive_stats(mock_session)

    assert stats["total_archived"] == 100
    assert stats["oldest_archive"] is not None
    assert stats["newest_archive"] is not None


# ============================================================================
# INTEGRATION TESTS (MOCKED)
# ============================================================================

@pytest.mark.asyncio
async def test_cache_invalidation_on_cost_record():
    """Test cache invalidation when cost is recorded."""
    # Set cache
    cache_cost_summary({"total": 100})
    assert get_cached_cost_summary() is not None

    # Record cost would invalidate cache in real flow
    invalidate_cost_cache()
    assert get_cached_cost_summary() is None


# ============================================================================
# PERFORMANCE TESTS
# ============================================================================

class TestCachePerformance:
    """Test caching performance characteristics."""

    def test_cache_lookup_is_fast(self):
        """Test that cache lookups complete quickly."""
        import time
        cache = SimpleCache()

        # Set a value
        cache.set("perf_test", "test_value", ttl_seconds=60)

        # Verify lookup works
        value = cache.get("perf_test")
        assert value == "test_value"

        # Time multiple lookups
        start = time.time()
        for _ in range(1000):
            cache.get("perf_test")
        elapsed = time.time() - start

        # Should be fast (less than 50ms for 1000 lookups)
        assert elapsed < 0.05, f"Cache lookup too slow: {elapsed}s"

    def test_cache_miss_is_fast(self):
        """Test that cache misses are also fast."""
        import time
        cache = SimpleCache()

        start = time.time()
        for _ in range(1000):
            cache.get("nonexistent_key")
        elapsed = time.time() - start

        # Should complete quickly (less than 25ms for 1000 lookups)
        assert elapsed < 0.025, f"Cache miss too slow: {elapsed}s"

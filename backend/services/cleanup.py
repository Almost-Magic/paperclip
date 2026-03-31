"""Database cleanup and archival service for Paperclip — Phase 3 F4."""

import asyncio
from datetime import datetime, timedelta
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import logging

logger = logging.getLogger("paperclip.cleanup")


async def archive_old_tasks(session: AsyncSession, days: int = 30) -> dict:
    """Archive completed tasks older than specified days.

    Args:
        session: AsyncSession for database operations
        days: Number of days to keep (default 30)

    Returns:
        dict with count and timing info
    """
    start_time = datetime.utcnow()
    cutoff_date = start_time - timedelta(days=days)

    try:
        # Move completed tasks to archive
        result = await session.execute(text("""
            INSERT INTO tasks_archive (id, assigned_to, assigned_to_type, instruction, status, created_at, completed_at, output)
            SELECT id, assigned_to, assigned_to_type, instruction, status, created_at, completed_at, output
            FROM tasks
            WHERE status = 'complete' AND completed_at < :cutoff_date
                AND id NOT IN (SELECT id FROM tasks_archive)
        """), {"cutoff_date": cutoff_date})

        archived_count = result.rowcount or 0

        # Delete from main table
        if archived_count > 0:
            await session.execute(text("""
                DELETE FROM tasks
                WHERE status = 'complete' AND completed_at < :cutoff_date
                    AND id IN (SELECT id FROM tasks_archive WHERE archived_at > :archive_cutoff)
            """), {"cutoff_date": cutoff_date, "archive_cutoff": start_time - timedelta(seconds=1)})

        # Record cleanup job
        await session.execute(text("""
            INSERT INTO cleanup_jobs (job_type, status, records_processed, started_at, completed_at)
            VALUES ('archive_tasks', 'completed', :count, :started, :completed)
        """), {"count": archived_count, "started": start_time, "completed": datetime.utcnow()})

        await session.commit()

        logger.info(f"Archived {archived_count} tasks (older than {days} days)")
        return {
            "job_type": "archive_tasks",
            "archived_count": archived_count,
            "duration_seconds": (datetime.utcnow() - start_time).total_seconds()
        }

    except Exception as e:
        logger.error(f"Archive failed: {str(e)}")
        await session.execute(text("""
            INSERT INTO cleanup_jobs (job_type, status, error_message, started_at, completed_at)
            VALUES ('archive_tasks', 'failed', :error, :started, :completed)
        """), {"error": str(e), "started": start_time, "completed": datetime.utcnow()})
        await session.commit()
        raise


async def cleanup_routing_history(session: AsyncSession, days: int = 90) -> dict:
    """Delete routing history older than specified days.

    Args:
        session: AsyncSession for database operations
        days: Number of days to keep (default 90)

    Returns:
        dict with count and timing info
    """
    start_time = datetime.utcnow()
    cutoff_date = start_time - timedelta(days=days)

    try:
        result = await session.execute(text("""
            DELETE FROM routing_history
            WHERE created_at < :cutoff_date
        """), {"cutoff_date": cutoff_date})

        deleted_count = result.rowcount or 0

        # Record cleanup job
        await session.execute(text("""
            INSERT INTO cleanup_jobs (job_type, status, records_processed, started_at, completed_at)
            VALUES ('cleanup_routing', 'completed', :count, :started, :completed)
        """), {"count": deleted_count, "started": start_time, "completed": datetime.utcnow()})

        await session.commit()

        logger.info(f"Deleted {deleted_count} routing history records (older than {days} days)")
        return {
            "job_type": "cleanup_routing",
            "deleted_count": deleted_count,
            "duration_seconds": (datetime.utcnow() - start_time).total_seconds()
        }

    except Exception as e:
        logger.error(f"Cleanup routing failed: {str(e)}")
        await session.execute(text("""
            INSERT INTO cleanup_jobs (job_type, status, error_message, started_at, completed_at)
            VALUES ('cleanup_routing', 'failed', :error, :started, :completed)
        """), {"error": str(e), "started": start_time, "completed": datetime.utcnow()})
        await session.commit()
        raise


async def cleanup_old_audit_logs(session: AsyncSession, days: int = 365) -> dict:
    """Delete audit logs older than specified days.

    Args:
        session: AsyncSession for database operations
        days: Number of days to keep (default 365 = 1 year)

    Returns:
        dict with count and timing info
    """
    start_time = datetime.utcnow()
    cutoff_date = start_time - timedelta(days=days)

    try:
        result = await session.execute(text("""
            DELETE FROM audit_log
            WHERE created_at < :cutoff_date
        """), {"cutoff_date": cutoff_date})

        deleted_count = result.rowcount or 0

        # Record cleanup job
        await session.execute(text("""
            INSERT INTO cleanup_jobs (job_type, status, records_processed, started_at, completed_at)
            VALUES ('cleanup_audit_logs', 'completed', :count, :started, :completed)
        """), {"count": deleted_count, "started": start_time, "completed": datetime.utcnow()})

        await session.commit()

        logger.info(f"Deleted {deleted_count} audit log records (older than {days} days)")
        return {
            "job_type": "cleanup_audit_logs",
            "deleted_count": deleted_count,
            "duration_seconds": (datetime.utcnow() - start_time).total_seconds()
        }

    except Exception as e:
        logger.error(f"Cleanup audit logs failed: {str(e)}")
        await session.execute(text("""
            INSERT INTO cleanup_jobs (job_type, status, error_message, started_at, completed_at)
            VALUES ('cleanup_audit_logs', 'failed', :error, :started, :completed)
        """), {"error": str(e), "started": start_time, "completed": datetime.utcnow()})
        await session.commit()
        raise


async def run_full_cleanup(session: AsyncSession) -> dict:
    """Run all cleanup jobs in sequence.

    Args:
        session: AsyncSession for database operations

    Returns:
        dict with results from all cleanup jobs
    """
    results = {}

    try:
        results["archive_tasks"] = await archive_old_tasks(session, days=30)
    except Exception as e:
        results["archive_tasks"] = {"error": str(e)}

    try:
        results["cleanup_routing"] = await cleanup_routing_history(session, days=90)
    except Exception as e:
        results["cleanup_routing"] = {"error": str(e)}

    try:
        results["cleanup_audit_logs"] = await cleanup_old_audit_logs(session, days=365)
    except Exception as e:
        results["cleanup_audit_logs"] = {"error": str(e)}

    logger.info(f"Full cleanup completed: {results}")
    return results


async def get_cleanup_history(session: AsyncSession, limit: int = 20) -> list:
    """Retrieve recent cleanup job history.

    Args:
        session: AsyncSession for database operations
        limit: Maximum number of records to return

    Returns:
        list of cleanup jobs (most recent first)
    """
    result = await session.execute(text("""
        SELECT id, job_type, status, records_processed, started_at, completed_at, error_message
        FROM cleanup_jobs
        ORDER BY created_at DESC
        LIMIT :limit
    """), {"limit": limit})

    rows = result.fetchall()
    return [
        {
            "id": row[0],
            "job_type": row[1],
            "status": row[2],
            "records_processed": row[3],
            "started_at": row[4],
            "completed_at": row[5],
            "error_message": row[6]
        }
        for row in rows
    ]


async def get_archive_stats(session: AsyncSession) -> dict:
    """Get statistics about archived tasks.

    Args:
        session: AsyncSession for database operations

    Returns:
        dict with archive statistics
    """
    result = await session.execute(text("""
        SELECT
            COUNT(*) as total_archived,
            MIN(archived_at) as oldest_archive,
            MAX(archived_at) as newest_archive
        FROM tasks_archive
    """))

    row = result.fetchone()
    return {
        "total_archived": row[0] if row else 0,
        "oldest_archive": row[1] if row else None,
        "newest_archive": row[2] if row else None
    }

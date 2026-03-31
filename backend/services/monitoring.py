"""Monitoring and observability service for Paperclip fleet."""

import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta

logger = logging.getLogger("paperclip.monitoring")


async def get_task_metrics(db: AsyncSession, hours: int = 24) -> dict:
    """Get task success/failure rates and execution times."""
    try:
        since = datetime.utcnow() - timedelta(hours=hours)

        # Get task counts by status
        result = await db.execute(text("""
            SELECT status, COUNT(*) as count
            FROM tasks
            WHERE created_at > :since
            GROUP BY status
        """), {"since": since})

        status_counts = {row[0]: row[1] for row in result.all()}

        # Calculate success rate
        total = sum(status_counts.values())
        completed = status_counts.get("complete", 0)
        success_rate = (completed / total * 100) if total > 0 else 0

        return {
            "total_tasks": total,
            "completed": completed,
            "pending": status_counts.get("pending", 0),
            "busy": status_counts.get("busy", 0),
            "offline": status_counts.get("offline", 0),
            "success_rate": round(success_rate, 2),
            "time_period_hours": hours,
        }
    except Exception as e:
        logger.error(f"Failed to get task metrics: {e}")
        return {}


async def get_terminal_metrics(db: AsyncSession) -> dict:
    """Get terminal status distribution and availability."""
    try:
        result = await db.execute(text("""
            SELECT id, name, status FROM terminals ORDER BY id
        """))

        terminals = [{"id": row[0], "name": row[1], "status": row[2]} for row in result.all()]

        idle_count = sum(1 for t in terminals if t["status"] == "idle")
        busy_count = sum(1 for t in terminals if t["status"] == "busy")
        offline_count = sum(1 for t in terminals if t["status"] == "offline")

        return {
            "total": len(terminals),
            "idle": idle_count,
            "busy": busy_count,
            "offline": offline_count,
            "availability": round((len(terminals) - offline_count) / len(terminals) * 100, 2) if terminals else 0,
            "terminals": terminals,
        }
    except Exception as e:
        logger.error(f"Failed to get terminal metrics: {e}")
        return {}


async def get_hand_metrics(db: AsyncSession) -> dict:
    """Get hand status distribution and availability."""
    try:
        result = await db.execute(text("""
            SELECT id, name, status FROM hands ORDER BY id
        """))

        hands = [{"id": row[0], "name": row[1], "status": row[2]} for row in result.all()]

        idle_count = sum(1 for h in hands if h["status"] == "idle")
        busy_count = sum(1 for h in hands if h["status"] == "busy")
        offline_count = sum(1 for h in hands if h["status"] == "offline")

        return {
            "total": len(hands),
            "idle": idle_count,
            "busy": busy_count,
            "offline": offline_count,
            "availability": round((len(hands) - offline_count) / len(hands) * 100, 2) if hands else 0,
            "hands": hands,
        }
    except Exception as e:
        logger.error(f"Failed to get hand metrics: {e}")
        return {}


async def get_agent_execution_time(db: AsyncSession, agent_id: str) -> dict:
    """Get average execution time and success rate for specific agent."""
    try:
        result = await db.execute(text("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'complete' THEN 1 ELSE 0 END) as completed,
                AVG(EXTRACT(EPOCH FROM (completed_at - created_at))) as avg_seconds
            FROM tasks
            WHERE assigned_to = :agent_id AND completed_at IS NOT NULL
        """), {"agent_id": agent_id})

        row = result.mappings().first()
        if row:
            return {
                "agent_id": agent_id,
                "total_tasks": row["total"] or 0,
                "completed": row["completed"] or 0,
                "success_rate": round((row["completed"] / row["total"] * 100) if row["total"] else 0, 2),
                "avg_execution_seconds": round(row["avg_seconds"] or 0, 2),
            }
        return {"agent_id": agent_id, "total_tasks": 0, "completed": 0, "success_rate": 0, "avg_execution_seconds": 0}
    except Exception as e:
        logger.error(f"Failed to get agent execution time: {e}")
        return {}


async def get_fleet_health_snapshot(db: AsyncSession) -> dict:
    """Get comprehensive fleet health snapshot."""
    try:
        task_metrics = await get_task_metrics(db, hours=24)
        terminal_metrics = await get_terminal_metrics(db)
        hand_metrics = await get_hand_metrics(db)

        # Calculate overall health score (0-100)
        components = [
            task_metrics.get("success_rate", 0),
            terminal_metrics.get("availability", 0),
            hand_metrics.get("availability", 0),
        ]
        overall_health = round(sum(components) / len(components), 2) if components else 0

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "overall_health_score": overall_health,
            "tasks": task_metrics,
            "terminals": terminal_metrics,
            "hands": hand_metrics,
            "status": "healthy" if overall_health >= 80 else "degraded" if overall_health >= 60 else "critical",
        }
    except Exception as e:
        logger.error(f"Failed to get fleet health snapshot: {e}")
        return {}

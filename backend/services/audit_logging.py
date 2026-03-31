"""Audit logging for compliance and security."""

import logging
import json
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta

logger = logging.getLogger("paperclip.audit_logging")


async def log_audit_event(
    db: AsyncSession,
    username: str,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    details: dict | None = None,
    ip_address: str | None = None,
) -> None:
    """Log an audit event (async, non-blocking)."""
    try:
        details_json = json.dumps(details) if details else None

        await db.execute(text("""
            INSERT INTO audit_log (username, action, resource_type, resource_id, details, ip_address)
            VALUES (:username, :action, :resource_type, :resource_id, :details, :ip_address)
        """), {
            "username": username,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "details": details_json,
            "ip_address": ip_address,
        })
        await db.commit()
    except Exception as e:
        logger.warning(f"Failed to log audit event: {e}")
        await db.rollback()


async def get_audit_log(
    db: AsyncSession,
    username: str | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    hours: int = 24,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Get filtered audit log entries."""
    try:
        since = datetime.utcnow() - timedelta(hours=hours)

        where_clauses = ["created_at > :since"]
        params = {"since": since}

        if username:
            where_clauses.append("username = :username")
            params["username"] = username
        if action:
            where_clauses.append("action = :action")
            params["action"] = action
        if resource_type:
            where_clauses.append("resource_type = :resource_type")
            params["resource_type"] = resource_type

        where_clause = " AND ".join(where_clauses)

        # Get total count
        count_result = await db.execute(text(f"""
            SELECT COUNT(*) FROM audit_log WHERE {where_clause}
        """), params)
        total = count_result.scalar() or 0

        # Get paginated results
        params["limit"] = limit
        params["offset"] = offset

        result = await db.execute(text(f"""
            SELECT id, username, action, resource_type, resource_id, details, ip_address, created_at
            FROM audit_log
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """), params)

        rows = result.mappings().all()
        entries = [
            {
                "id": row["id"],
                "username": row["username"],
                "action": row["action"],
                "resource_type": row["resource_type"],
                "resource_id": row["resource_id"],
                "details": json.loads(row["details"]) if row["details"] else None,
                "ip_address": row["ip_address"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            }
            for row in rows
        ]

        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + limit < total,
            "entries": entries,
        }
    except Exception as e:
        logger.error(f"Failed to get audit log: {e}")
        return {"total": 0, "entries": []}


async def get_audit_summary(db: AsyncSession, hours: int = 24) -> dict:
    """Get summary of audit events."""
    try:
        since = datetime.utcnow() - timedelta(hours=hours)

        # Get action counts
        result = await db.execute(text("""
            SELECT action, COUNT(*) as count
            FROM audit_log
            WHERE created_at > :since
            GROUP BY action
            ORDER BY count DESC
        """), {"since": since})

        action_counts = {row[0]: row[1] for row in result.all()}

        # Get user counts
        result = await db.execute(text("""
            SELECT COUNT(DISTINCT username) as unique_users,
                   COUNT(*) as total_events
            FROM audit_log
            WHERE created_at > :since
        """), {"since": since})

        row = result.mappings().first()

        return {
            "period_hours": hours,
            "total_events": row["total_events"] or 0,
            "unique_users": row["unique_users"] or 0,
            "action_breakdown": action_counts,
        }
    except Exception as e:
        logger.error(f"Failed to get audit summary: {e}")
        return {}

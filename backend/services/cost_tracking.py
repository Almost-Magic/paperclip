"""Cost tracking for LLM calls and infrastructure."""

import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta

logger = logging.getLogger("paperclip.cost_tracking")

# Pricing per 1M tokens (AUD) — adjust based on actual rates
PRICING = {
    "claude-opus": {"input": 15, "output": 75},
    "claude-sonnet": {"input": 3, "output": 15},
    "claude-haiku": {"input": 0.25, "output": 1.25},
    "ollama": {"input": 0, "output": 0},  # Local, no cost
    "gpt-4": {"input": 30, "output": 60},
    "gpt-3.5": {"input": 0.50, "output": 1.50},
    "deepseek": {"input": 0.14, "output": 0.28},
    "gemini": {"input": 0.075, "output": 0.30},
}


def calculate_cost_cents(model: str, input_tokens: int, output_tokens: int) -> int:
    """Calculate cost in cents for a model call."""
    pricing = PRICING.get(model.lower(), {"input": 0, "output": 0})

    # Cost = (tokens / 1M) * price_per_M
    input_cost = (input_tokens / 1_000_000) * pricing.get("input", 0)
    output_cost = (output_tokens / 1_000_000) * pricing.get("output", 0)

    # Convert to cents (AUD)
    total_cents = int((input_cost + output_cost) * 100)
    return max(0, total_cents)  # Never negative


async def record_task_cost(
    db: AsyncSession,
    task_id: str,
    agent_id: str,
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> dict:
    """Record cost for a completed task."""
    try:
        cost_cents = calculate_cost_cents(model, input_tokens, output_tokens)

        await db.execute(text("""
            INSERT INTO cost_ledger (task_id, agent_id, model, input_tokens, output_tokens, cost_cents)
            VALUES (:task_id, :agent_id, :model, :input_tokens, :output_tokens, :cost_cents)
            ON CONFLICT (task_id) DO UPDATE SET
                cost_cents = :cost_cents,
                input_tokens = :input_tokens,
                output_tokens = :output_tokens
        """), {
            "task_id": task_id,
            "agent_id": agent_id,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_cents": cost_cents,
        })
        await db.commit()

        return {
            "task_id": task_id,
            "cost_cents": cost_cents,
            "cost_aud": round(cost_cents / 100, 4),
            "model": model,
        }
    except Exception as e:
        logger.error(f"Failed to record task cost: {e}")
        await db.rollback()
        return {}


async def get_cost_summary(
    db: AsyncSession,
    agent_id: str | None = None,
    hours: int = 24,
) -> dict:
    """Get cost summary for period (optionally filtered by agent)."""
    try:
        since = datetime.utcnow() - timedelta(hours=hours)

        where_clause = "created_at > :since"
        params = {"since": since}

        if agent_id:
            where_clause += " AND agent_id = :agent_id"
            params["agent_id"] = agent_id

        result = await db.execute(text(f"""
            SELECT
                COUNT(*) as task_count,
                SUM(cost_cents) as total_cents,
                AVG(cost_cents) as avg_cents,
                SUM(input_tokens) as total_input,
                SUM(output_tokens) as total_output,
                COUNT(DISTINCT agent_id) as unique_agents
            FROM cost_ledger
            WHERE {where_clause}
        """), params)

        row = result.mappings().first()
        if row:
            total_cents = row["total_cents"] or 0
            return {
                "period_hours": hours,
                "task_count": row["task_count"] or 0,
                "total_cost_cents": int(total_cents),
                "total_cost_aud": round(total_cents / 100, 2),
                "avg_cost_cents": int(row["avg_cents"] or 0),
                "avg_cost_aud": round((row["avg_cents"] or 0) / 100, 4),
                "total_tokens_input": row["total_input"] or 0,
                "total_tokens_output": row["total_output"] or 0,
                "unique_agents": row["unique_agents"] or 0,
                "agent_id": agent_id,
            }
        return {
            "period_hours": hours,
            "task_count": 0,
            "total_cost_aud": 0,
            "agent_id": agent_id,
        }
    except Exception as e:
        logger.error(f"Failed to get cost summary: {e}")
        return {}


async def get_cost_by_agent(db: AsyncSession, hours: int = 24) -> dict:
    """Get cost breakdown by agent."""
    try:
        since = datetime.utcnow() - timedelta(hours=hours)

        result = await db.execute(text("""
            SELECT
                agent_id,
                COUNT(*) as task_count,
                SUM(cost_cents) as total_cents,
                AVG(cost_cents) as avg_cents
            FROM cost_ledger
            WHERE created_at > :since
            GROUP BY agent_id
            ORDER BY total_cents DESC
        """), {"since": since})

        rows = result.mappings().all()
        return {
            "period_hours": hours,
            "agents": [
                {
                    "agent_id": row["agent_id"],
                    "task_count": row["task_count"],
                    "total_cost_aud": round((row["total_cents"] or 0) / 100, 2),
                    "avg_cost_aud": round((row["avg_cents"] or 0) / 100, 4),
                }
                for row in rows
            ],
        }
    except Exception as e:
        logger.error(f"Failed to get cost by agent: {e}")
        return {"agents": []}


async def get_cost_trend(db: AsyncSession, days: int = 7) -> dict:
    """Get daily cost trend for last N days."""
    try:
        since = datetime.utcnow() - timedelta(days=days)

        result = await db.execute(text("""
            SELECT
                DATE(created_at) as date,
                COUNT(*) as task_count,
                SUM(cost_cents) as total_cents
            FROM cost_ledger
            WHERE created_at > :since
            GROUP BY DATE(created_at)
            ORDER BY DATE(created_at) ASC
        """), {"since": since})

        rows = result.mappings().all()
        daily_data = [
            {
                "date": row["date"].isoformat() if row["date"] else None,
                "task_count": row["task_count"],
                "cost_aud": round((row["total_cents"] or 0) / 100, 2),
            }
            for row in rows
        ]

        total_cents = sum((row["total_cents"] or 0) for row in rows)
        avg_daily = total_cents / days if days > 0 else 0

        return {
            "period_days": days,
            "daily_data": daily_data,
            "total_cost_aud": round(total_cents / 100, 2),
            "avg_daily_aud": round(avg_daily / 100, 2),
        }
    except Exception as e:
        logger.error(f"Failed to get cost trend: {e}")
        return {"daily_data": []}

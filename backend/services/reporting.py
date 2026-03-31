"""Advanced Reporting API for Paperclip — Phase 3 F5.

Features:
- Cost forecasting (ML-lite trend prediction)
- Budget alerts and recommendations
- Cost optimization insights
- Detailed cost breakdowns
"""

from datetime import datetime, timedelta
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import statistics
import logging

logger = logging.getLogger("paperclip.reporting")


async def get_cost_forecast(
    session: AsyncSession,
    days_ahead: int = 7,
    historical_days: int = 30,
) -> dict:
    """Predict future costs using linear trend analysis.

    Args:
        session: AsyncSession for database operations
        days_ahead: Number of days to forecast (default 7)
        historical_days: Historical data for trend (default 30)

    Returns:
        dict with forecast including daily predictions and trend
    """
    try:
        # Get historical daily costs
        cutoff_date = datetime.utcnow() - timedelta(days=historical_days)

        result = await session.execute(text("""
            SELECT DATE(created_at) as date, SUM(cost_cents) as daily_cost
            FROM cost_ledger
            WHERE created_at >= :cutoff_date
            GROUP BY DATE(created_at)
            ORDER BY date
        """), {"cutoff_date": cutoff_date})

        historical = result.fetchall()
        if not historical or len(historical) < 3:
            return {
                "status": "insufficient_data",
                "message": f"Need at least 3 days of data ({len(historical)} found)",
                "forecast": []
            }

        # Extract costs (convert cents to dollars)
        costs = [row[1] / 100.0 for row in historical]
        dates = [row[0] for row in historical]

        # Simple linear trend: y = mx + b
        n = len(costs)
        avg_x = (n - 1) / 2
        avg_y = statistics.mean(costs)

        # Calculate slope (m)
        numerator = sum((i - avg_x) * (costs[i] - avg_y) for i in range(n))
        denominator = sum((i - avg_x) ** 2 for i in range(n))
        slope = numerator / denominator if denominator != 0 else 0
        intercept = avg_y - slope * avg_x

        # Generate forecast
        forecast = []
        today = datetime.utcnow().date()
        for day_offset in range(1, days_ahead + 1):
            future_date = today + timedelta(days=day_offset)
            # Linear projection: y = mx + b
            predicted_cost = max(0, slope * (n - 1 + day_offset) + intercept)
            forecast.append({
                "date": future_date.isoformat(),
                "predicted_cost_aud": round(predicted_cost, 2),
                "confidence": "medium" if len(costs) >= 7 else "low"
            })

        # Calculate trend
        if slope > 0.1:
            trend = "increasing"
        elif slope < -0.1:
            trend = "decreasing"
        else:
            trend = "stable"

        return {
            "status": "success",
            "trend": trend,
            "slope": round(slope, 4),
            "historical_avg": round(avg_y, 2),
            "historical_days": n,
            "forecast": forecast,
            "forecast_total": round(sum(f["predicted_cost_aud"] for f in forecast), 2),
            "forecast_daily_avg": round(sum(f["predicted_cost_aud"] for f in forecast) / days_ahead, 2)
        }

    except Exception as e:
        logger.error(f"Cost forecasting failed: {str(e)}")
        return {"status": "error", "message": str(e), "forecast": []}


async def get_cost_optimization_tips(
    session: AsyncSession,
    hours: int = 24,
) -> dict:
    """Generate cost optimization recommendations.

    Args:
        session: AsyncSession for database operations
        hours: Time period for analysis (default 24 hours)

    Returns:
        dict with optimization tips and opportunities
    """
    try:
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)

        # Get cost breakdown by agent and model
        result = await session.execute(text("""
            SELECT
                agent_id,
                model,
                COUNT(*) as task_count,
                SUM(input_tokens) as input_tokens,
                SUM(output_tokens) as output_tokens,
                SUM(cost_cents) as total_cost
            FROM cost_ledger
            WHERE created_at >= :cutoff_time
            GROUP BY agent_id, model
            ORDER BY total_cost DESC
        """), {"cutoff_time": cutoff_time})

        costs_by_agent_model = result.fetchall()

        tips = []
        total_cost = sum(row[5] for row in costs_by_agent_model) / 100.0

        # Tip 1: High-cost agents
        for agent_id, model, task_count, input_tokens, output_tokens, cost_cents in costs_by_agent_model[:3]:
            cost = cost_cents / 100.0
            pct = (cost / total_cost * 100) if total_cost > 0 else 0
            if pct > 20:
                tips.append({
                    "type": "high_cost_agent",
                    "agent": agent_id,
                    "model": model,
                    "cost_aud": round(cost, 2),
                    "percentage": round(pct, 1),
                    "suggestion": f"Consider routing fewer tasks to {agent_id} or using cheaper model for {model}"
                })

        # Tip 2: Token efficiency
        for agent_id, model, task_count, input_tokens, output_tokens, cost_cents in costs_by_agent_model:
            if task_count > 10:
                avg_output = output_tokens / task_count if task_count > 0 else 0
                if avg_output > 2000:
                    tips.append({
                        "type": "token_efficiency",
                        "agent": agent_id,
                        "avg_output_tokens": int(avg_output),
                        "suggestion": f"{agent_id} outputs {avg_output:.0f} tokens on average. Consider prompt optimization."
                    })

        # Tip 3: Most efficient agent (for benchmarking)
        if costs_by_agent_model:
            most_efficient = min(
                costs_by_agent_model,
                key=lambda x: (x[5] / x[2]) if x[2] > 0 else float('inf')
            )
            tips.insert(0, {
                "type": "efficiency_leader",
                "agent": most_efficient[0],
                "model": most_efficient[1],
                "cost_per_task": round((most_efficient[5] / 100.0) / most_efficient[2], 4),
                "suggestion": f"{most_efficient[0]} is most cost-efficient at ${(most_efficient[5] / 100.0) / most_efficient[2]:.4f}/task"
            })

        return {
            "status": "success",
            "period_hours": hours,
            "total_cost_aud": round(total_cost, 2),
            "tip_count": len(tips),
            "tips": tips
        }

    except Exception as e:
        logger.error(f"Cost optimization analysis failed: {str(e)}")
        return {"status": "error", "message": str(e), "tips": []}


async def get_cost_breakdown_detailed(
    session: AsyncSession,
    hours: int = 24,
    group_by: str = "agent",  # 'agent', 'model', 'action'
) -> dict:
    """Get detailed cost breakdown by various dimensions.

    Args:
        session: AsyncSession for database operations
        hours: Time period for analysis
        group_by: Grouping dimension ('agent', 'model', or 'action')

    Returns:
        dict with detailed cost breakdown
    """
    try:
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)

        if group_by == "agent":
            query = """
                SELECT
                    agent_id as dimension,
                    COUNT(*) as task_count,
                    SUM(cost_cents) as total_cost,
                    AVG(cost_cents) as avg_cost,
                    SUM(input_tokens) as input_tokens,
                    SUM(output_tokens) as output_tokens
                FROM cost_ledger
                WHERE created_at >= :cutoff_time
                GROUP BY agent_id
                ORDER BY total_cost DESC
            """
        elif group_by == "model":
            query = """
                SELECT
                    model as dimension,
                    COUNT(*) as task_count,
                    SUM(cost_cents) as total_cost,
                    AVG(cost_cents) as avg_cost,
                    SUM(input_tokens) as input_tokens,
                    SUM(output_tokens) as output_tokens
                FROM cost_ledger
                WHERE created_at >= :cutoff_time
                GROUP BY model
                ORDER BY total_cost DESC
            """
        else:  # provider
            query = """
                SELECT
                    provider as dimension,
                    COUNT(*) as task_count,
                    SUM(cost_cents) as total_cost,
                    AVG(cost_cents) as avg_cost,
                    SUM(input_tokens) as input_tokens,
                    SUM(output_tokens) as output_tokens
                FROM cost_ledger
                WHERE created_at >= :cutoff_time
                GROUP BY provider
                ORDER BY total_cost DESC
            """

        result = await session.execute(text(query), {"cutoff_time": cutoff_time})
        rows = result.fetchall()

        items = []
        total_cost = sum(row[2] for row in rows) if rows else 0

        for dimension, task_count, total_cost_cents, avg_cost_cents, input_tokens, output_tokens in rows:
            pct = (total_cost_cents / total_cost * 100) if total_cost > 0 else 0
            items.append({
                "name": dimension or "unknown",
                "task_count": task_count,
                "total_cost_aud": round(total_cost_cents / 100.0, 2),
                "avg_cost_aud": round(avg_cost_cents / 100.0, 4),
                "percentage": round(pct, 1),
                "total_tokens": (input_tokens or 0) + (output_tokens or 0),
                "tokens_per_task": round(((input_tokens or 0) + (output_tokens or 0)) / task_count, 0) if task_count > 0 else 0
            })

        return {
            "status": "success",
            "group_by": group_by,
            "period_hours": hours,
            "total_cost_aud": round(total_cost / 100.0, 2),
            "item_count": len(items),
            "items": items
        }

    except Exception as e:
        logger.error(f"Detailed cost breakdown failed: {str(e)}")
        return {"status": "error", "message": str(e), "items": []}


async def get_budget_analysis(
    session: AsyncSession,
    monthly_budget_aud: float = 1000.0,
) -> dict:
    """Analyze spending against budget.

    Args:
        session: AsyncSession for database operations
        monthly_budget_aud: Monthly budget in AUD

    Returns:
        dict with budget vs actual analysis
    """
    try:
        # Get current month costs
        now = datetime.utcnow()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        result = await session.execute(text("""
            SELECT SUM(cost_cents) FROM cost_ledger
            WHERE created_at >= :month_start
        """), {"month_start": month_start})

        monthly_cost_cents = result.scalar() or 0
        monthly_cost_aud = monthly_cost_cents / 100.0

        # Calculate metrics
        spent_pct = (monthly_cost_aud / monthly_budget_aud * 100) if monthly_budget_aud > 0 else 0
        days_in_month = (now.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        days_elapsed = now.day
        days_remaining = days_in_month.day - days_elapsed

        # Forecast end-of-month
        daily_avg = monthly_cost_aud / days_elapsed if days_elapsed > 0 else 0
        projected_cost = monthly_cost_aud + (daily_avg * days_remaining)

        # Status
        if spent_pct > 90:
            status = "critical"
        elif spent_pct > 75:
            status = "warning"
        elif spent_pct > 50:
            status = "caution"
        else:
            status = "ok"

        return {
            "status": "success",
            "budget_aud": round(monthly_budget_aud, 2),
            "spent_aud": round(monthly_cost_aud, 2),
            "spent_percentage": round(spent_pct, 1),
            "remaining_aud": round(max(0, monthly_budget_aud - monthly_cost_aud), 2),
            "days_elapsed": days_elapsed,
            "days_remaining": max(0, days_remaining),
            "daily_average": round(daily_avg, 2),
            "projected_end_of_month": round(projected_cost, 2),
            "projected_over_budget": max(0, projected_cost - monthly_budget_aud),
            "health_status": status
        }

    except Exception as e:
        logger.error(f"Budget analysis failed: {str(e)}")
        return {"status": "error", "message": str(e)}

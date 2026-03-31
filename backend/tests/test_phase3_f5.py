"""Tests for Phase 3 F5: Advanced Reporting API.

Coverage target: 80%+
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from backend.services.reporting import (
    get_cost_forecast, get_cost_optimization_tips,
    get_cost_breakdown_detailed, get_budget_analysis
)


# ============================================================================
# COST FORECASTING TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_cost_forecast_with_insufficient_data():
    """Test forecast with insufficient historical data."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = []  # No data

    mock_session.execute.return_value = mock_result

    forecast = await get_cost_forecast(mock_session, days_ahead=7, historical_days=30)

    assert forecast["status"] == "insufficient_data"
    assert forecast["forecast"] == []


@pytest.mark.asyncio
async def test_cost_forecast_with_data():
    """Test forecast with valid historical data."""
    mock_session = AsyncMock()
    mock_result = MagicMock()

    # Simulate 10 days of cost data
    today = datetime.utcnow().date()
    historical_data = [
        (today - timedelta(days=9-i), 10000 + i*1000)  # Increasing costs
        for i in range(10)
    ]
    mock_result.fetchall.return_value = historical_data

    mock_session.execute.return_value = mock_result

    forecast = await get_cost_forecast(mock_session, days_ahead=7, historical_days=30)

    assert forecast["status"] == "success"
    assert len(forecast["forecast"]) == 7
    assert "trend" in forecast
    assert "forecast_total" in forecast
    assert all("predicted_cost_aud" in f for f in forecast["forecast"])


@pytest.mark.asyncio
async def test_cost_forecast_trend_detection():
    """Test that forecast correctly detects increasing trend."""
    mock_session = AsyncMock()
    mock_result = MagicMock()

    # Strongly increasing trend
    today = datetime.utcnow().date()
    historical_data = [
        (today - timedelta(days=9-i), 5000 * (i+1))  # 5k, 10k, 15k...
        for i in range(10)
    ]
    mock_result.fetchall.return_value = historical_data

    mock_session.execute.return_value = mock_result

    forecast = await get_cost_forecast(mock_session)

    assert forecast["status"] == "success"
    assert forecast["trend"] == "increasing"
    assert forecast["slope"] > 0.1


# ============================================================================
# COST OPTIMIZATION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_cost_optimization_no_data():
    """Test optimization tips with no cost data."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = []

    mock_session.execute.return_value = mock_result

    tips = await get_cost_optimization_tips(mock_session, hours=24)

    assert tips["status"] == "success"
    assert tips["tip_count"] == 0
    assert tips["tips"] == []


@pytest.mark.asyncio
async def test_cost_optimization_high_cost_agent():
    """Test optimization tips identify high-cost agents."""
    mock_session = AsyncMock()
    mock_result = MagicMock()

    # Two agents: one expensive (50% of costs), one cheap
    mock_result.fetchall.return_value = [
        ("T1", "claude-opus", 5, 10000, 50000, 500000),  # 50% of cost
        ("T2", "claude-haiku", 10, 5000, 25000, 100000),  # 10% of cost
    ]

    mock_session.execute.return_value = mock_result

    tips = await get_cost_optimization_tips(mock_session)

    assert tips["status"] == "success"
    # Should include efficiency leader and high-cost tips
    assert tips["tip_count"] > 0
    assert any(t["type"] == "high_cost_agent" for t in tips["tips"])


@pytest.mark.asyncio
async def test_cost_optimization_token_efficiency():
    """Test optimization tips detect inefficient token usage."""
    mock_session = AsyncMock()
    mock_result = MagicMock()

    # Agent with very high token output
    mock_result.fetchall.return_value = [
        ("T1", "claude-opus", 15, 50000, 300000, 500000),  # Avg 20k tokens/task
    ]

    mock_session.execute.return_value = mock_result

    tips = await get_cost_optimization_tips(mock_session)

    assert tips["status"] == "success"
    # Should detect high token usage
    token_tips = [t for t in tips["tips"] if t["type"] == "token_efficiency"]
    assert len(token_tips) > 0


# ============================================================================
# COST BREAKDOWN TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_cost_breakdown_by_agent():
    """Test cost breakdown grouped by agent."""
    mock_session = AsyncMock()
    mock_result = MagicMock()

    mock_result.fetchall.return_value = [
        ("T1", 10, 500000, 50000, 50000, 200000),  # 50% of cost
        ("T2", 20, 300000, 15000, 30000, 100000),  # 30% of cost
        ("T3", 30, 200000, 6666, 20000, 50000),   # 20% of cost
    ]

    mock_session.execute.return_value = mock_result

    breakdown = await get_cost_breakdown_detailed(mock_session, hours=24, group_by="agent")

    assert breakdown["status"] == "success"
    assert len(breakdown["items"]) == 3
    assert breakdown["items"][0]["name"] == "T1"
    assert breakdown["items"][0]["total_cost_aud"] == 5000.0
    assert breakdown["items"][0]["percentage"] == 50.0


@pytest.mark.asyncio
async def test_cost_breakdown_by_model():
    """Test cost breakdown grouped by model."""
    mock_session = AsyncMock()
    mock_result = MagicMock()

    mock_result.fetchall.return_value = [
        ("claude-opus", 5, 400000, 80000, 20000, 150000),  # 40% of cost
        ("claude-sonnet", 15, 300000, 20000, 30000, 100000),  # 30% of cost
        ("claude-haiku", 30, 300000, 10000, 50000, 100000),  # 30% of cost
    ]

    mock_session.execute.return_value = mock_result

    breakdown = await get_cost_breakdown_detailed(mock_session, group_by="model")

    assert breakdown["status"] == "success"
    assert breakdown["group_by"] == "model"
    assert len(breakdown["items"]) == 3


@pytest.mark.asyncio
async def test_cost_breakdown_tokens_per_task():
    """Test that breakdown calculates tokens per task correctly."""
    mock_session = AsyncMock()
    mock_result = MagicMock()

    mock_result.fetchall.return_value = [
        ("T1", 10, 500000, 50000, 100000, 200000),  # 30k tokens for 10 tasks = 3k/task
    ]

    mock_session.execute.return_value = mock_result

    breakdown = await get_cost_breakdown_detailed(mock_session)

    assert breakdown["items"][0]["tokens_per_task"] == 30000  # 300k / 10


# ============================================================================
# BUDGET ANALYSIS TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_budget_analysis_under_budget():
    """Test budget analysis when under budget."""
    mock_session = AsyncMock()
    mock_result = MagicMock()

    # Current month: only 2000 cents spent (20 AUD)
    mock_result.scalar.return_value = 2000

    mock_session.execute.return_value = mock_result

    analysis = await get_budget_analysis(mock_session, monthly_budget_aud=1000.0)

    assert analysis["status"] == "success"
    assert analysis["spent_aud"] == 20.0
    assert analysis["spent_percentage"] == 2.0
    assert analysis["remaining_aud"] == 980.0
    assert analysis["health_status"] == "ok"


@pytest.mark.asyncio
async def test_budget_analysis_over_budget():
    """Test budget analysis when approaching/over budget."""
    mock_session = AsyncMock()
    mock_result = MagicMock()

    # Current month: 950 cents spent (950 AUD) out of 1000
    mock_result.scalar.return_value = 95000

    mock_session.execute.return_value = mock_result

    analysis = await get_budget_analysis(mock_session, monthly_budget_aud=1000.0)

    assert analysis["status"] == "success"
    assert analysis["spent_aud"] == 950.0
    assert analysis["spent_percentage"] == 95.0
    assert analysis["health_status"] == "critical"


@pytest.mark.asyncio
async def test_budget_analysis_projection():
    """Test that budget analysis projects end-of-month costs."""
    mock_session = AsyncMock()
    mock_result = MagicMock()

    # Day 10 of month: 5000 cents (50 AUD) spent
    mock_result.scalar.return_value = 5000

    mock_session.execute.return_value = mock_result

    analysis = await get_budget_analysis(mock_session, monthly_budget_aud=1000.0)

    assert analysis["status"] == "success"
    assert "projected_end_of_month" in analysis
    assert "daily_average" in analysis
    # If we've spent 50 AUD in 10 days, daily avg is 5 AUD
    # 20 more days would be about 100 AUD more
    assert analysis["daily_average"] > 0


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_forecast_database_error():
    """Test forecast handles database errors gracefully."""
    mock_session = AsyncMock()
    mock_session.execute.side_effect = Exception("Database error")

    forecast = await get_cost_forecast(mock_session)

    assert forecast["status"] == "error"
    assert "message" in forecast


@pytest.mark.asyncio
async def test_optimization_database_error():
    """Test optimization handles database errors gracefully."""
    mock_session = AsyncMock()
    mock_session.execute.side_effect = Exception("Database error")

    tips = await get_cost_optimization_tips(mock_session)

    assert tips["status"] == "error"
    assert tips["tips"] == []


@pytest.mark.asyncio
async def test_breakdown_database_error():
    """Test breakdown handles database errors gracefully."""
    mock_session = AsyncMock()
    mock_session.execute.side_effect = Exception("Database error")

    breakdown = await get_cost_breakdown_detailed(mock_session)

    assert breakdown["status"] == "error"
    assert breakdown["items"] == []


@pytest.mark.asyncio
async def test_budget_database_error():
    """Test budget analysis handles database errors gracefully."""
    mock_session = AsyncMock()
    mock_session.execute.side_effect = Exception("Database error")

    analysis = await get_budget_analysis(mock_session)

    assert analysis["status"] == "error"


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_forecast_confidence_levels():
    """Test that forecast assigns appropriate confidence levels."""
    mock_session = AsyncMock()
    mock_result = MagicMock()

    # 3 days of data (low confidence)
    today = datetime.utcnow().date()
    historical_data = [
        (today - timedelta(days=2), 10000),
        (today - timedelta(days=1), 10500),
        (today, 11000),
    ]
    mock_result.fetchall.return_value = historical_data

    mock_session.execute.return_value = mock_result

    forecast = await get_cost_forecast(mock_session)

    assert forecast["status"] == "success"
    for item in forecast["forecast"]:
        assert item["confidence"] == "low"


@pytest.mark.asyncio
async def test_forecast_stable_trend():
    """Test forecast detects stable trend correctly."""
    mock_session = AsyncMock()
    mock_result = MagicMock()

    # Stable costs around 10000
    today = datetime.utcnow().date()
    historical_data = [
        (today - timedelta(days=9-i), 10000)  # Same cost every day
        for i in range(10)
    ]
    mock_result.fetchall.return_value = historical_data

    mock_session.execute.return_value = mock_result

    forecast = await get_cost_forecast(mock_session)

    assert forecast["status"] == "success"
    assert forecast["trend"] == "stable"
    assert forecast["slope"] < 0.1

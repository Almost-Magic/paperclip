"""Paperclip — AMTL Fleet Command Centre (FastAPI main app)."""

import logging
from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from config import PORT, HOST, ENV
from models.database import init_db, seed_terminals_and_hands, get_session, SessionLocal
from models.schemas import (
    HealthResponse, TerminalOut, HandOut, TaskCreate, TaskOut, CommandRequest, CommandResponse,
    LoginRequest, LoginResponse, TaskReplayRequest
)
from services.routing_engine import route_command
from services.advanced_routing import route_command_advanced, save_user_preference, get_routing_frequency, record_routing_decision
from services.auth import authenticate_user, create_access_token, verify_token, get_token_from_header
from services.websocket import manager
from services.monitoring import get_task_metrics, get_terminal_metrics, get_hand_metrics, get_agent_execution_time, get_fleet_health_snapshot
from services.cost_tracking import record_task_cost, get_cost_summary, get_cost_by_agent, get_cost_trend
from services.audit_logging import log_audit_event, get_audit_log, get_audit_summary
from services.reporting import get_cost_forecast, get_cost_optimization_tips, get_cost_breakdown_detailed, get_budget_analysis
from services.caching import (
    cache_terminals_list, get_cached_terminals_list, invalidate_terminals_cache,
    cache_hands_list, get_cached_hands_list, invalidate_hands_cache,
    cache_fleet_health, get_cached_fleet_health, invalidate_fleet_health_cache,
    cache_cost_summary, get_cached_cost_summary, invalidate_cost_cache, get_cache
)
from services.cleanup import archive_old_tasks, cleanup_routing_history, cleanup_old_audit_logs, run_full_cleanup, get_cleanup_history, get_archive_stats
import uuid
from datetime import datetime, timedelta
from collections import defaultdict
import time

logger = logging.getLogger("paperclip")

# FastAPI app
app = FastAPI(
    title="Paperclip",
    description="AMTL Fleet Command Centre",
    version="1.0.0",
)

# Rate limiting (simple in-memory implementation)
# Production would use Redis for distributed rate limiting
rate_limit_storage: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT_PER_SECOND = 10
RATE_LIMIT_WINDOW = 60  # seconds


@app.middleware("http")
async def rate_limit_middleware(request, call_next):
    """Simple rate limiting middleware (10 requests per minute per IP)."""
    client_ip = request.client.host if request.client else "unknown"

    # Clean old entries
    current_time = time.time()
    if client_ip in rate_limit_storage:
        rate_limit_storage[client_ip] = [t for t in rate_limit_storage[client_ip] if current_time - t < RATE_LIMIT_WINDOW]

    # Check rate limit
    if len(rate_limit_storage[client_ip]) >= RATE_LIMIT_PER_SECOND:
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded (10 requests per minute)"},
        )

    # Record this request
    rate_limit_storage[client_ip].append(current_time)

    response = await call_next(request)
    return response


# Lifespan event — initialize DB on startup
@app.on_event("startup")
async def startup_event():
    """Initialize database and seed terminals/hands on startup."""
    logger.info(f"Starting Paperclip on {HOST}:{PORT} ({ENV})")
    await init_db()
    await seed_terminals_and_hands()
    logger.info("Paperclip ready")


# Health endpoint
@app.get("/paperclip/health")
@app.get("/health")
async def health(db: AsyncSession = Depends(get_session)):
    """Health check endpoint (AMTL standard)."""
    try:
        # Quick DB check
        await db.execute(text("SELECT 1"))

        # Count online terminals and hands
        t_result = await db.execute(text("SELECT COUNT(*) FROM terminals WHERE status = 'idle' OR status = 'busy'"))
        terminals_online = t_result.scalar() or 0

        h_result = await db.execute(text("SELECT COUNT(*) FROM hands WHERE status = 'idle' OR status = 'busy'"))
        hands_online = h_result.scalar() or 0

        return HealthResponse(
            status="operational",
            database="ok",
            terminals_online=terminals_online,
            hands_online=hands_online,
        )
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unavailable")


# Authentication dependency
async def get_current_user(authorization: str = Depends(HTTPBearer(auto_error=False))):
    """Dependency to validate JWT token from Authorization header."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")

    token = get_token_from_header(f"Bearer {authorization.credentials}")
    if not token:
        raise HTTPException(status_code=401, detail="Invalid authorization header format")

    try:
        payload = verify_token(token)
        return {
            "username": payload.get("sub"),
            "role": payload.get("role"),
            "permissions": payload.get("permissions", []),
        }
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


# Login endpoint (no auth required)
@app.post("/paperclip/auth/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """Authenticate user and return JWT token."""
    user = authenticate_user(request.username, request.password)
    if not user:
        logger.warning(f"Login failed for user: {request.username}")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Create token
    access_token = create_access_token({
        "sub": user["username"],
        "role": user["role"],
        "permissions": user["permissions"],
    })

    logger.info(f"User logged in: {user['username']} (role={user['role']})")

    return LoginResponse(
        access_token=access_token,
        username=user["username"],
        role=user["role"],
        expires_in=1440 * 60,  # 24 hours in seconds
    )


# Terminals endpoint
@app.get("/paperclip/api/terminals", response_model=list[TerminalOut])
async def list_terminals(
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """List all 7 terminals with status (requires authentication). Cached for 5 seconds."""
    try:
        # Check cache first (Phase 3 F4)
        cached = get_cached_terminals_list()
        if cached is not None:
            return cached

        result = await db.execute(text("SELECT * FROM terminals ORDER BY id"))
        rows = result.mappings().all()
        terminals = [dict(row) for row in rows]

        # Cache for 5 seconds
        cache_terminals_list(terminals)
        return terminals
    except Exception as e:
        logger.error(f"Failed to list terminals: {e}")
        raise HTTPException(status_code=500, detail="Failed to list terminals")


# Hands endpoint
@app.get("/paperclip/api/hands", response_model=list[HandOut])
async def list_hands(
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """List all 11 hands with status. Cached for 5 seconds."""
    try:
        # Check cache first (Phase 3 F4)
        cached = get_cached_hands_list()
        if cached is not None:
            return cached

        result = await db.execute(text("SELECT * FROM hands ORDER BY id"))
        rows = result.mappings().all()
        hands = [dict(row) for row in rows]

        # Cache for 5 seconds
        cache_hands_list(hands)
        return hands
    except Exception as e:
        logger.error(f"Failed to list hands: {e}")
        raise HTTPException(status_code=500, detail="Failed to list hands")


# Tasks endpoint — create
@app.post("/paperclip/api/tasks", response_model=TaskOut, status_code=201)
async def create_task(payload: TaskCreate, db: AsyncSession = Depends(get_session), current_user: dict = Depends(get_current_user)):
    """Create a task and assign to terminal/hand."""
    try:
        task_id = f"task_{uuid.uuid4().hex[:8]}"
        created_at = datetime.utcnow()

        await db.execute(text("""
            INSERT INTO tasks (id, assigned_to, assigned_to_type, instruction, status, created_at)
            VALUES (:id, :assigned_to, :assigned_to_type, :instruction, 'pending', :created_at)
        """), {
            "id": task_id,
            "assigned_to": payload.assigned_to,
            "assigned_to_type": payload.assigned_to_type,
            "instruction": payload.instruction,
            "created_at": created_at,
        })
        await db.commit()

        logger.info(f"Task {task_id} created: {payload.instruction}")

        # Log audit event
        await log_audit_event(
            db=db,
            username=current_user.get("username"),
            action="task_created",
            resource_type="task",
            resource_id=task_id,
            details={"instruction": payload.instruction, "assigned_to": payload.assigned_to},
        )

        # Broadcast to all connected WebSocket clients
        await manager.broadcast_task_created(
            task_id=task_id,
            instruction=payload.instruction,
            assigned_to=payload.assigned_to,
            assigned_to_type=payload.assigned_to_type,
        )

        return TaskOut(
            id=task_id,
            assigned_to=payload.assigned_to,
            assigned_to_type=payload.assigned_to_type,
            instruction=payload.instruction,
            status="pending",
            created_at=created_at,
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to create task: {e}")
        raise HTTPException(status_code=500, detail="Failed to create task")


# Tasks endpoint — list with filtering and pagination
@app.get("/paperclip/api/tasks", response_model=dict)
async def list_tasks(
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
    status: Optional[str] = None,
    assigned_to: Optional[str] = None,
    assigned_to_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    """List tasks with filtering and pagination."""
    try:
        # Build WHERE clause
        where_clauses = []
        params = {}

        if status:
            where_clauses.append("status = :status")
            params["status"] = status

        if assigned_to:
            where_clauses.append("assigned_to = :assigned_to")
            params["assigned_to"] = assigned_to

        if assigned_to_type:
            where_clauses.append("assigned_to_type = :assigned_to_type")
            params["assigned_to_type"] = assigned_to_type

        where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"

        # Get total count
        count_result = await db.execute(text(f"""
            SELECT COUNT(*) FROM tasks WHERE {where_clause}
        """), params)
        total = count_result.scalar() or 0

        # Get paginated results
        params["limit"] = limit
        params["offset"] = offset

        result = await db.execute(text(f"""
            SELECT id, assigned_to, assigned_to_type, instruction, status, output, created_at, completed_at
            FROM tasks
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """), params)
        rows = result.mappings().all()

        return {
            "items": [dict(row) for row in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + limit < total,
        }
    except Exception as e:
        logger.error(f"Failed to list tasks: {e}")
        raise HTTPException(status_code=500, detail="Failed to list tasks")


# Tasks endpoint — get detail
@app.get("/paperclip/api/tasks/{task_id}", response_model=TaskOut)
async def get_task(task_id: str, db: AsyncSession = Depends(get_session), current_user: dict = Depends(get_current_user)):
    """Get task detail."""
    try:
        result = await db.execute(text("""
            SELECT id, assigned_to, assigned_to_type, instruction, status, output, created_at, completed_at
            FROM tasks WHERE id = :id
        """), {"id": task_id})
        row = result.mappings().first()

        if not row:
            raise HTTPException(status_code=404, detail="Task not found")

        return dict(row)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get task: {e}")
        raise HTTPException(status_code=500, detail="Failed to get task")


# Tasks endpoint — replay
@app.post("/paperclip/api/tasks/{task_id}/replay", response_model=TaskOut, status_code=201)
async def replay_task(
    task_id: str,
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """Replay a previous task — creates a new task with same instruction."""
    try:
        # Get original task
        result = await db.execute(text("""
            SELECT assigned_to, assigned_to_type, instruction
            FROM tasks WHERE id = :id
        """), {"id": task_id})
        row = result.mappings().first()

        if not row:
            raise HTTPException(status_code=404, detail="Original task not found")

        # Create new task with same instruction
        new_task_id = f"task_{uuid.uuid4().hex[:8]}"
        created_at = datetime.utcnow()

        await db.execute(text("""
            INSERT INTO tasks (id, assigned_to, assigned_to_type, instruction, status, created_at)
            VALUES (:id, :assigned_to, :assigned_to_type, :instruction, 'pending', :created_at)
        """), {
            "id": new_task_id,
            "assigned_to": row.assigned_to,
            "assigned_to_type": row.assigned_to_type,
            "instruction": row.instruction,
            "created_at": created_at,
        })
        await db.commit()

        logger.info(f"Task {task_id} replayed as {new_task_id}: {row.instruction}")

        return TaskOut(
            id=new_task_id,
            assigned_to=row.assigned_to,
            assigned_to_type=row.assigned_to_type,
            instruction=row.instruction,
            status="pending",
            created_at=created_at,
        )
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to replay task: {e}")
        raise HTTPException(status_code=500, detail="Failed to replay task")


# Command endpoint — high-level routing (uses advanced routing with learning)
@app.post("/paperclip/api/command", response_model=CommandResponse)
async def handle_command(
    payload: CommandRequest,
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """High-level command — route to right terminal/hand and create task using advanced routing."""
    try:
        # Use advanced routing (with learning, preferences, fallback)
        agent_id, agent_type, reason = await route_command_advanced(
            instruction=payload.instruction,
            db=db,
            username=current_user.get("username"),
        )

        # Record routing decision for learning
        await record_routing_decision(
            db=db,
            username=current_user.get("username"),
            instruction=payload.instruction,
            keyword_matched=reason.split(":")[1] if ":" in reason else "",
            routed_to=agent_id,
            routed_to_type=agent_type,
            reason=reason,
        )

        # Create a task for the routed agent
        task_id = f"task_{uuid.uuid4().hex[:8]}"
        created_at = datetime.utcnow()

        await db.execute(text("""
            INSERT INTO tasks (id, assigned_to, assigned_to_type, instruction, status, created_at)
            VALUES (:id, :assigned_to, :assigned_to_type, :instruction, 'pending', :created_at)
        """), {
            "id": task_id,
            "assigned_to": agent_id,
            "assigned_to_type": agent_type,
            "instruction": payload.instruction,
            "created_at": created_at,
        })
        await db.commit()

        logger.info(f"Command routed: '{payload.instruction}' → {agent_id} ({reason})")

        # Broadcast task creation to all connected WebSocket clients
        await manager.broadcast_task_created(
            task_id=task_id,
            instruction=payload.instruction,
            assigned_to=agent_id,
            assigned_to_type=agent_type,
        )

        return CommandResponse(
            instruction=payload.instruction,
            routed_to=agent_id,
            routed_to_type=agent_type,
            task_id=task_id,
            message=f"Routed to {agent_id} ({reason})",
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to handle command: {e}")
        raise HTTPException(status_code=500, detail="Failed to handle command")


# User preferences endpoint — set preferred routing
@app.post("/paperclip/api/preferences")
async def set_user_preference(
    preferred_terminal: Optional[str] = None,
    preferred_hand: Optional[str] = None,
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """Set user routing preferences (preferred terminal or hand)."""
    try:
        await save_user_preference(
            db=db,
            username=current_user.get("username"),
            preferred_terminal=preferred_terminal,
            preferred_hand=preferred_hand,
        )
        logger.info(f"User {current_user.get('username')} preferences updated")
        return {
            "status": "success",
            "preferred_terminal": preferred_terminal,
            "preferred_hand": preferred_hand,
        }
    except Exception as e:
        logger.error(f"Failed to set user preference: {e}")
        raise HTTPException(status_code=500, detail="Failed to set preference")


# Routing frequency endpoint — show most common routes for user
@app.get("/paperclip/api/routing-stats")
async def get_routing_stats(
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """Get routing frequency statistics (learning insights)."""
    try:
        freq = await get_routing_frequency(db, current_user.get("username"))
        return {
            "username": current_user.get("username"),
            "routing_frequency": freq,
            "most_used": list(freq.keys())[0] if freq else None,
        }
    except Exception as e:
        logger.error(f"Failed to get routing stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to get routing stats")


# Monitoring & Observability Endpoints (F6)
@app.get("/paperclip/api/metrics/tasks")
async def get_task_metrics_endpoint(
    hours: int = 24,
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """Get task success/failure rates and execution statistics."""
    try:
        metrics = await get_task_metrics(db, hours)
        return metrics
    except Exception as e:
        logger.error(f"Failed to get task metrics: {e}")
        raise HTTPException(status_code=500, detail="Failed to get task metrics")


@app.get("/paperclip/api/metrics/terminals")
async def get_terminal_metrics_endpoint(
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """Get terminal availability and status distribution."""
    try:
        metrics = await get_terminal_metrics(db)
        return metrics
    except Exception as e:
        logger.error(f"Failed to get terminal metrics: {e}")
        raise HTTPException(status_code=500, detail="Failed to get terminal metrics")


@app.get("/paperclip/api/metrics/hands")
async def get_hand_metrics_endpoint(
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """Get hand availability and status distribution."""
    try:
        metrics = await get_hand_metrics(db)
        return metrics
    except Exception as e:
        logger.error(f"Failed to get hand metrics: {e}")
        raise HTTPException(status_code=500, detail="Failed to get hand metrics")


@app.get("/paperclip/api/metrics/agent/{agent_id}")
async def get_agent_metrics(
    agent_id: str,
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """Get specific agent execution time and success rate."""
    try:
        metrics = await get_agent_execution_time(db, agent_id)
        return metrics
    except Exception as e:
        logger.error(f"Failed to get agent metrics: {e}")
        raise HTTPException(status_code=500, detail="Failed to get agent metrics")


@app.get("/paperclip/api/metrics/fleet-health")
async def get_fleet_health(
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """Get comprehensive fleet health snapshot (overall score + component breakdown). Cached for 30 seconds."""
    try:
        # Check cache first (Phase 3 F4)
        cached = get_cached_fleet_health()
        if cached is not None:
            return cached

        health = await get_fleet_health_snapshot(db)

        # Cache for 30 seconds
        cache_fleet_health(health)
        return health
    except Exception as e:
        logger.error(f"Failed to get fleet health: {e}")
        raise HTTPException(status_code=500, detail="Failed to get fleet health")


# Cost Tracking Endpoints (Phase 3 F1)
@app.post("/paperclip/api/costs/record")
async def record_cost(
    task_id: str,
    agent_id: str,
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """Record cost for a task."""
    try:
        result = await record_task_cost(db, task_id, agent_id, model, input_tokens, output_tokens)
        # Invalidate cost cache when new cost recorded (Phase 3 F4)
        invalidate_cost_cache()
        return result
    except Exception as e:
        logger.error(f"Failed to record cost: {e}")
        raise HTTPException(status_code=500, detail="Failed to record cost")


@app.get("/paperclip/api/costs/summary")
async def get_cost_summary_endpoint(
    agent_id: Optional[str] = None,
    hours: int = 24,
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """Get cost summary for period (optionally by agent). Cached for 60 seconds (24h without agent_id filter)."""
    try:
        # Cache only 24h global summary (Phase 3 F4)
        if agent_id is None and hours == 24:
            cached = get_cached_cost_summary()
            if cached is not None:
                return cached

        summary = await get_cost_summary(db, agent_id, hours)

        # Cache only if global summary
        if agent_id is None and hours == 24:
            cache_cost_summary(summary)

        return summary
    except Exception as e:
        logger.error(f"Failed to get cost summary: {e}")
        raise HTTPException(status_code=500, detail="Failed to get cost summary")


@app.get("/paperclip/api/costs/by-agent")
async def get_agent_costs(
    hours: int = 24,
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """Get cost breakdown by agent."""
    try:
        data = await get_cost_by_agent(db, hours)
        return data
    except Exception as e:
        logger.error(f"Failed to get agent costs: {e}")
        raise HTTPException(status_code=500, detail="Failed to get agent costs")


@app.get("/paperclip/api/costs/trend")
async def get_cost_trend_endpoint(
    days: int = 7,
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """Get daily cost trend for last N days."""
    try:
        trend = await get_cost_trend(db, days)
        return trend
    except Exception as e:
        logger.error(f"Failed to get cost trend: {e}")
        raise HTTPException(status_code=500, detail="Failed to get cost trend")


# Advanced Reporting Endpoints (Phase 3 F5)
@app.get("/paperclip/api/reports/forecast")
async def get_cost_forecast_endpoint(
    days_ahead: int = 7,
    historical_days: int = 30,
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """Get cost forecast using trend analysis."""
    try:
        forecast = await get_cost_forecast(db, days_ahead, historical_days)
        return forecast
    except Exception as e:
        logger.error(f"Failed to get cost forecast: {e}")
        raise HTTPException(status_code=500, detail="Failed to get cost forecast")


@app.get("/paperclip/api/reports/optimization")
async def get_optimization_tips_endpoint(
    hours: int = 24,
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """Get cost optimization recommendations."""
    try:
        tips = await get_cost_optimization_tips(db, hours)
        return tips
    except Exception as e:
        logger.error(f"Failed to get optimization tips: {e}")
        raise HTTPException(status_code=500, detail="Failed to get optimization tips")


@app.get("/paperclip/api/reports/breakdown")
async def get_breakdown_endpoint(
    hours: int = 24,
    group_by: str = "agent",
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """Get detailed cost breakdown by agent, model, or provider."""
    try:
        if group_by not in ["agent", "model", "provider"]:
            raise HTTPException(status_code=400, detail="Invalid group_by parameter")
        breakdown = await get_cost_breakdown_detailed(db, hours, group_by)
        return breakdown
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get cost breakdown: {e}")
        raise HTTPException(status_code=500, detail="Failed to get cost breakdown")


@app.get("/paperclip/api/reports/budget")
async def get_budget_endpoint(
    budget_aud: float = 1000.0,
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """Analyze spending against monthly budget."""
    try:
        analysis = await get_budget_analysis(db, budget_aud)
        return analysis
    except Exception as e:
        logger.error(f"Failed to get budget analysis: {e}")
        raise HTTPException(status_code=500, detail="Failed to get budget analysis")


# Audit Logging Endpoints (Phase 3 F2)
@app.get("/paperclip/api/audit-log")
async def get_audit_log_endpoint(
    username: Optional[str] = None,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    hours: int = 24,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """Get filtered audit log entries."""
    try:
        log = await get_audit_log(db, username, action, resource_type, hours, limit, offset)
        return log
    except Exception as e:
        logger.error(f"Failed to get audit log: {e}")
        raise HTTPException(status_code=500, detail="Failed to get audit log")


@app.get("/paperclip/api/audit-summary")
async def get_audit_summary_endpoint(
    hours: int = 24,
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """Get summary of audit events."""
    try:
        summary = await get_audit_summary(db, hours)
        return summary
    except Exception as e:
        logger.error(f"Failed to get audit summary: {e}")
        raise HTTPException(status_code=500, detail="Failed to get audit summary")


# Database Cleanup Endpoints (Phase 3 F4)
@app.post("/paperclip/api/cleanup/run")
async def run_cleanup(
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """Run all database cleanup jobs (archive, routing history, audit logs)."""
    try:
        results = await run_full_cleanup(db)
        logger.info(f"Cleanup jobs completed: {results}")
        return {"status": "success", "results": results}
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")
        raise HTTPException(status_code=500, detail=f"Cleanup failed: {str(e)}")


@app.post("/paperclip/api/cleanup/archive-tasks")
async def archive_tasks(
    days: int = 30,
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """Archive completed tasks older than specified days."""
    try:
        result = await archive_old_tasks(db, days=days)
        logger.info(f"Task archival completed: {result}")
        return {"status": "success", "result": result}
    except Exception as e:
        logger.error(f"Task archival failed: {e}")
        raise HTTPException(status_code=500, detail=f"Task archival failed: {str(e)}")


@app.post("/paperclip/api/cleanup/routing-history")
async def cleanup_routing(
    days: int = 90,
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """Delete routing history older than specified days."""
    try:
        result = await cleanup_routing_history(db, days=days)
        logger.info(f"Routing history cleanup completed: {result}")
        return {"status": "success", "result": result}
    except Exception as e:
        logger.error(f"Routing history cleanup failed: {e}")
        raise HTTPException(status_code=500, detail=f"Routing cleanup failed: {str(e)}")


@app.post("/paperclip/api/cleanup/audit-logs")
async def cleanup_audit_logs(
    days: int = 365,
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """Delete audit logs older than specified days."""
    try:
        result = await cleanup_old_audit_logs(db, days=days)
        logger.info(f"Audit log cleanup completed: {result}")
        return {"status": "success", "result": result}
    except Exception as e:
        logger.error(f"Audit log cleanup failed: {e}")
        raise HTTPException(status_code=500, detail=f"Audit cleanup failed: {str(e)}")


@app.get("/paperclip/api/cleanup/history")
async def get_cleanup_history_endpoint(
    limit: int = 20,
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """Get recent cleanup job history."""
    try:
        history = await get_cleanup_history(db, limit=limit)
        return {"items": history}
    except Exception as e:
        logger.error(f"Failed to get cleanup history: {e}")
        raise HTTPException(status_code=500, detail="Failed to get cleanup history")


@app.get("/paperclip/api/cleanup/archive-stats")
async def get_archive_stats_endpoint(
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """Get statistics about archived tasks."""
    try:
        stats = await get_archive_stats(db)
        return stats
    except Exception as e:
        logger.error(f"Failed to get archive stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to get archive stats")


@app.get("/paperclip/api/cache/stats")
async def get_cache_stats(
    current_user: dict = Depends(get_current_user),
):
    """Get in-memory cache statistics."""
    try:
        stats = get_cache().stats()
        return {"cache": stats}
    except Exception as e:
        logger.error(f"Failed to get cache stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to get cache stats")


@app.post("/paperclip/api/cache/clear")
async def clear_cache(
    current_user: dict = Depends(get_current_user),
):
    """Clear all in-memory cache entries."""
    try:
        get_cache().clear()
        logger.info("Cache cleared by user")
        return {"status": "success", "message": "Cache cleared"}
    except Exception as e:
        logger.error(f"Failed to clear cache: {e}")
        raise HTTPException(status_code=500, detail="Failed to clear cache")


# WebSocket endpoint for real-time fleet updates
@app.websocket("/paperclip/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time terminal/hand/task updates.

    Clients connect and receive broadcasts whenever:
    - A terminal or hand changes status
    - A task is created, updated, or completed
    - Fleet health changes
    """
    await manager.connect(websocket)

    # Send initial fleet health on connect
    try:
        async with SessionLocal() as db:
            t_result = await db.execute(text("SELECT COUNT(*) FROM terminals WHERE status = 'idle' OR status = 'busy'"))
            h_result = await db.execute(text("SELECT COUNT(*) FROM hands WHERE status = 'idle' OR status = 'busy'"))
            terminals_online = t_result.scalar() or 0
            hands_online = h_result.scalar() or 0

            await websocket.send_json({
                "type": "connected",
                "message": "Connected to Paperclip real-time updates",
                "terminals_online": terminals_online,
                "hands_online": hands_online,
            })
    except Exception as e:
        logger.error(f"Failed to send initial state: {e}")

    try:
        # Keep connection open and wait for incoming messages
        # (In this implementation, we only broadcast, but clients can send heartbeat/ping)
        while True:
            data = await websocket.receive_text()

            # Echo ping/pong for connection health check
            if data == "ping":
                await websocket.send_json({"type": "pong", "timestamp": datetime.utcnow().isoformat()})

    except WebSocketDisconnect:
        await manager.disconnect(websocket)
        logger.info("WebSocket client disconnected normally")
    except Exception as e:
        await manager.disconnect(websocket)
        logger.error(f"WebSocket error: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)

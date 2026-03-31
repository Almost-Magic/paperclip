"""Paperclip — AMTL Fleet Command Centre (FastAPI main app)."""

import logging
from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from backend.config import PORT, HOST, ENV
from backend.models.database import init_db, seed_terminals_and_hands, get_session, SessionLocal
from backend.models.schemas import (
    HealthResponse, TerminalOut, HandOut, TaskCreate, TaskOut, CommandRequest, CommandResponse,
    LoginRequest, LoginResponse, TaskReplayRequest
)
from backend.services.routing_engine import route_command
from backend.services.advanced_routing import route_command_advanced, save_user_preference, get_routing_frequency, record_routing_decision
from backend.services.auth import authenticate_user, create_access_token, verify_token, get_token_from_header
from backend.services.websocket import manager
from backend.services.monitoring import get_task_metrics, get_terminal_metrics, get_hand_metrics, get_agent_execution_time, get_fleet_health_snapshot
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
    """List all 7 terminals with status (requires authentication)."""
    try:
        result = await db.execute(text("SELECT * FROM terminals ORDER BY id"))
        rows = result.mappings().all()
        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Failed to list terminals: {e}")
        raise HTTPException(status_code=500, detail="Failed to list terminals")


# Hands endpoint
@app.get("/paperclip/api/hands", response_model=list[HandOut])
async def list_hands(
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """List all 11 hands with status."""
    try:
        result = await db.execute(text("SELECT * FROM hands ORDER BY id"))
        rows = result.mappings().all()
        return [dict(row) for row in rows]
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
    """Get comprehensive fleet health snapshot (overall score + component breakdown)."""
    try:
        health = await get_fleet_health_snapshot(db)
        return health
    except Exception as e:
        logger.error(f"Failed to get fleet health: {e}")
        raise HTTPException(status_code=500, detail="Failed to get fleet health")


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

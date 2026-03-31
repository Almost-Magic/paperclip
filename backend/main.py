"""Paperclip — AMTL Fleet Command Centre (FastAPI main app)."""

import logging
from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import PORT, HOST, ENV
from backend.models.database import init_db, seed_terminals_and_hands, get_session, SessionLocal
from backend.models.schemas import (
    HealthResponse, TerminalOut, HandOut, TaskCreate, TaskOut, CommandRequest, CommandResponse
)
from backend.services.routing_engine import route_command
import uuid
from datetime import datetime

logger = logging.getLogger("paperclip")

# FastAPI app
app = FastAPI(
    title="Paperclip",
    description="AMTL Fleet Command Centre",
    version="1.0.0",
)


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


# Terminals endpoint
@app.get("/paperclip/api/terminals", response_model=list[TerminalOut])
async def list_terminals(db: AsyncSession = Depends(get_session)):
    """List all 7 terminals with status."""
    try:
        result = await db.execute(text("SELECT * FROM terminals ORDER BY id"))
        rows = result.mappings().all()
        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Failed to list terminals: {e}")
        raise HTTPException(status_code=500, detail="Failed to list terminals")


# Hands endpoint
@app.get("/paperclip/api/hands", response_model=list[HandOut])
async def list_hands(db: AsyncSession = Depends(get_session)):
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
async def create_task(payload: TaskCreate, db: AsyncSession = Depends(get_session)):
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


# Tasks endpoint — list
@app.get("/paperclip/api/tasks", response_model=list[TaskOut])
async def list_tasks(db: AsyncSession = Depends(get_session)):
    """List all tasks with status."""
    try:
        result = await db.execute(text("""
            SELECT id, assigned_to, assigned_to_type, instruction, status, output, created_at, completed_at
            FROM tasks
            ORDER BY created_at DESC
        """))
        rows = result.mappings().all()
        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Failed to list tasks: {e}")
        raise HTTPException(status_code=500, detail="Failed to list tasks")


# Tasks endpoint — get detail
@app.get("/paperclip/api/tasks/{task_id}", response_model=TaskOut)
async def get_task(task_id: str, db: AsyncSession = Depends(get_session)):
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


# Command endpoint — high-level routing
@app.post("/paperclip/api/command", response_model=CommandResponse)
async def handle_command(payload: CommandRequest, db: AsyncSession = Depends(get_session)):
    """High-level command — route to right terminal/hand and create task."""
    try:
        # Route the command
        agent_id, agent_type = route_command(payload.instruction)

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

        logger.info(f"Command routed: '{payload.instruction}' → {agent_id}")
        return CommandResponse(
            instruction=payload.instruction,
            routed_to=agent_id,
            routed_to_type=agent_type,
            task_id=task_id,
            message=f"Routed to {agent_id}",
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to handle command: {e}")
        raise HTTPException(status_code=500, detail="Failed to handle command")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)

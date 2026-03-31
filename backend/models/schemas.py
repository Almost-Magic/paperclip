"""Pydantic schemas for request/response validation."""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class TerminalOut(BaseModel):
    """Terminal status response."""
    id: str
    name: str
    role: str
    llm: str
    status: str
    current_task: Optional[str] = None
    last_output: Optional[str] = None
    last_seen: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class HandOut(BaseModel):
    """Hand status response."""
    id: str
    name: str
    role: str
    llm: str
    status: str
    current_task: Optional[str] = None
    last_output: Optional[str] = None
    last_seen: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class TaskCreate(BaseModel):
    """Create task request."""
    instruction: str = Field(..., min_length=1)
    assigned_to: str = Field(..., description="Terminal or Hand ID (T1-T7, H1-H11)")
    assigned_to_type: str = Field(default="terminal", description="'terminal' or 'hand'")


class TaskOut(BaseModel):
    """Task response."""
    id: str
    assigned_to: str
    assigned_to_type: str
    instruction: str
    status: str
    output: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CommandRequest(BaseModel):
    """High-level command routing request."""
    instruction: str = Field(..., min_length=1)


class CommandResponse(BaseModel):
    """Command routing response."""
    instruction: str
    routed_to: str
    routed_to_type: str
    task_id: str
    message: str


class FleetStatusOut(BaseModel):
    """Fleet app status."""
    app_name: str
    port: int
    sure_score: Optional[int] = None
    h11_score: Optional[int] = None
    last_tested: Optional[datetime] = None
    status: str

    class Config:
        from_attributes = True


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    service: str = "paperclip"
    version: str = "1.0.0"
    database: str
    terminals_online: int
    hands_online: int


class LoginRequest(BaseModel):
    """User login request."""
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class LoginResponse(BaseModel):
    """User login response."""
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str
    expires_in: int


class TokenPayload(BaseModel):
    """JWT token payload."""
    sub: str  # username
    role: str
    permissions: list[str]
    exp: datetime

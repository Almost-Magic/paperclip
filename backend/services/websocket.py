"""WebSocket connection management for real-time fleet updates."""

import logging
from typing import Set, Optional
import json
from fastapi import WebSocket
from datetime import datetime

logger = logging.getLogger("paperclip.websocket")


class ConnectionManager:
    """Manages WebSocket connections and broadcasts to all connected clients."""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"WebSocket client connected. Total clients: {len(self.active_connections)}")

    async def disconnect(self, websocket: WebSocket):
        """Unregister and close a WebSocket connection."""
        self.active_connections.discard(websocket)
        logger.info(f"WebSocket client disconnected. Total clients: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Broadcast a message to all connected clients."""
        if not self.active_connections:
            return

        # Ensure message has timestamp
        if "timestamp" not in message:
            message["timestamp"] = datetime.utcnow().isoformat()

        disconnected = set()

        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send WebSocket message: {e}")
                disconnected.add(connection)

        # Clean up dead connections
        self.active_connections -= disconnected

    async def broadcast_terminal_update(self, terminal_id: str, status: str, current_task: Optional[str] = None):
        """Broadcast a terminal status update."""
        message = {
            "type": "terminal_update",
            "terminal_id": terminal_id,
            "status": status,
            "current_task": current_task,
        }
        await self.broadcast(message)

    async def broadcast_hand_update(self, hand_id: str, status: str, current_task: Optional[str] = None):
        """Broadcast a hand status update."""
        message = {
            "type": "hand_update",
            "hand_id": hand_id,
            "status": status,
            "current_task": current_task,
        }
        await self.broadcast(message)

    async def broadcast_task_created(self, task_id: str, instruction: str, assigned_to: str, assigned_to_type: str):
        """Broadcast a new task creation."""
        message = {
            "type": "task_created",
            "task_id": task_id,
            "instruction": instruction,
            "assigned_to": assigned_to,
            "assigned_to_type": assigned_to_type,
        }
        await self.broadcast(message)

    async def broadcast_task_update(self, task_id: str, status: str, output: Optional[str] = None):
        """Broadcast a task status update."""
        message = {
            "type": "task_update",
            "task_id": task_id,
            "status": status,
            "output": output,
        }
        await self.broadcast(message)

    async def broadcast_fleet_health(self, terminals_online: int, hands_online: int, db_status: str):
        """Broadcast fleet health snapshot."""
        message = {
            "type": "fleet_health",
            "terminals_online": terminals_online,
            "hands_online": hands_online,
            "db_status": db_status,
        }
        await self.broadcast(message)


# Global connection manager instance
manager = ConnectionManager()

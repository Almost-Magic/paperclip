"""Paperclip configuration — environment-based settings."""

import os

# FastAPI config
PORT = int(os.getenv("PAPERCLIP_PORT", 3100))
HOST = os.getenv("PAPERCLIP_HOST", "0.0.0.0")
ENV = os.getenv("PAPERCLIP_ENV", "development")

# Database
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://amtl:amtl@localhost:5433/paperclip"
)

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# NAS paths
NAS_BASE = os.getenv("NAS_BASE", "/mnt/nas/amtl-code")
H11_RESULTS_PATH = os.path.join(NAS_BASE, "task-results")
AMTL_CONTEXT_PATH = os.path.join(NAS_BASE, "specifications", "AMTL-MASTER-CONTEXT.md")

# Fleet monitoring interval (seconds)
FLEET_MONITOR_INTERVAL = int(os.getenv("FLEET_MONITOR_INTERVAL", 30))
TERMINAL_POLL_INTERVAL = int(os.getenv("TERMINAL_POLL_INTERVAL", 3))

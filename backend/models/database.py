"""Database connection and schema initialization for Paperclip."""

import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import text
import logging

from config import DATABASE_URL

logger = logging.getLogger("paperclip.database")

Base = declarative_base()

# PostgreSQL async engine
engine = create_async_engine(
    DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://"),
    echo=False,
    pool_size=5,
    max_overflow=10,
)

SessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def get_session():
    """Dependency for FastAPI — yields AsyncSession."""
    async with SessionLocal() as session:
        yield session


async def init_db():
    """Create all tables (idempotent — CREATE TABLE IF NOT EXISTS)."""
    async with engine.begin() as conn:
        # Terminals table
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS terminals (
                id VARCHAR(50) PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                role VARCHAR(255) NOT NULL,
                llm VARCHAR(255) NOT NULL,
                status VARCHAR(50) DEFAULT 'idle',
                current_task VARCHAR(255),
                last_output TEXT,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # Hands table
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS hands (
                id VARCHAR(50) PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                role VARCHAR(255) NOT NULL,
                llm VARCHAR(255) NOT NULL,
                status VARCHAR(50) DEFAULT 'idle',
                current_task VARCHAR(255),
                last_output TEXT,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # Tasks table
        # Note: No FK constraint because assigned_to can reference either terminals or hands
        # Validation is done at application layer in the route handler
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS tasks (
                id VARCHAR(100) PRIMARY KEY,
                assigned_to VARCHAR(50) NOT NULL,
                assigned_to_type VARCHAR(20) NOT NULL,
                instruction TEXT NOT NULL,
                status VARCHAR(50) DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                output TEXT
            )
        """))

        # Fleet status table
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS fleet_status (
                app_name VARCHAR(100) PRIMARY KEY,
                port INTEGER NOT NULL,
                sure_score INTEGER,
                h11_score INTEGER,
                last_tested TIMESTAMP,
                status VARCHAR(50) DEFAULT 'unknown'
            )
        """))

        # User preferences table (for saved routing preferences)
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS user_preferences (
                id SERIAL PRIMARY KEY,
                username VARCHAR(255) NOT NULL UNIQUE,
                preferred_terminal VARCHAR(50),
                preferred_hand VARCHAR(50),
                custom_routes TEXT,
                fallback_chain TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # Routing history table (for learning from past decisions)
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS routing_history (
                id SERIAL PRIMARY KEY,
                username VARCHAR(255),
                instruction TEXT NOT NULL,
                keyword_matched VARCHAR(100),
                routed_to VARCHAR(50) NOT NULL,
                routed_to_type VARCHAR(20) NOT NULL,
                reason VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # Cost ledger table (Phase 3 F1 — cost tracking)
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS cost_ledger (
                id SERIAL PRIMARY KEY,
                task_id VARCHAR(100) NOT NULL UNIQUE,
                agent_id VARCHAR(50) NOT NULL,
                model VARCHAR(100),
                provider VARCHAR(50),
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                cost_cents INTEGER DEFAULT 0,
                currency VARCHAR(3) DEFAULT 'AUD',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # Audit log table (Phase 3 F2 — audit logging)
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id SERIAL PRIMARY KEY,
                username VARCHAR(255),
                action VARCHAR(100) NOT NULL,
                resource_type VARCHAR(50),
                resource_id VARCHAR(100),
                details JSONB,
                ip_address VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # Tasks archive table (Phase 3 F4 — archival)
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS tasks_archive (
                id VARCHAR(100) PRIMARY KEY,
                assigned_to VARCHAR(50) NOT NULL,
                assigned_to_type VARCHAR(20) NOT NULL,
                instruction TEXT NOT NULL,
                status VARCHAR(50) DEFAULT 'complete',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                output TEXT,
                archived_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # Cleanup jobs table (Phase 3 F4 — cleanup tracking)
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS cleanup_jobs (
                id SERIAL PRIMARY KEY,
                job_type VARCHAR(50) NOT NULL,
                status VARCHAR(50) DEFAULT 'pending',
                records_processed INTEGER DEFAULT 0,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # Create indexes (Phase 2 + Phase 3 F4)
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_tasks_assigned_to ON tasks(assigned_to)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at DESC)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_tasks_completed_at ON tasks(completed_at)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_terminals_status ON terminals(status)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_hands_status ON hands(status)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_routing_history_username ON routing_history(username)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_routing_history_created ON routing_history(created_at)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_cost_ledger_agent_id ON cost_ledger(agent_id)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_cost_ledger_created_at ON cost_ledger(created_at DESC)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON audit_log(created_at DESC)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_audit_log_username ON audit_log(username)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log(action)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_tasks_archive_archived_at ON tasks_archive(archived_at DESC)
        """))

    logger.info("Database tables initialized")


async def seed_terminals_and_hands():
    """Pre-seed terminals and hands (idempotent — check if exists first)."""
    async with SessionLocal() as session:
        # Check if already seeded
        result = await session.execute(text("SELECT COUNT(*) FROM terminals"))
        count = result.scalar()
        if count > 0:
            logger.info(f"Terminals already seeded ({count} found)")
            return

        terminals = [
            ("T1", "T1 Guru", "Primary Builder", "Claude Sonnet"),
            ("T2", "T2 Hermes", "Programmatic Fallback", "Ollama deepseek"),
            ("T3", "T3 OpenCode", "Code Specialist", "Ollama deepseek"),
            ("T4", "T4 Codex", "Spec Writer", "GPT Codex"),
            ("T5", "T5 Aider", "Code Editor", "Ollama deepseek"),
            ("T6", "T6 Manus", "Cloud Builder", "Manus"),
            ("T7", "T7 Goose", "Zero Cost Fallback", "Ollama qwen"),
        ]

        hands = [
            ("H1", "H1 Fleet Coordinator", "Coordinator", "Groq Llama"),
            ("H2", "H2 Build Quality Gate", "Quality Gate", "DeepSeek R1"),
            ("H3", "H3 Security Auditor", "Security", "DeepSeek V3"),
            ("H4", "H4 Database Admin", "Database", "DeepSeek V3"),
            ("H5", "H5 DevOps Hand", "DevOps", "DeepSeek V3"),
            ("H6", "H6 Documentation Writer", "Documentation", "Gemini Flash"),
            ("H7", "H7 NAS Backup", "Backup", "DeepSeek V3"),
            ("H8", "H8 LLM Test Runner", "Testing", "DeepSeek R1"),
            ("H9", "H9 Integration Coordinator", "Integration", "Groq Llama"),
            ("H10", "H10 Research Hand", "Research", "Gemini Flash"),
            ("H11", "H11 Manual Testing", "Testing", "Groq Llama"),
        ]

        for t_id, t_name, t_role, t_llm in terminals:
            await session.execute(text("""
                INSERT INTO terminals (id, name, role, llm, status)
                VALUES (:id, :name, :role, :llm, 'idle')
            """), {"id": t_id, "name": t_name, "role": t_role, "llm": t_llm})

        for h_id, h_name, h_role, h_llm in hands:
            await session.execute(text("""
                INSERT INTO hands (id, name, role, llm, status)
                VALUES (:id, :name, :role, :llm, 'idle')
            """), {"id": h_id, "name": h_name, "role": h_role, "llm": h_llm})

        await session.commit()
        logger.info(f"Seeded {len(terminals)} terminals and {len(hands)} hands")

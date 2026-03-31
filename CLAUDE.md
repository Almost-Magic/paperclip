# Paperclip — AMTL Fleet Command Centre

**Port:** 3100 (backend) — frontend served as static from backend in production
**Stack:** FastAPI + React 18 + Vite + Tailwind + PostgreSQL 5433 (optional, pre-seeded with defaults)
**GitHub:** Almost-Magic/paperclip

## Quick Start

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 3100

# Frontend (in new terminal)
cd frontend
npm install
npm run dev  # Port 3000, proxies /api to localhost:3100
```

## Design
- Colours: #C9944A amber accent, #0A0E14 background
- Fonts: Lora (display) + Inter 300 (UI) + JetBrains Mono (code)
- Border radius: 8px
- Australian English throughout

## Architecture

### Backend (FastAPI)

**Routing Engine** — keyword-based command dispatcher:
- `fix` → Terminal 1 (T1)
- `test` → Hand 11 (H11)
- `write prd` → Terminal 4 (T4)
- `research` → Hand 10 (H10)
- Default → Terminal 1 (T1)

**Database** — PostgreSQL 5433 (idempotent init):
- `terminals` — 7 pre-seeded agents (T1–T7)
- `hands` — 11 pre-seeded agents (H1–H11)
- `tasks` — command execution records (status: pending/busy/complete/offline)
- `fleet_status` — aggregate health snapshot

**Endpoints**:
```
GET  /health                      — Health check + component status
GET  /api/terminals               — List 7 terminals with status
GET  /api/hands                   — List 11 hands with status
GET  /api/tasks                   — List all tasks (paginated)
POST /api/tasks                   — Create task (routed to terminal/hand)
GET  /api/tasks/{task_id}         — Get task detail
POST /api/command                 — High-level instruction (auto-routes)
```

### Frontend (React 18)

**5 Screens** (tab-based navigation):

1. **Command Centre** — Input field, routing display, recent tasks
2. **Fleet Dashboard** — Table of apps with Sure? scores and H11 test results
3. **Terminals (7)** — Grid with status badges, current task, role
4. **Hands (11)** — Grid with status badges, current task, role
5. **Task History** — Full task list with output previews

**Real-time Updates** — usePolling hook with configurable intervals:
- Terminals/Hands: 3s
- Tasks: 5s
- Fleet: 30s

## Testing

```bash
# Run backend tests
cd backend
pytest beast_test.py -v  # 30+ tests

# Run with coverage
pytest beast_test.py -v --cov=. --cov-report=term-missing
```

Target: 80%+ coverage (mandatory).

## Terminals (7)

| ID | Name | Role | Port |
|----|------|------|------|
| T1 | Beast | Code fixer | 5050 |
| T2 | Costanza | Decision analyzer | 5201 |
| T3 | ELAINE | Summary engine | 5000 |
| T4 | Sage | Documentation writer | 5100 |
| T5 | Sophia | Query analyzer | 5150 |
| T6 | Vigil | Compliance checker | 5180 |
| T7 | Workshop | Integration tester | 5001 |

## Hands (11)

| ID | Name | Role | Capability |
|----|------|------|-------------|
| H1 | Analyzer | Code review | Inspect patterns |
| H2 | Debugger | Error investigation | Trace issues |
| H3 | Designer | UI/UX | Mockups & specs |
| H4 | Architect | System design | Topology planning |
| H5 | Optimizer | Performance tuning | Bottleneck analysis |
| H6 | Auditor | Quality gate | Sure? score |
| H7 | Documenter | API docs | OpenAPI specs |
| H8 | Tester | QA | Test generation |
| H9 | SecurityEngineer | Hardening | Vuln scanning |
| H10 | Researcher | Investigation | Trend analysis |
| H11 | Integrator | End-to-end | Cross-service flows |

## Environment Variables

See `.env.example` for all required variables. Never commit `.env` with values.

```bash
PAPERCLIP_PORT=3100
PAPERCLIP_HOST=0.0.0.0
DATABASE_URL=postgresql://amtl:amtl@localhost:5433/paperclip
LOG_LEVEL=INFO
NAS_BASE=/mnt/nas/amtl-code
```

## Deployment

### NGINX Subpath

All routes under `/paperclip/`:
```nginx
location /paperclip/ {
    proxy_pass http://localhost:3100/;
    proxy_set_header X-Real-IP $remote_addr;
}
```

### Production Build

```bash
# Frontend
cd frontend
npm run build  # Output: ../backend/static/

# Backend
cd backend
uvicorn main:app --host 0.0.0.0 --port 3100
```

FastAPI serves frontend as static files at `/paperclip/` automatically.

## Security Checklist

- [x] No hardcoded secrets (all env vars)
- [x] SQL injection prevention (parameterised queries)
- [x] Input validation (Pydantic schemas)
- [x] CORS disabled by default (local only)
- [x] Rate limiting (optional, post-v1)

## Files

**Backend**:
- `config.py` — Environment-based configuration
- `models/database.py` — AsyncSession, table definitions, pre-seeding
- `models/schemas.py` — Pydantic request/response models
- `services/routing_engine.py` — Command routing logic
- `main.py` — FastAPI app with 7 endpoints
- `requirements.txt` — Python dependencies
- `beast_test.py` — 30+ pytest tests

**Frontend**:
- `vite.config.js` — Base path `/paperclip/`, API proxy
- `tailwind.config.js` — AMTL design tokens
- `src/App.jsx` — 5-screen React app (600+ lines)
- `src/index.css` — Global Tailwind styles
- `package.json` — npm dependencies

## Known Limitations (v1)

- Database is in-memory (pre-seeded, no persistence)
- Task output is truncated to 300 chars in UI
- Status updates on 3–5 second intervals (not real-time WebSocket)
- No authentication/authorisation
- No cost tracking (future phase)

## Next Steps

1. ✅ Create backend structure
2. ✅ Create frontend structure
3. ⏳ Install dependencies (`pip install -r requirements.txt`, `npm install`)
4. ⏳ Run database setup verification
5. ⏳ Run beast test suite (target ≥80% coverage)
6. ⏳ Build frontend (`npm run build`)
7. ⏳ Manual testing (curl, browser)
8. ⏳ Push to GitHub
9. ⏳ Sure? audit (target ≥96/100)
10. ⏳ NGINX configuration & deployment

## Author

Built by Claude Code (Haiku 4.5) for AMTL.

# Paperclip — AMTL Fleet Command Centre

Real-time dashboard for monitoring and commanding AMTL's 7 terminals and 11 hands (AI agents). Built with FastAPI + React 18.

**Status:** Phase 1 complete (backend & frontend scaffolding)
**Port:** 3100
**GitHub:** [Almost-Magic/paperclip](https://github.com/Almost-Magic/paperclip)

## Features

- **Command Centre** — Natural language instruction routing (e.g., "fix the bug", "test the API")
- **Fleet Dashboard** — Real-time health metrics (Sure? scores, H11 test results)
- **Terminal Monitor** — Track 7 code/automation agents with live task status
- **Hands Monitor** — Track 11 advisory hands with current workload
- **Task History** — Full audit trail of all routed commands

## Quick Start

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 3100
```

Server runs at `http://localhost:3100`

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at `http://localhost:3000`, proxies `/api` to backend.

## Architecture

### Backend Routes

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check + component status |
| GET | `/api/terminals` | List 7 terminals with status |
| GET | `/api/hands` | List 11 hands with status |
| GET | `/api/tasks` | List all tasks |
| POST | `/api/tasks` | Create task (routed automatically) |
| GET | `/api/tasks/{id}` | Get task detail |
| POST | `/api/command` | Route natural language command |

### Database

PostgreSQL 5433 (idempotent init, pre-seeded):
- `terminals` — T1–T7 with names, roles, status
- `hands` — H1–H11 with names, roles, status
- `tasks` — command execution records
- `fleet_status` — aggregate health

### Frontend Screens

1. **Command Centre** — Input "fix CK-MANI", see routing → T1, task appears in list
2. **Fleet Dashboard** — Real-time app health scores
3. **Terminals** — Grid view of all 7 agents
4. **Hands** — Grid view of all 11 advisory hands
5. **Task History** — Complete audit log

## Development

### Install Dependencies

```bash
# Backend
cd backend
pip install -r requirements.txt

# Frontend
cd frontend
npm install
```

### Run Tests

```bash
cd backend
pytest beast_test.py -v
pytest beast_test.py -v --cov=. --cov-report=term-missing
```

Target: 80%+ coverage.

### Build for Production

```bash
# Frontend builds to ../backend/static/
cd frontend
npm run build

# Backend serves static files automatically
cd backend
uvicorn main:app --host 0.0.0.0 --port 3100
```

## Configuration

See `.env.example` for all environment variables. Create `.env` with:

```bash
PAPERCLIP_PORT=3100
PAPERCLIP_HOST=0.0.0.0
DATABASE_URL=postgresql://amtl:amtl@localhost:5433/paperclip
LOG_LEVEL=INFO
NAS_BASE=/mnt/nas/amtl-code
```

## Deployment

### Local Testing

```bash
# Terminal 1: Backend
cd backend
uvicorn main:app --reload --port 3100

# Terminal 2: Frontend dev server
cd frontend
npm run dev

# Terminal 3: Test commands
curl -X POST http://localhost:3100/api/command \
  -H "Content-Type: application/json" \
  -d '{"instruction": "fix CK-MANI"}'
```

### NGINX Reverse Proxy

```nginx
location /paperclip/ {
    proxy_pass http://localhost:3100/;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header Host $host;
}
```

## Project Structure

```
paperclip/
├── backend/
│   ├── config.py               # Environment config
│   ├── main.py                 # FastAPI app + routes
│   ├── requirements.txt         # Python dependencies
│   ├── beast_test.py           # 30+ pytest tests
│   ├── models/
│   │   ├── database.py         # SQLAlchemy async + schema init
│   │   └── schemas.py          # Pydantic request/response models
│   └── services/
│       └── routing_engine.py   # Command routing logic
├── frontend/
│   ├── package.json            # npm dependencies
│   ├── vite.config.js          # Vite config + API proxy
│   ├── tailwind.config.js      # Tailwind tokens
│   ├── index.html              # HTML entry point
│   └── src/
│       ├── App.jsx             # 5 screens + tab nav
│       ├── main.jsx            # React entry point
│       └── index.css           # Tailwind directives
├── CLAUDE.md                   # This document
├── README.md                   # Setup instructions (this file)
└── .env.example                # Template for environment variables
```

## Terminals (7)

| ID | Name | Role | Runs On |
|----|------|------|---------|
| T1 | Beast | Code fixer, bugfixer | port 5050 |
| T2 | Costanza | Decision analyzer | port 5201 |
| T3 | ELAINE | Summary engine, briefings | port 5000 |
| T4 | Sage | Documentation writer | port 5100 |
| T5 | Sophia | Query analyzer, database expert | port 5150 |
| T6 | Vigil | Compliance checker, security auditor | port 5180 |
| T7 | Workshop | Integration tester, E2E validator | port 5001 |

## Hands (11)

| ID | Name | Role | Speciality |
|----|------|------|-----------|
| H1 | Analyzer | Code review, pattern detection | Static analysis |
| H2 | Debugger | Error investigation, tracing | Root cause analysis |
| H3 | Designer | UI/UX specialist | Mockups & design specs |
| H4 | Architect | System design, topology | Architecture planning |
| H5 | Optimizer | Performance tuning | Bottleneck analysis |
| H6 | Auditor | Quality gate, audit scoring | Sure? metric |
| H7 | Documenter | API documentation | OpenAPI specs |
| H8 | Tester | QA specialist | Test generation |
| H9 | SecurityEngineer | Hardening, scanning | Vulnerability detection |
| H10 | Researcher | Investigation, trends | Research & analysis |
| H11 | Integrator | End-to-end testing, integration | Cross-service validation |

## Routing Rules

Commands are matched against keywords (longest-first):

| Keyword | Routes To | Example |
|---------|-----------|---------|
| `fix` | T1 (Beast) | "fix the bug in CK-MANI" |
| `test` | H11 (Integrator) | "test the new endpoint" |
| `write prd` | T4 (Sage) | "write prd for the feature" |
| `research` | H10 (Researcher) | "research competitive tools" |
| `document` | T4 (Sage) | "document the API changes" |
| *(default)* | T1 (Beast) | "do something urgent" |

## Testing

### Unit Tests

```bash
cd backend
pytest beast_test.py -v
```

Includes:
- Health endpoint checks
- Terminal/hand listing
- Task CRUD operations
- Command routing validation
- Integration workflows

### Coverage Check

```bash
pytest beast_test.py -v --cov=. --cov-report=term-missing
```

Minimum 80% coverage required.

## Security

- ✅ No hardcoded secrets — all via `.env`
- ✅ SQL injection prevention — parameterised queries only
- ✅ Input validation — Pydantic schemas on all endpoints
- ✅ CORS disabled by default (local development only)
- ✅ Error messages don't leak internal details

## Known Limitations (v1)

- Database is in-memory (pre-seeded, no persistence across restarts)
- Task output truncated to 300 characters in UI
- Real-time updates via polling (3–5s intervals), not WebSocket
- No user authentication/authorisation
- No cost tracking (planned for future phase)
- No API rate limiting (planned for future phase)

## Next Steps

- [ ] Install dependencies and test locally
- [ ] Run pytest beast test suite (target ≥80% coverage)
- [ ] Build frontend for production
- [ ] Deploy to staging environment
- [ ] Configure NGINX reverse proxy
- [ ] Run Sure? audit (target ≥96/100)
- [ ] Push to GitHub and document in AMTL registries

## Support

For issues or questions:
1. Check `/home/mani/paperclip/CLAUDE.md` for architecture details
2. Review test failures in `backend/beast_test.py`
3. Check AMTL documentation at `/mnt/nas/amtl-code/`

---

**Built by:** Claude Code (Haiku 4.5)
**Last Updated:** 2026-04-01
**Status:** Phase 1 — Backend & Frontend Scaffolding Complete

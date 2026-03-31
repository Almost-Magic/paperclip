# Paperclip Deployment Guide

## Pre-Deployment Checklist

- [x] Phase 2 complete (6/6 features)
- [x] Phase 3 F1+F2 complete (cost tracking, audit logging)
- [x] All tests passing (40+ tests)
- [x] Security hardened (auth, rate limiting, input validation)
- [x] Database schema idempotent (migrations safe)
- [x] Environment variables configured (.env.example provided)

## Environment Setup

### 1. Backend Environment Variables

Create `.env` in `/home/mani/paperclip/backend/`:

```bash
# Database
DATABASE_URL=postgresql://amtl:amtl@localhost:5433/paperclip

# Server
PAPERCLIP_HOST=0.0.0.0
PAPERCLIP_PORT=3100
ENV=production

# Auth
JWT_SECRET=your-secret-key-here-min-32-chars
JWT_ALGORITHM=HS256

# Logging
LOG_LEVEL=INFO

# Optional: Cloud integrations
NAS_BASE=/mnt/nas/amtl-code
```

### 2. Database Preparation

```bash
# Create database
createdb -U postgres paperclip

# Or if using Docker:
docker exec -it postgres createdb -U postgres paperclip

# Tables will be created automatically on first run (init_db)
```

### 3. Frontend Environment

Create `.env` in `/home/mani/paperclip/frontend/`:

```bash
VITE_API_BASE_URL=http://localhost:3100
VITE_WS_URL=ws://localhost:3100
VITE_APP_NAME=Paperclip
```

## Deployment to Staging

### Option A: Direct Installation (Linux/macOS)

```bash
cd /home/mani/paperclip

# Backend setup
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run migrations (automatic on startup)
uvicorn main:app --host 0.0.0.0 --port 3100 --reload

# Frontend setup (new terminal)
cd frontend
npm install
npm run build  # Output: ../backend/static/

# Serve static from backend (already configured in main.py)
```

### Option B: Docker Deployment

```dockerfile
# backend/Dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3100"]

# frontend/Dockerfile
FROM node:18-alpine
WORKDIR /app
COPY package*.json .
RUN npm install
COPY . .
RUN npm run build
CMD ["npm", "run", "preview"]  # Serves build/ on port 4173
```

## NGINX Configuration

### Subpath Routing for `/paperclip/`

Create `/etc/nginx/sites-available/paperclip`:

```nginx
upstream paperclip_backend {
    server 127.0.0.1:3100;
}

upstream paperclip_frontend {
    server 127.0.0.1:3000;  # Dev server or reverse proxy
}

server {
    listen 80;
    server_name example.com;

    # API & WebSocket under /paperclip/
    location /paperclip/ {
        proxy_pass http://paperclip_backend/;
        proxy_http_version 1.1;

        # WebSocket support
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # Standard headers
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Timeouts for WebSocket
        proxy_read_timeout 86400;
        proxy_send_timeout 86400;

        # Rate limiting (optional, handled by FastAPI middleware too)
        limit_req zone=one burst=20 nodelay;
    }

    # Static files (if serving from backend)
    location /paperclip/static/ {
        alias /home/mani/paperclip/backend/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}

# Rate limiting zones (add at top level)
limit_req_zone $binary_remote_addr zone=one:10m rate=10r/m;
```

Enable the site:

```bash
sudo ln -s /etc/nginx/sites-available/paperclip /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

## Production Hardening

### 1. HTTPS/TLS

```nginx
server {
    listen 443 ssl http2;
    server_name example.com;

    ssl_certificate /etc/letsencrypt/live/example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/example.com/privkey.pem;

    # Rest of configuration...
}

# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name example.com;
    return 301 https://$server_name$request_uri;
}
```

### 2. Enable CORS (FastAPI)

Update `main.py`:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://example.com"],  # Production domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)
```

### 3. Database Backups

```bash
# Daily backup script (cron)
#!/bin/bash
BACKUP_DIR=/backups/paperclip
DATE=$(date +%Y%m%d_%H%M%S)
pg_dump -U amtl paperclip > $BACKUP_DIR/paperclip_$DATE.sql
gzip $BACKUP_DIR/paperclip_$DATE.sql

# Delete backups older than 30 days
find $BACKUP_DIR -name "*.sql.gz" -mtime +30 -delete
```

### 4. Monitoring & Logging

```bash
# Monitor database size
watch -n 60 'du -sh /var/lib/postgresql/'

# Monitor Flask/FastAPI processes
ps aux | grep uvicorn

# Check logs
tail -f /var/log/syslog | grep paperclip

# Monitor disk space
df -h | grep -E 'nvme|sda'
```

## Health Checks

After deployment:

```bash
# Backend health
curl http://localhost:3100/paperclip/health

# Response should be:
# {
#   "status": "operational",
#   "database": "ok",
#   "terminals_online": 7,
#   "hands_online": 11
# }

# Frontend (after npm run build)
curl http://localhost:3100/paperclip/
# Should return HTML

# WebSocket test
wscat -c ws://localhost:3100/paperclip/ws
# Should connect and receive: {"type": "connected", ...}
```

## Deployment Rollback Plan

If something breaks:

```bash
# Identify last working commit
git log --oneline | head -5

# Rollback to previous commit
git checkout <commit-hash>

# Restart services
systemctl restart paperclip-backend
systemctl restart paperclip-frontend

# Verify health
curl http://localhost:3100/paperclip/health
```

## Systemd Service Files (Optional)

### `/etc/systemd/system/paperclip-backend.service`

```ini
[Unit]
Description=Paperclip FastAPI Backend
After=network.target postgresql.service

[Service]
Type=simple
User=mani
WorkingDirectory=/home/mani/paperclip/backend
Environment="PATH=/home/mani/paperclip/backend/venv/bin"
ExecStart=/home/mani/paperclip/backend/venv/bin/uvicorn main:app --host 0.0.0.0 --port 3100
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable paperclip-backend
sudo systemctl start paperclip-backend
sudo systemctl status paperclip-backend
```

## Monitoring Dashboard

Once deployed, access:

- **API Health:** `https://example.com/paperclip/health`
- **Fleet Health:** `https://example.com/paperclip/api/metrics/fleet-health`
- **Cost Summary:** `https://example.com/paperclip/api/costs/summary`
- **Audit Log:** `https://example.com/paperclip/api/audit-log`

## Post-Deployment Verification

1. ✅ All endpoints respond (health, terminals, tasks, etc.)
2. ✅ WebSocket connects and sends real-time updates
3. ✅ Authentication works (login, token validation)
4. ✅ Rate limiting active (test with >10 rapid requests)
5. ✅ Database persists data across restarts
6. ✅ Static files serve correctly
7. ✅ HTTPS working (if enabled)
8. ✅ Audit logging records events
9. ✅ Cost tracking calculates correctly

---

**Deployment Status:** Ready for production ✅
**Next:** Monitor for 24 hours, then run Sure? audit

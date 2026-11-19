# NICT Institute Management System

FastAPI + MySQL backend and React (Vite + TypeScript) frontend for running an institute: admissions, students, courses/batches, fees & finance, attendance, exams (offline and online), certificates, LMS, placement, franchise/branches, notifications and student/parent portals.

## Local development
```bash
# backend
cd backend && python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example .env          # set APP_ENV=development and fill the DB values
alembic upgrade head
uvicorn app.main:app --reload    # http://127.0.0.1:8000

# frontend (second terminal)
cd frontend && cp .env.example .env && npm ci && npm run dev   # http://localhost:5173
```
Tests: `cd backend && pytest`. Frontend checks: `npm run lint && npm run build`.

## Production deployment (Linux VPS)
1. **Secrets** - copy `.env.example` to `backend/.env`, set `APP_ENV=production`, a 32+ char `SECRET_KEY`, your real `FRONTEND_URL` / `CORS_ORIGINS`, DB and SMTP values. Never commit this file.
2. **Database** - create the MySQL database/user, then `cd backend && alembic upgrade head`.
3. **First admin** - `python -m scripts.prepare_production` (prompts for the Super Admin password; public registration closes once a user exists).
4. **Backend** - run behind a process manager, e.g. systemd:
   `ExecStart=/srv/nict/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2`
5. **Frontend** - `cd frontend && npm ci && npm run build`; serve `frontend/dist`.
6. **nginx** (HTTPS via certbot):
```nginx
server {
  server_name your-domain.com;
  root /srv/nict/frontend/dist;
  client_max_body_size 12m;
  location / { try_files $uri /index.html; }
  location /api/ { proxy_pass http://127.0.0.1:8000/; proxy_set_header Host $host;
                   proxy_set_header X-Forwarded-For $remote_addr; proxy_set_header X-Forwarded-Proto $scheme; }
}
```
   Then set `TRUST_PROXY_HEADERS=true` in `.env` so rate limiting sees real client IPs.
7. **Persistence & backups** - `backend/uploads` and `backend/private_uploads` hold student photos and documents; back them up with the database.
8. Keep `FEE_RECEIPT_EMAIL_MODE=dry_run` and `AUTOMATION_DRY_RUN=true` until you have verified emails on test data, then switch to live deliberately.

## Notes
- **API paths:** backend routes live under `/api/...` and the frontend base URL is `/api`, so the proxy (Vite in dev, nginx in production) strips one `/api` prefix. Keep the trailing slashes in the nginx `location /api/` + `proxy_pass http://127.0.0.1:8000/;` pair exactly as shown.
- **Rate limits:** login, password reset and the public admission form/upload/payment endpoints are rate limited per IP (in-memory, per worker process).
- **Uploads:** documents are validated by size, extension and file signature; photos are decoded with Pillow.
- **Dependency pin:** `reportlab` must stay `<5` because `xhtml2pdf` requires it.

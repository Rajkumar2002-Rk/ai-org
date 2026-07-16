# Autonomous AI Engineering Organization

Week 1 — Foundation scaffold.

## Stack
- **Backend:** FastAPI (async) on port 8000
- **Database:** PostgreSQL via SQLAlchemy async + Alembic migrations
- **Cache:** Redis
- **Frontend:** React + Next.js on port 3000
- **Containers:** Docker Compose (backend, frontend, postgres, redis)

## Run everything

```bash
docker compose up --build
```

Then open:
- Frontend: http://localhost:3000
- Backend health: http://localhost:8000/health  → `{ "status": "ok" }`
- API docs: http://localhost:8000/docs

The backend runs `alembic upgrade head` on startup, creating the
`projects` and `conversations` tables.

## What works this week
- `GET /health` returns `{ "status": "ok" }`
- `POST /conversation` accepts `{ "message": "..." }` and returns a placeholder reply
- Frontend page with an idea input + purple submit button that calls the API

## Project structure

```
backend/
  app/
    main.py          FastAPI app + routes
    config.py        Settings from env
    database.py      Async SQLAlchemy engine/session
    redis_client.py  Async Redis client
    models.py        projects, conversations tables
    schemas.py       Request/response models
  alembic/           Migrations
  Dockerfile
frontend/
  app/               Next.js App Router page
  Dockerfile
docker-compose.yml
.env
```

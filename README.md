# WashSlot
Laundromat reservation service: reserve a specific washer or dryer in advance, no new machines or payment system needed. FastAPI + PostgreSQL + React.

**Founders:** Anthony4044 · Lemonada10 · ammarranko · **Course:** SOEN 387 Fall 2026

- Back end: [backend/README.md](backend/README.md)
- Front end: [frontend/README.md](frontend/README.md)
- **Architecture:** [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- **Features + how to test:** [docs/FEATURES.md](docs/FEATURES.md)
- **Proof tests (which test proves which guarantee):** [docs/TESTING.md](docs/TESTING.md)
- **Milestone 2 demo script:** [docs/MILESTONE2_DEMO.md](docs/MILESTONE2_DEMO.md)
- Coding rules: [docs/CODING_GUIDE.md](docs/CODING_GUIDE.md)
- Plan: [PROJECT_PLAN.md](PROJECT_PLAN.md)

## How to run

### Docker Compose

Install Docker with Compose v2. From a fresh clone, copy `backend/.env.example` to
`backend/.env` (or use the team's existing `.env`). Set `DATABASE_URL` to your
direct Neon PostgreSQL connection string and keep `sslmode=require`. Keep
`backend/.env` private.

Run this command from the repository root.

```sh
docker compose up
```

Compose builds the images on the first run and applies `alembic upgrade head`
before starting the API and worker. PostgreSQL stays on Neon. The API generates
its JWT signing keys on first startup and keeps them in the `jwt_keys` Docker
volume.

Open the [front end](http://localhost:5173/) or the [API docs](http://localhost:8000/docs).
Use a second terminal to check for HTTP 200 from both probes.

```sh
curl -i http://localhost:8000/health/live
curl -i http://localhost:8000/health/ready
```

On Windows PowerShell, use `curl.exe`. Liveness checks the API process.
Readiness checks PostgreSQL and returns HTTP 503 when the database is unavailable.
If startup stops at the migration step, check `docker compose logs migrate`
and confirm the Neon connection string in `backend/.env`.

Use `docker compose down` to stop the stack and `docker compose up --build`
to rebuild after changing the source.

To check that bookings survive a restart, run `python scripts/restart_check.py`.
It books a slot, deletes and recreates every container, and reads the booking
back. Each run leaves a `restart-check-…@example.com` customer and a cancelled
booking in the database that `backend/.env` points at.

### Local development

See the [front-end setup](frontend/README.md) for Vite and the
[back-end setup](backend/README.md) for Uvicorn, the worker, and seed data.

## CI

Every push to `main` and every pull request runs [`.github/workflows/ci.yml`](.github/workflows/ci.yml):

- **Backend:** `ruff check .` and `pytest` (database tests skip unless `TEST_DATABASE_URL` is set)
- **Conformance:** the current and the frozen v1.0 conformance suites, against the API on a fresh, seeded Postgres
- **Restart check:** `scripts/restart_check.py` on the Compose stack, with Postgres in a container (`compose.ci.yaml`)
- **Frontend:** `npm ci` and `npm run build`

## Repo conventions

PR template and how to protect `main`: [`.github/REPO_CONVENTIONS.md`](.github/REPO_CONVENTIONS.md). Tag PRs with `backend` / `frontend`.

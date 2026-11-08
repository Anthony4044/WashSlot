# WashSlot
Laundromat reservation service: reserve a specific washer or dryer in advance, no new machines or payment system needed. FastAPI + PostgreSQL + React.

- Back end: [backend/README.md](backend/README.md)
- Front end: [frontend/README.md](frontend/README.md)

## How to run

Commands must be run **inside** `frontend/` or `backend/` — there is no `package.json` at the repo root.

### Front end

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173/

If you see `Port 5173 is already in use`, either open that URL (a server is already running) or stop the old process and run `npm run dev` again.

### Back end

See [backend/README.md](backend/README.md) (`uvicorn` on http://localhost:8000).

## CI

Every push to `main` and every pull request runs [`.github/workflows/ci.yml`](.github/workflows/ci.yml):

- **Backend:** `ruff check .` and `pytest` (database tests skip unless `TEST_DATABASE_URL` is set)
- **Frontend:** `npm ci` and `npm run build`

## Repo conventions

PR template and how to protect `main`: [`.github/REPO_CONVENTIONS.md`](.github/REPO_CONVENTIONS.md). Tag PRs with `backend` / `frontend`.

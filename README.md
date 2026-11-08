# WashSlot
Laundromat reservation service: reserve a specific washer or dryer in advance, no new machines or payment system needed. FastAPI + PostgreSQL + React.

- Back end: [backend/README.md](backend/README.md)
- Front end: [frontend/README.md](frontend/README.md)

## CI

Every push to `main` and every pull request runs [`.github/workflows/ci.yml`](.github/workflows/ci.yml):

- **Backend:** `ruff check .` and `pytest` (database tests skip unless `TEST_DATABASE_URL` is set)
- **Frontend:** `npm ci` and `npm run build`

## Repo conventions

PR template and how to protect `main`: [`.github/REPO_CONVENTIONS.md`](.github/REPO_CONVENTIONS.md). Tag PRs with `backend` / `frontend`.

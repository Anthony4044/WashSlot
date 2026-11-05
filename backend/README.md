# WashSlot back end

FastAPI · SQLAlchemy 2 · Alembic · PostgreSQL on Neon (psycopg 3).

## Setup (once)

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env        # or use the ready-made .env Ammar sent you privately (see "Neon" below)
```

## Run

```bash
alembic upgrade head          # build/update the tables in DATABASE_URL
uvicorn app.main:app --reload # http://localhost:8000/docs
```

## Test

```bash
pytest          # database tests run only when TEST_DATABASE_URL is set
ruff check .    # lint (ruff check . --fix to auto-fix)
```

Database tests **wipe every table in TEST_DATABASE_URL**. Never point it at `main`.

## Neon

- **`neondb`** is the shared real database → `DATABASE_URL`.
- **Each of us has our own test database** → `TEST_DATABASE_URL`. They are **already created**:

  | Person | `TEST_DATABASE_URL` database |
  |---|---|
  | Ammar | `neondb_test` |
  | Anthony | `neondb_test_anthony` |
  | Firas | `neondb_test_lemonada` |

  Tests wipe every table in it on each run, so never point it at `neondb`, and don't use someone else's.
  Ammar sends each person a ready-made `.env` privately; never commit it or post it publicly.
  Need another one? `CREATE DATABASE neondb_test_<name>;` in the Neon SQL Editor.
- Use the **direct** connection string (host without `-pooler`). Paste it as Neon gives it
  (`postgresql://...?...sslmode=require`); the app adds the psycopg driver itself.
- Migrate a test branch by hand if needed: `alembic -x db=test upgrade head`.

## Where code goes

**Read [docs/CODING_GUIDE.md](../docs/CODING_GUIDE.md) first.** It holds the rules we code by (contract-first, layers, locking, idempotency, JWT).

| Folder | Layer | What goes there |
|---|---|---|
| `app/api/` | Interface | Routes (`routes/`, one file per area, register in `app/main.py`), request/response DTOs (`schemas/`), the error catalog (`errors.py`), `to_response()` (`responses.py`), wiring (`deps.py`). Thin: no rules, no SQL. |
| `app/services/` | Service | One method per use case. Opens one unit of work, calls the domain, returns an `Outcome` with a DTO. Owns idempotency and ownership checks. Public ids (`ids.py`). |
| `app/domain/` | Domain | The rules, as methods on the `MachineSlot` aggregate. Imports no framework at all. |
| `app/data/` | Data | Row classes (`tables/`), the slot repository (Data Mapper), the unit of work, in-memory doubles for tests. |
| `app/core/` | — | Settings (`config.py`). |
| `alembic/versions/` | — | Migrations: `0001` now, `0002` idempotency (US-5.2), `0003` outbox (US-6.1). |
| `../contract/openapi.yaml` | — | The authored API contract, which is the source of truth (US-1.3). |

## Conventions (summary, details in the guide)

- **Errors:** every error is `{"error": "<code>"}`. The domain raises `SlotUnavailable()`, a service returns `Outcome.failure("not_found")`, and only `app/api/errors.py` maps a code to a status.
- **JSON is camelCase, ids are prefixed** (`slot_1842`), lists are wrapped (`{"laundromats": [...]}`).
- **The user comes from the JWT only,** never from the request body.
- **Times** are stored as `timestamptz` (UTC). Show them in the laundromat's `timezone` (default `America/Toronto`).
- **Writing to a slot** happens in one unit of work with `uow.slots.get(id, lock=True)`. Call `slot.expire_stale_holds(now)` before placing a hold: the partial unique index still counts a stale `HELD` row until its status changes.
- **Changing a table** means changing the row class **and** adding a migration. `tests/test_schema.py` fails if they differ. Draft one with `alembic revision --autogenerate -m "..."`, then read and fix it by hand.
- **The layers' import rules are tested** (`tests/test_layers.py`).

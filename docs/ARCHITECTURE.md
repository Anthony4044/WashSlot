# WashSlot architecture

How the service is shaped for SOEN 387 (contract → layers → concurrency → auth). 

## What WashSlot is

A **laundromat reservation service**: customers browse free washers/dryers, hold a slot for 10 minutes, confirm it, and see only their own bookings. The **contended resource** is a `MachineSlot` (one machine, one hour). Two people must never both hold the same slot.

| Piece | Choice |
|---|---|
| Contract | `contract/openapi.yaml` (authored first; CI + conformance tests) |
| API | FastAPI |
| DB | PostgreSQL (Neon) + Alembic migrations |
| Front end | React + Vite (for demos / manual testing) |
| Auth | RS256 JWT (`sub` + `scope`) |

## Layered design (dependency rule)

```
  Browser / client
         │  HTTP + JSON (camelCase)
         ▼
┌────────────────────┐
│  Interface         │  app/api/     routes, JWT check, error → HTTP status
│  (thin)            │               no business rules, no SQL
└─────────┬──────────┘
          │  calls services with plain ids / Outcome
          ▼
┌────────────────────┐
│  Service           │  app/services/   one method = one use case
│  (use cases)       │   opens unit of work, ownership, DTOs
└─────────┬──────────┘
          │  domain objects only
          ▼
┌────────────────────┐     ┌────────────────────┐
│  Domain            │ ◄── │  Data              │
│  app/domain/       │     │  app/data/         │
│  rules on aggregates│    │  rows, repos, UoW  │
│  (no FastAPI/SQL)  │     │  (no HTTP)         │
└────────────────────┘     └────────────────────┘
```

**Import rule (enforced by `tests/test_layers.py`):**

- `api` may import `services` / `domain` codes, not SQLAlchemy.
- `services` must not import FastAPI or SQLAlchemy.
- `domain` imports **nothing** from the other layers.
- `data` maps rows ↔ domain; domain never sees a `*Row`.

Full rules: [CODING_GUIDE.md](CODING_GUIDE.md).

### Request walkthrough (place a hold)

1. **Route** `POST /slots/{slotId}/holds` (`app/api/routes/holds.py`)  
   - Checks scope `reservations:write` (401/403).  
   - Requires `Idempotency-Key` header.  
   - Parses `slot_5` → `5`, takes `user.id` from the JWT (never from the body).
2. **Service** `HoldService.place_hold` (`app/services/holds.py`)  
   - `with uow_factory() as uow:` → one DB transaction (opened by `run_once`, `app/services/idempotency.py`).  
   - Known `Idempotency-Key`? Replay the stored outcome (`Idempotency-Replayed: true`) and stop (US-5.2).  
   - `uow.slots.get(slot_id, lock=True)` → `SELECT … FOR UPDATE`.  
   - Calls `slot.place_hold(...)` on the domain object.  
   - `save`, then `INSERT` the key's record `ON CONFLICT DO NOTHING` (0 rows → a twin won: roll back, replay its outcome).  
   - Commit → returns `HoldDto`.
3. **Domain** `MachineSlot.place_hold` (`app/domain/slot.py`)  
   - Expires stale holds, then refuses if the slot is already taken (`SlotUnavailable`).
4. **Data** `SqlSlotRepository` (`app/data/repositories.py`)  
   - Loads/saves the aggregate; never decides the rule.

## The aggregate (domain)

**Root:** `MachineSlot` (e.g. Washer 4, 18:00–19:00).  
**Children:** `Reservation` entities (a hold becomes the same row when confirmed — `hold_7` and `res_7` share the number).

Invariant: **at most one active reservation per slot** (active = live `HELD` or `CONFIRMED`). Stated once as `MachineSlot.is_available(now)` / `place_hold`.

There is **no** `ReservationRepository`. You always load/save through the slot (`uow.slots`). To change a reservation you lock its **slot**, not only the reservation row (`get_for_reservation(..., lock=True)`).

## Data and persistence

| Concern | Where |
|---|---|
| Tables | `app/data/tables/*.py` |
| Migrations | `backend/alembic/versions/` (Milestone 1 = migration 001) |
| Unit of work | `app/data/unit_of_work.py` (Postgres) · `app/data/memory.py` (tests) |
| Safety net | Partial unique index: one `HELD`/`CONFIRMED` row per `slot_id` |

**Commands** load the aggregate. **Queries** (browse list, my reservations) may use a read-model SQL join, but availability must match `is_available` (pinned by tests).

## Concurrency (Milestone must-show)

**Contended resource:** the slot.  
**Strategy:** pessimistic locking — `SELECT … FOR UPDATE` on the slot row inside one short transaction.

```
Customer A                         Customer B
   │                                  │
   ├─ BEGIN                           ├─ BEGIN
   ├─ SELECT slot FOR UPDATE  ──┐     │
   │  (holds lock)              │     ├─ SELECT slot FOR UPDATE  (waits)
   ├─ place_hold → INSERT       │     │
   ├─ COMMIT ───────────────────┘     │
   │                                  ├─ wakes, sees hold → SlotUnavailable
   │                                  ├─ 409 slot_unavailable
```

**Proof:** `backend/tests/test_hold_race.py` — 20 threads, one slot, barrier; with the lock → one `201`, rest `409`, one DB row.

The unique index is the **safety net** if locking were forgotten; the lock is what returns a clean business error instead of a DB crash.

## Authentication and authorization

| Step | Mechanism |
|---|---|
| Register / login | `POST /auth/register`, `POST /auth/login` → RS256 access token |
| Keys | `backend/keys/*.pem` (git-ignored); `scripts/generate_keys.py` |
| Every protected call | Verify signature (`RS256` only), `iss`, `aud`, `exp`, then `sub` + `scope` |
| Scopes | `reservations:read`, `reservations:write`, `operator:manage` |
| Ownership | In the **service** (e.g. Bob’s id on Alice’s reservation → `404 not_found`) |

Public (no token): browse laundromats and slots.  
Auth attacks covered in tests: forged payload, `alg=none`, wrong audience (`tests/test_security.py`).

## Contract-first

1. Edit `contract/openapi.yaml`.
2. Implement layers to match.
3. Conformance tests in `backend/tests/conformance/` hit a **live** server over HTTP and validate JSON Schema — they never import `app`.

Errors on the wire are always `{"error": "<code>"}`. Status mapping lives only in `app/api/errors.py`.

## Front end (for demos)

Thin client over the contract:

| Concern | File |
|---|---|
| HTTP + token | `frontend/src/api.js`, `auth.js` |
| Routes | `frontend/src/App.jsx` |
| Browse / hold / reservations | `browse.js`, `holds.js`, `reservations.js` + `pages/*` |

Base URL: `VITE_API_BASE_URL` (default `http://localhost:8000`). CORS must allow the exact origin you open (`localhost` vs `127.0.0.1`).

## What Milestone 2 expects vs later work

| Milestone 2 (now) | Later stories |
|---|---|
| Contract, layers, DB | Foreign email (Resend) via outbox/worker |
| Contended slot + race test | Full idempotency store (US-5.2) |
| Auth + per-user ownership | Cancel, check-in, operator tools |
| Short progress demo | Health checks, Docker, final defense |

## Folder map

```
WashSlot/
├── contract/openapi.yaml          # source of truth
├── docs/                          # this guide + features + demo script
├── backend/
│   ├── app/
│   │   ├── api/                   # interface
│   │   ├── services/              # use cases
│   │   ├── domain/                # rules
│   │   ├── data/                  # persistence
│   │   └── core/                  # settings, JWT, passwords
│   ├── alembic/                   # migrations
│   ├── scripts/                   # seed_*, generate_keys
│   └── tests/                     # domain · service · DB · conformance
└── frontend/src/                  # React demo UI
```

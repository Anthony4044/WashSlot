# WashSlot — Project Plan

Source: `WashSlot_Proposal` (SOEN 387, Fall 2026). Stack: FastAPI · SQLAlchemy · Alembic · PostgreSQL (Neon) · React · Resend · Docker.

Team: **@Anthony4044** · **@Lemonada10** · **@ammarranko**

## How this plan works

- **We finish 2 days before every official deadline.** The finish date is the real deadline for the team.
- **One person owns a whole user story**: back end, front end and tests. Nobody waits on half of someone else's story.
- **Every story has a due date.** Merged into `main` with tests passing by the end of that day.
- **Naming:** epics `[ES-01]` · user stories `[US-1.1]` (epic 1, story 1) · tasks `[T.1.1.1]` (epic 1, story 1, task 1).
- **Coding rules:** [docs/CODING_GUIDE.md](docs/CODING_GUIDE.md) (contract-first, layers, locking, idempotency, RS256 JWT). Every story that adds or changes an endpoint **updates `contract/openapi.yaml` first** and adds **conformance tests** for it.
- **Points:** 1 = a couple of hours · 2 = half a day · 3 = a day · 5 = 2 days · 8 = 3 days.

| Checkpoint | Official deadline | **We finish by** |
|---|---|---|
| **Milestone 1 (Week 9)**: running service, auth, availability, holds, confirmation, no double-booking | Mon Nov 16 | **Sat Nov 14** |
| Week 10 sprint: expiration, idempotency, cancellation | — | **Sat Nov 21** |
| Week 11 sprint: emails, operator tools, check-in | — | **Sat Nov 28** |
| **Code freeze + report (Week 12)** | Mon Dec 7 (to confirm) | **Sat Dec 5** |
| Demo & defense | in class, Week 12 | — |

---

## Rules that keep us out of each other's way

1. **Routes are fixed now.** Each page and endpoint has one owner (see the table below). You fill in only your own.
2. **Migrations are numbered in this plan.** Only the story that lists a migration creates it: 001 → US-1.1, 002 → US-5.2, 003 → US-6.1. Migration 001 already contains **every table Milestone 1 needs**, so nobody waits for a table.
3. **Shared files** (`main.py` router list, `App.jsx` routes, `worker.py` job list, `requirements.txt`) only get one-line additions. Resolve merge conflicts there by keeping both sides.
4. **Need something from another story that isn't merged yet?** Insert rows directly in your test fixtures. Don't wait.
5. One branch per story (`US-4.1-hold-slot`), PR into `main`, someone else reviews within 24 h. **US-4.1, US-4.2, US-5.1, US-5.2 and US-6.1** get a careful line-by-line review: they are the concurrency, idempotency, expiry and email logic the proposal promises to check by hand.
6. Write every AI suggestion that was wrong or needed fixing in `docs/ai-log.md` as it happens.

### Who owns what

| Front-end route | Back-end endpoints | Owner | Story |
|---|---|---|---|
| `/login`, `/register` | `POST /auth/register`, `POST /auth/login` | @Anthony4044 | US-2.1 |
| `/laundromats`, `/laundromats/:id` | `GET /laundromats`, `GET /laundromats/{id}/slots?date=` | @Lemonada10 | US-3.1 |
| `/slots/:slotId/hold` | `POST /slots/{slotId}/holds` | @Anthony4044 | US-4.1, US-5.2 |
| `/holds/:holdId` | `GET /holds/{holdId}`, `POST /holds/{holdId}/confirm` | @ammarranko | US-4.2, US-5.1 |
| `/reservations` | `GET /me/reservations`, `GET /reservations/{id}`, `DELETE /reservations/{id}`, `POST /reservations/{id}/check-in` | @Lemonada10 | US-4.3, US-5.3, US-7.2 |
| `/operator` | `/operator/laundromats/{id}/machines…`, `/operator/laundromats/{id}/slots` | @Anthony4044 | US-7.1 |
| `/operator/today` | `GET /operator/laundromats/{id}/today` | @Lemonada10 | US-7.2 |
| `/operator/notifications` | `/operator/notifications…` | @Anthony4044 | US-7.3 |
| — | back-end skeleton, migration 001, `worker.py`, notification outbox | @ammarranko | US-1.1, US-5.1, US-6.1 |
| — | `contract/openapi.yaml` structure, conformance harness | @ammarranko | US-1.3 (each story then adds its own operations) |
| — | `GET /health/live`, `GET /health/ready`, correlation-id logging | @Lemonada10 | US-8.1, US-8.2 |

How the pages connect: the slot grid (@Lemonada10) links to `/slots/:slotId/hold` (@Anthony4044). A successful hold redirects to `/holds/:holdId` (@ammarranko). A confirmed hold redirects to `/reservations` (@Lemonada10).

---

## Calendar at a glance

| Dates | @Anthony4044 | @Lemonada10 | @ammarranko |
|---|---|---|---|
| Wed Nov 4 – Fri Nov 6 | US-2.1 Register & log in *(JWT code + tests first)* | US-1.2 Front-end foundation & CI | US-1.1 Back-end foundation *(due Fri Nov 6)* |
| Sat Nov 7 – Mon Nov 9 | US-2.1 *(due Mon Nov 9)* | US-3.1 Browse laundromats & slots | US-1.3 Contract + conformance harness *(due Sat Nov 7)* → US-4.2 Confirm my hold |
| Tue Nov 10 – Thu Nov 12 | US-4.1 Hold a slot *(due Thu Nov 12)* | US-3.1 *(due Tue Nov 10)* → US-4.3 My reservations | US-4.2 *(due Thu Nov 12)* |
| Fri Nov 13 | Review PRs, fix bugs | US-4.3 *(due Fri Nov 13)* | US-9.1 Full end-to-end run, file bugs |
| **Sat Nov 14** | **Fix bugs from the Nov 13 run** | **Fix bugs from the Nov 13 run** | **US-9.1 README, demo script, submit** |
| Mon Nov 16 – Sat Nov 21 | US-5.2 Safe retries (idempotency) | US-5.3 Cancel a reservation | US-5.1 Holds expire on their own |
| Mon Nov 23 – Sat Nov 28 | US-7.1 Operator machines & slots · US-7.3 Retry failed emails | US-7.2 Today view & check-in | US-6.1 Confirmation email |
| Mon Nov 30 – Thu Dec 3 | US-8.4 Tests & persistence | US-8.1 One-command run · US-8.2 Request tracing | US-8.3 Contract check & evolution |
| Fri Dec 4 | US-9.2 Report (your sections) | US-9.2 Report (your sections) | US-9.2 Report (your sections) |
| **Sat Dec 5** | **US-9.3 Rehearse demo, tag v1.0** | **US-9.3 Rehearse demo, tag v1.0** | **US-9.3 Rehearse demo, tag v1.0** |

---

## [ES-01] Foundation
The back end, the database and the front end exist and run, and every PR is checked automatically.

### [US-1.1] Back-end foundation
**As a developer, I can start the back end and build the whole database with one command.**
Owner: **@ammarranko** · Due: **Fri Nov 6** · 3 pts · Needs: nothing

- [ ] [T.1.1.1] **Layered project structure**: `backend/` with `api/` (routes + Pydantic schemas), `services/` (business rules), `repositories/` (SQLAlchemy queries), `models/`; `requirements.txt`
- [ ] [T.1.1.2] **Settings from environment variables**: `pydantic-settings`; commit `.env.example` (DB URL, JWT secret, Resend key), never the real `.env`
- [ ] [T.1.1.3] **Neon database branches**: `main` branch for the demo, `test` branch for automated tests; share the connection strings privately
- [ ] [T.1.1.4] **Alembic + migration 001 with all Milestone 1 tables**:
  - `users` (id, email, password_hash, role CUSTOMER/OPERATOR)
  - `laundromats` (id, name, address, operator_id)
  - `machines` (id, laundromat_id, label, type WASHER/DRYER, reservable)
  - `machine_slots` (id, machine_id, start_time, end_time)
  - `reservations` (id, slot_id, user_id, status HELD/CONFIRMED/EXPIRED/CANCELLED/NO_SHOW, expires_at, confirmation_email, checked_in_at, created_at)
  - Partial unique index on `reservations(slot_id) WHERE status IN ('HELD','CONFIRMED')` (safety net behind the row lock)
- [ ] [T.1.1.5] **CORS and error format**: CORS for the React dev server; global handler so every error is `{"error": "<code>"}`
- [ ] [T.1.1.6] **Test database fixture**: pytest fixture that gives each test a clean database on the `test` branch
- [ ] [T.1.1.7] **Domain, service and data layers**: pure `app/domain` (the `MachineSlot` aggregate with `is_available` and `expire_stale_holds`), `app/services` (`Outcome`, prefixed ids, unit-of-work interface), `app/data` (`*Row` tables, slot repository as a Data Mapper with `lock=True` → `SELECT … FOR UPDATE`, unit of work, in-memory doubles), `app/api` (error catalog code→status, camelCase DTO bases, `to_response`); RS256 JWT settings; `docs/CODING_GUIDE.md`; tests for the import rules and the row lock

**Done when:** `alembic upgrade head` builds all tables on an empty Neon branch, and `uvicorn` starts.

### [US-1.3] API contract first, with a conformance suite
**As a client developer, I can build against a written contract, and a test suite proves the server keeps it.**
Owner: **@ammarranko** · Due: **Sat Nov 7** · 3 pts · Needs: nothing (the proposal defines the operations)

- [ ] [T.1.3.1] **Author contract v1.0**: `contract/openapi.yaml` (OpenAPI 3.1) for the proposal's operations plus `POST /auth/register`, `POST /auth/login`, `GET /holds/{holdId}`, `GET /me/reservations`; camelCase schemas with `required` and `additionalProperties: false`; id patterns (`^slot_[1-9][0-9]*$`, …); lists wrapped in objects; RS256 bearer security scheme with scopes
- [ ] [T.1.3.2] **Error catalog and semantics in the contract**: the shared `Error` schema, every code with its status and whether it is retryable (same list as `app/api/errors.py`); each operation's description says if it is safe, idempotent or neither, and what a timed-out caller must do
- [ ] [T.1.3.3] **Conformance harness**: `backend/tests/conformance/` loads the contract and validates live responses with JSON Schema (draft 2020-12) against `CONFORMANCE_BASE_URL`; never imports `app`; one example test per existing endpoint, which every later story copies
- [ ] [T.1.3.4] **Contract checked in CI**: validate `contract/openapi.yaml` (openapi-spec-validator) on every PR

**Done when:** the contract validates in CI and the conformance harness runs against a local server.

### [US-1.2] Front-end foundation & CI
**As a developer, I have a React app with every page stubbed, and every PR is checked automatically.**
Owner: **@Lemonada10** · Due: **Fri Nov 6** · 3 pts · Needs: nothing

- [ ] [T.1.2.1] **React app with all routes stubbed**: Vite + React + React Router, a placeholder page for every route in the "Who owns what" table
- [ ] [T.1.2.2] **API client**: `src/api.js` with base URL from env, adds `Authorization: Bearer <token>` from storage, turns `{error}` bodies into readable messages
- [ ] [T.1.2.3] **Navigation bar**: Laundromats · My reservations · Login/Logout
- [ ] [T.1.2.4] **GitHub Actions CI**: `ruff` + `pytest` for the back end, `npm run build` for the front end
- [ ] [T.1.2.5] **Repo conventions**: PR template, `backend`/`frontend` labels, protect `main`

**Done when:** the app runs with every route showing a placeholder, and CI is green on a PR.

## [ES-02] Accounts
Customers and operators can sign up and log in; the server trusts only verified tokens.

### [US-2.1] Register and log in
**As a customer, I can create an account and log in so I can make reservations.**
Owner: **@Anthony4044** · Due: **Mon Nov 9** · 5 pts · Needs: US-1.1 for the `users` table (write the JWT code and its tests first, Nov 4–6)

- [ ] [T.2.1.1] **Password hashing and RS256 tokens**: bcrypt; `scripts/generate_keys.py` makes the RSA key pair in `backend/keys/` (git-ignored); login signs with the private key; claims `sub` (`usr_N`), `scope`, `iss`, `aud`, `exp` from settings
- [ ] [T.2.1.2] **Auth dependencies**: verify with the public key and `algorithms=["RS256"]`, checking `iss`, `aud`, `exp`; no token → 401 `missing_token`, bad token → 401 `invalid_token`; `require_scope("reservations:write")` → 403 `insufficient_scope`
- [ ] [T.2.1.3] **Register and login endpoints**: contract first, then `POST /auth/register` (always creates a CUSTOMER, never an operator; duplicate → 409 `email_taken`) and `POST /auth/login` (scopes by role: customers `reservations:read reservations:write`, operators add `operator:manage`)
- [ ] [T.2.1.4] **Seed users**: `scripts/seed_users.py` with 2 customers + 1 operator (the only way to create an operator)
- [ ] [T.2.1.5] **Login and register pages**: `/login`, `/register`; save the token; logout; go to `/login` on any 401
- [ ] [T.2.1.6] **Auth tests, including the three attacks**: login works · wrong password → 401 · expired → 401 · tampered payload → 401 · `alg=none` → 401 · wrong audience → 401 · missing scope → 403 · register with `role: OPERATOR` still creates a customer · conformance tests for both endpoints

**Done when:** you can register and log in through the browser, and protected requests carry the token.

## [ES-03] Browse availability
Customers can see laundromats and which machines are free at which times.

### [US-3.1] Browse laundromats and free slots
**As a customer, I can pick a laundromat and a date and see which machines are free when.**
Owner: **@Lemonada10** · Due: **Tue Nov 10** · 6 pts · Needs: US-1.1 (tables), US-1.2

- [ ] [T.3.1.1] **Seed laundromats, machines and slots**: `scripts/seed_laundromats.py` with 2 laundromats, ~8 machines each (some `reservable=false`), 1-hour slots for the next 7 days
- [ ] [T.3.1.2] **List laundromats endpoint**: contract first; `GET /laundromats` returns `{"laundromats": [...]}` with ids like `lm_3`
- [ ] [T.3.1.3] **Slots-by-date endpoint (read model)**: `GET /laundromats/{id}/slots?date=YYYY-MM-DD` returns `{"machines": [...]}` (reservable machines, each with its slots marked `AVAILABLE` or `UNAVAILABLE`) in **one** SQL query, with no N+1; an expired HELD counts as available
- [ ] [T.3.1.4] **Laundromat list page**: `/laundromats`
- [ ] [T.3.1.5] **Availability grid page**: `/laundromats/:id` grid (machines × times) with a date picker; an available slot links to `/slots/:slotId/hold`
- [ ] [T.3.1.6] **Availability tests**: HELD and CONFIRMED slot → unavailable · expired HELD → available · non-reservable machines hidden · **the read model agrees with `MachineSlot.is_available`** for every case · conformance tests for both endpoints

**Done when:** you can click through laundromat → date → available slot in the browser.

## [ES-04] Reserve a machine
The contended resource (graded at 20%): one machine slot can only ever go to one customer.

### [US-4.1] Hold a slot, never double-booked
**As a customer, I can hold a slot for 10 minutes, and if two people try at the same time only one gets it.**
Owner: **@Anthony4044** · Due: **Thu Nov 12** · 8 pts · Needs: US-1.1, US-2.1

- [ ] [T.4.1.1] **Domain rule `MachineSlot.place_hold(user_id, email, now, minutes)`**: expires stale holds first, raises `SlotUnavailable` if the slot is taken, adds a HELD reservation with `expires_at = now + 10 min`; domain tests with no database
- [ ] [T.4.1.2] **Use case and endpoint (contract first)**: `HoldService.place_hold` opens one unit of work, `uow.slots.get(id, lock=True)` (`SELECT … FOR UPDATE`), uses the database clock, calls the domain rule, saves, returns an `Outcome` with a DTO; thin route `POST /slots/{slotId}/holds` with scope `reservations:write`; 201 (body as in the proposal, `holdId: "hold_N"`) · 401 · 403 · 404 `not_found` · 409 `slot_unavailable` · 422 `invalid_request`; missing `Idempotency-Key` → 422 `idempotency_key_required`, key must be 8–128 characters (storing it comes in US-5.2)
- [ ] [T.4.1.3] **Hold page**: `/slots/:slotId/hold` with slot details, email field (prefilled), "Hold this slot" → on 201 go to `/holds/:holdId`; on 409 show "Someone just took this slot" and link back
- [ ] [T.4.1.4] **Race test**: on the test database, 20 threads released together by a `threading.Barrier` → exactly one 201, 19 × 409, one active row in the DB
- [ ] [T.4.1.5] **Hold tests**: service tests with the in-memory unit of work · 404 unknown or malformed slot id · 401 no token · 403 missing scope · expired hold on the slot → new hold allowed · conformance tests for the endpoint

**Done when:** the race test passes, and two browsers clicking the same slot get one success and one 409.

### [US-4.2] Confirm my hold
**As a customer, I can confirm my hold before the 10 minutes run out.**
Owner: **@ammarranko** · Due: **Thu Nov 12** · 4 pts · Needs: US-2.1 (insert HELD rows in fixtures, so no wait for US-4.1)

- [ ] [T.4.2.1] **Get hold endpoint (contract first)**: `GET /holds/{holdId}`; the ownership check is in the service layer (someone else's hold → 404 `not_found`)
- [ ] [T.4.2.2] **Domain rule `MachineSlot.confirm(reservation_id, now)` and confirm endpoint**: `POST /holds/{holdId}/confirm`, one unit of work, lock the **slot** (`uow.slots.get_for_reservation(id, lock=True)`), check the owner in the service, decide with the **database** clock:
  - HELD and not expired → CONFIRMED, 200
  - already CONFIRMED by the same user → 200 with the same reservation (naturally idempotent, no key needed)
  - expired → 409 `hold_expired`
  - another user's hold → 404
- [ ] [T.4.2.3] **Hold review page**: `/holds/:holdId` with details, countdown from `expiresAt` (display only), "Confirm" button → go to `/reservations`
- [ ] [T.4.2.4] **Confirm tests**: domain tests and service tests (in-memory) for each case above, including confirming twice · conformance tests for both endpoints

**Done when:** hold → confirm works end to end in the browser.

### [US-4.3] My reservations (only mine)
**As a customer, I can see my reservations, and nobody else can see them.**
Owner: **@Lemonada10** · Due: **Fri Nov 13** · 4 pts · Needs: US-2.1

- [ ] [T.4.3.1] **My reservations endpoint (contract first)**: `GET /me/reservations` returns `{"reservations": [...]}` for the caller (from the token), newest first, ids like `res_N`, scope `reservations:read`
- [ ] [T.4.3.2] **Single reservation endpoint**: `GET /reservations/{id}`; the ownership check is in the service layer; someone else's → 404 `not_found` (don't reveal it exists)
- [ ] [T.4.3.3] **My reservations page**: `/reservations` with laundromat, machine, date, time, status
- [ ] [T.4.3.4] **Ownership tests**: customer B gets 404 on A's reservation by changing the id · list only shows your own · conformance tests for both endpoints

**Done when:** each test customer sees only their own bookings.

## [ES-05] Expiration, safe retries & cancellation
Abandoned holds free themselves, retries never double-book, and customers can cancel.

### [US-5.1] Holds expire on their own
**As a customer, a hold someone abandoned frees the machine without anyone doing anything.**
Owner: **@ammarranko** · Due: **Thu Nov 19** · 4 pts · Needs: US-4.1, US-4.2

- [ ] [T.5.1.1] **Background worker with expiry job**: `backend/worker.py`, a separate process with a job list; first job runs every 30 s: `UPDATE reservations SET status='EXPIRED' WHERE status='HELD' AND expires_at < now()`
- [ ] [T.5.1.2] **Lazy expiry check everywhere**: slot list, hold and confirm all go through the one domain rule (`Reservation.is_active` / `MachineSlot.expire_stale_holds`) with the database clock, so a late worker never blocks a slot
- [ ] [T.5.1.3] **Expired hold message**: on `/holds/:holdId`, when the countdown hits 0 or confirm returns 409, show "Hold expired" and a link back to the grid
- [ ] [T.5.1.4] **Expiry tests**: slot is free again after expiry with the worker off · confirm right at expiry gives one clear answer

**Done when:** an abandoned hold frees its slot, with or without the worker running.

### [US-5.2] Safe retries with an idempotency key
**As a client, if my hold request's response is lost, I can retry and never get two holds.**
Owner: **@Anthony4044** · Due: **Sat Nov 21** · 6 pts · Needs: US-4.1

- [ ] [T.5.2.1] **Migration 002 for idempotency records**: `idempotency_records` (user_id, key, endpoint, request_hash, status_code, response_body, created_at; primary key user_id + key); row class and repository on the unit of work
- [ ] [T.5.2.2] **Store and replay any outcome, in the service layer**: in the **same unit of work** as the hold, `INSERT … ON CONFLICT DO NOTHING` (0 rows → a twin won: roll back and replay its result); replay the stored outcome **whatever it was** (201, 404 or 409) with the same body and `Idempotency-Replayed: true`; same key + different body or endpoint → 422 `idempotency_key_reuse`; contract updated
- [ ] [T.5.2.3] **Client retry key**: hold page creates one UUID per attempt and reuses it when retrying
- [ ] [T.5.2.4] **Idempotency tests**: duplicate → same response and one row · replayed 409 stays 409 · different body → 422 · **8 parallel clicks with the same key → 1 hold, 7 replayed** · conformance tests
- [ ] [T.5.2.5] **24-hour retention**: worker job deletes records older than `IDEMPOTENCY_RETENTION_HOURS` (database clock, never earlier); the contract states the 24-hour promise

**Done when:** retrying a hold with the same key never creates a second hold.

### [US-5.3] Cancel a future reservation
**As a customer, I can cancel a booking I can't make so someone else can use the machine.**
Owner: **@Lemonada10** · Due: **Thu Nov 19** · 3 pts · Needs: US-4.3

- [ ] [T.5.3.1] **Domain rule `MachineSlot.cancel(reservation_id, now)` and cancel endpoint (contract first)**: `DELETE /reservations/{id}`, lock the slot, owner check in the service, only before the slot starts → CANCELLED, 204; **cancelling again → 204 (idempotent, same end state)**; started/past → 409 `too_late_to_cancel`; another user's → 404
- [ ] [T.5.3.2] **Cancel button**: on `/reservations`, with an "are you sure?" step
- [ ] [T.5.3.3] **Cancel tests**: domain and service tests for each case above · slot shows available again after cancelling · conformance tests

**Done when:** a cancelled booking's slot shows up as available again.

## [ES-06] Confirmation email
The foreign-service integration: Resend emails sent through an outbox, safe when Resend is down.

### [US-6.1] Confirmation email that survives Resend being down
**As a customer, I get an email with the laundromat, machine, date and time after I confirm.**
Owner: **@ammarranko** · Due: **Fri Nov 27** · 8 pts · Needs: US-4.2, US-5.1

- [ ] [T.6.1.1] **Migration 003 for the outbox (merge by Tue Nov 24)**: `notification_outbox` (id, reservation_id, laundromat_id, type, payload, status PENDING/SENT/FAILED, attempts, next_attempt_at, last_error, correlation_id); US-7.3 builds on it
- [ ] [T.6.1.2] **Write outbox row on confirm**: in the confirm use case's **same unit of work**, insert a `SEND_CONFIRMATION_EMAIL` row (never call Resend inside the transaction)
- [ ] [T.6.1.3] **Email sender job**: worker takes PENDING rows due now with `FOR UPDATE SKIP LOCKED`, sends through Resend with `Idempotency-Key = outbox id`
- [ ] [T.6.1.4] **Retry with backoff**: network error or 5xx → retry at 30 s, 1 m, 2 m, 4 m, 8 m; max 6 attempts → FAILED; 4xx → FAILED right away
- [ ] [T.6.1.5] **Fake failures switch**: `EMAIL_FAKE_FAILURES=N` makes the email client fail N times (for tests and the demo)
- [ ] [T.6.1.6] **Email tests**: fails twice then SENT · always fails → FAILED · reservation stays CONFIRMED either way

**Done when:** confirming sends one email, and turning on fake failures shows retries then FAILED.

## [ES-07] Operator tools & check-in
Operators control their machines, see today's bookings and handle failed emails; no-shows free the machine.

### [US-7.1] Operator manages machines and slots
**As an operator, I choose which machines can be reserved and when.**
Owner: **@Anthony4044** · Due: **Wed Nov 25** · 4 pts · Needs: US-2.1

- [ ] [T.7.1.1] **Operator machine and slot endpoints (contract first)**: scope `operator:manage`; only for the operator's own laundromat (ownership check in the service, else 404): toggle `reservable`, create slots for a date range
- [ ] [T.7.1.2] **Operator page**: `/operator` with a machine list, on/off switches and a "Create slots" form
- [ ] [T.7.1.3] **Operator access tests**: operator of laundromat 1 can't change laundromat 2 · customers get 403

**Done when:** an operator can switch a machine to reservable and create slots for it.

### [US-7.2] Today view, check-in and no-shows
**As an attendant, I see today's bookings and who has arrived; late customers lose their slot to walk-ins.**
Owner: **@Lemonada10** · Due: **Sat Nov 28** · 5 pts · Needs: US-4.3, US-5.1 (worker)

- [ ] [T.7.2.1] **Today view**: `GET /operator/laundromats/{id}/today` + `/operator/today` page (machine, time, customer, checked in?)
- [ ] [T.7.2.2] **Check-in (domain rule `MachineSlot.check_in`)**: `POST /reservations/{id}/check-in` by the customer ("I'm here" on `/reservations`) or the operator ("Mark present" on the today page); naturally idempotent (checking in again returns the reservation); cancelled → 409 `already_cancelled`; contract first
- [ ] [T.7.2.3] **No-show job**: add a job to `worker.py`: CONFIRMED, not checked in, 15 min after start → NO_SHOW
- [ ] [T.7.2.4] **Check-in tests**: domain and service tests for the check-in rules · NO_SHOW after 15 min · conformance tests

**Done when:** the today page shows who checked in, and a late customer becomes NO_SHOW.

### [US-7.3] Operator retries failed emails
**As an operator, I can see which confirmation emails failed and send them again.**
Owner: **@Anthony4044** · Due: **Sat Nov 28** · 2 pts · Needs: migration 003 from US-6.1 (Tue Nov 24)

- [ ] [T.7.3.1] **Failed email endpoints**: `GET /operator/notifications?status=FAILED` (own laundromat only) and `POST /operator/notifications/{id}/retry` (back to PENDING, attempts reset)
- [ ] [T.7.3.2] **Failed emails page**: `/operator/notifications` with a "Retry" button
- [ ] [T.7.3.3] **Failed email tests**: other laundromat's notifications → 404 · retry sets PENDING

**Done when:** an operator can retry a failed email and it gets sent.

## [ES-08] Running in production
One-command startup, health checks, traceable logs, a published contract and proof tests.

### [US-8.1] One command runs everything
**As anyone, I can start WashSlot with one documented command.**
Owner: **@Lemonada10** · Due: **Wed Dec 2** · 4 pts · Needs: US-5.1 (worker)

- [ ] [T.8.1.1] **Docker setup**: Dockerfiles; `docker compose up` starts the API, the worker and the front end and runs `alembic upgrade head` on start; the DB stays on Neon
- [ ] [T.8.1.2] **Health checks**: `GET /health/live` (process up) and `GET /health/ready` (can reach Postgres, else 503)
- [ ] [T.8.1.3] **README run instructions**: update the README for the one-command start

**Done when:** a fresh clone starts with `docker compose up` and `/health/ready` returns 200.

### [US-8.2] Trace one request across the API and the worker
**As a developer, I can follow one booking through every log line.**
Owner: **@Lemonada10** · Due: **Wed Dec 2** · 3 pts · Needs: US-6.1

- [ ] [T.8.2.1] **JSON logs with correlation id**: middleware reads or creates `X-Correlation-ID` and returns it in the response
- [ ] [T.8.2.2] **Correlation id in the worker**: saved on the outbox row; the worker logs it when sending

**Done when:** one correlation id appears in the API and worker logs for the same booking.

### [US-8.3] Contract check and a backward-compatible change
**As a client developer, I can trust that the running service matches the published contract, even as it evolves.**
Owner: **@ammarranko** · Due: **Thu Dec 3** · 2 pts · Needs: all endpoints merged

- [ ] [T.8.3.1] **Generated docs checked against the contract**: a CI test compares FastAPI's generated OpenAPI with `contract/openapi.yaml` (same paths, methods, status codes and schemas) and fails on any difference
- [ ] [T.8.3.2] **Backward-compatible change**: contract v1.1 adds the optional `notificationPreference` (EMAIL/SMS) to the hold request, then the code; a copy of the v1.0 conformance suite stays in CI and still passes

**Done when:** CI fails on any drift from the contract, and the v1.0 suite passes against v1.1.

### [US-8.4] Proof tests and persistence
**As graders, we can see the key guarantees hold.**
Owner: **@Anthony4044** · Due: **Thu Dec 3** · 3 pts · Needs: everything else merged

- [ ] [T.8.4.1] **Fill test gaps at all three levels**: domain, service (in-memory) and conformance tests for concurrency, idempotency, auth, expiry and outbox; CI green
- [ ] [T.8.4.2] **Restart persistence check**: `scripts/restart_check` creates a reservation, restarts the containers, checks it's still there

**Done when:** CI is green and the restart check passes.

## [ES-09] Delivery: milestone, report & demo
Hand in each checkpoint on time and ready to defend.

### [US-9.1] Milestone 1 run and submission
**As the team, we hand in a milestone that runs from a clean start.**
Owner: **@ammarranko** · Due: **Sat Nov 14** · 2 pts · Needs: US-1.1 to US-4.3

- [ ] [T.9.1.1] **End-to-end run (Fri Nov 13)**: fresh Neon branch → migrate → seed → register → browse → hold → confirm → my reservations, plus a two-browser race; open a bug issue for each problem, assigned to the story's owner (fix by Sat Nov 14 noon)
- [ ] [T.9.1.2] **README and demo script**: README "How to run" (env vars, migrate, seed, start back end and front end) and `docs/milestone-demo.md`
- [ ] [T.9.1.3] **Tag and submit (Sat Nov 14)**: tag `v0.1-milestone` and submit

**Done when:** Milestone 1 is submitted.

### [US-9.2] Final report
**As the team, we explain and defend every design decision in the report.**
Owner: **everyone** · Due: **Fri Dec 4** · 6 pts (2 each) · Needs: code complete

- [ ] [T.9.2.1] **@Anthony4044 report sections**: concurrency control (holds, locking), idempotency, authentication & authorization (RS256, scopes, the three attacks)
- [ ] [T.9.2.2] **@Lemonada10 report sections**: front end, deployment, health checks and tracing, operator features
- [ ] [T.9.2.3] **@ammarranko report sections**: the contract and conformance suite, the layered architecture (domain, service, data mapper), expiry, email outbox & retries; merge `docs/ai-log.md` into the AI-collaboration log section

**Done when:** the report is complete and everyone has read all of it.

### [US-9.3] Demo rehearsal and code freeze
**As the team, we can show all 7 promised scenarios without surprises.**
Owner: **everyone** · Due: **Sat Dec 5** · 3 pts (1 each) · Needs: US-9.2

- [ ] [T.9.3.1] **@Anthony4044 demo scenarios**: two users racing · duplicate idempotency key
- [ ] [T.9.3.2] **@Lemonada10 demo scenarios**: normal booking · data survives a restart
- [ ] [T.9.3.3] **@ammarranko demo scenarios**: expired hold · access to someone else's reservation · email failure and retry
- [ ] [T.9.3.4] **@ammarranko rehearsal and freeze**: run two full rehearsals with everyone, tag `v1.0`, code freeze

**Done when:** two clean rehearsals and `v1.0` is tagged.

---

## Totals

| | Milestone 1 | Week 10 | Week 11 | Week 12 | **Total** |
|---|---|---|---|---|---|
| @Anthony4044 | 13 | 6 | 6 | 6 | **31** |
| @Lemonada10 | 13 | 3 | 5 | 10 | **31** |
| @ammarranko | 12 | 4 | 8 | 5 | **29** |

## Changes from the proposal

- **Alembic starts now, not in Week 12.** Migration 001 builds all Milestone 1 tables, and 002 and 003 come later, giving more than the 2 migrations required.
- **Added `GET /me/reservations` and `GET /holds/{holdId}`** so pages don't need to know ids in advance. Both are backward-compatible additions.
- **Confirming an expired hold returns 409 `hold_expired`.** The proposal didn't name a status code for this case.
- **The contract is written by hand first** (`contract/openapi.yaml`, US-1.3). FastAPI's generated docs are checked against it, not used as the contract.
- **Ids are prefixed** (`slot_1842`, `hold_7251`, `res_7251`) and **JSON is camelCase**, as in the proposal's examples.
- **Tokens are signed RS256 with a key pair**, not a shared secret, and carry scopes.
- **Browsing laundromats and slots doesn't need a login.** This data isn't sensitive, and it lets US-3.1 be built without waiting for US-2.1. Everything that reads or changes a reservation still needs a token.

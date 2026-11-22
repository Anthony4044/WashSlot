# WashSlot features (Milestone 1 / Week 9)

What is **on `main` today**, how to try it, and where the code lives. Owners are from [PROJECT_PLAN.md](../PROJECT_PLAN.md).

**Demo accounts** (after `python scripts/seed_users.py`):

| Email | Password | Role |
|---|---|---|
| `alice@example.com` | `customer123` | CUSTOMER |
| `bob@example.com` | `customer123` | CUSTOMER |
| `operator@example.com` | `operator123` | OPERATOR |

**URLs:** app http://127.0.0.1:5173 · API docs http://127.0.0.1:8000/docs

---

## 1. Back-end foundation (US-1.1)

**What:** Layered FastAPI app, Neon Postgres, Alembic migration 001 (users, laundromats, machines, slots, reservations), CORS, `{"error": code}` catalog, in-memory test doubles.

| How to test | Where in code |
|---|---|
| `cd backend` → `alembic upgrade head` → `uvicorn app.main:app` → open `/docs` | `app/main.py`, `app/data/tables/`, `alembic/versions/` |
| `pytest tests/test_layers.py` | import rules |
| `pytest tests/test_app.py` | CORS / error shape |

---

## 2. Front-end foundation & CI (US-1.2) — @Lemonada10

**What:** Vite + React Router, nav, API client, stub pages, GitHub Actions (`ruff` + `pytest` + `npm build`).

| How to test | Where in code |
|---|---|
| `cd frontend` → `npm run dev` → click Laundromats / My reservations / Login | `frontend/src/App.jsx`, `components/NavBar.jsx` |
| Call API via `api()` helper | `frontend/src/api.js`, `auth.js` |
| CI on every PR | `.github/workflows/ci.yml` |

---

## 3. Contract + conformance (US-1.3)

**What:** Hand-authored OpenAPI 3.1; live responses checked with JSON Schema.

| How to test | Where in code |
|---|---|
| `openapi-spec-validator ../contract/openapi.yaml` | `contract/openapi.yaml` |
| Terminal 1: `uvicorn …` · Terminal 2: `$env:CONFORMANCE_BASE_URL="http://127.0.0.1:8000"; pytest tests/conformance` | `backend/tests/conformance/` |

---

## 4. Register & log in (US-2.1)

**What:** `POST /auth/register` (always CUSTOMER), `POST /auth/login` → RS256 JWT with scopes. UI login/register pages.

| How to test (browser) | How to test (API / pytest) | Where in code |
|---|---|---|
| Register a new email → Login → nav shows Logout | `POST /auth/register` then `/auth/login` in `/docs` | API: `app/api/routes/auth.py`, `app/services/auth.py`, `app/core/tokens.py` |
| Hit a protected route without token → redirected / 401 | `pytest tests/test_auth_api.py tests/test_security.py` | UI: `pages/LoginPage.jsx`, `RegisterPage.jsx` |
| Forged / `alg=none` / wrong aud token rejected | same security tests | `app/api/security.py` |

---

## 5. Browse laundromats & free slots (US-3.1) — @Lemonada10

**What:** Public browse. List laundromats; pick a date; see AVAILABLE / UNAVAILABLE slots; Free links into hold.

| How to test (browser) | How to test (API / pytest) | Where in code |
|---|---|---|
| Open `/laundromats` → Spin City / Fresh Cycle | `GET /laundromats` | API: `app/api/routes/browse.py`, `app/services/browse.py` |
| Open a laundromat → change date → Free / Taken | `GET /laundromats/{id}/slots?date=YYYY-MM-DD` | Domain pin: `app/domain/availability.py`, `MachineSlot.is_available` |
| Seed if empty: `python scripts/seed_laundromats.py` | `pytest tests/test_browse_availability.py` | UI: `pages/LaundromatsPage.jsx`, `LaundromatSlotsPage.jsx`, `browse.js` |
| | Conformance: `tests/conformance/test_browse.py` | Repo read model: `SqlLaundromatRepository.reservable_slots_for_day` |

---

## 6. Hold a slot for 10 minutes (US-4.1)

**What:** Authenticated customer holds a free slot. Domain rule + row lock. Race test proves no double hold.

| How to test (browser) | How to test (API / pytest) | Where in code |
|---|---|---|
| Log in → Free slot → confirm email → Hold | `POST /slots/{slotId}/holds` + `Idempotency-Key` + Bearer | Domain: `app/domain/slot.py` → `place_hold` |
| Second browser as Bob on same slot → “taken” / 409 | `pytest tests/test_hold_race.py` (needs `TEST_DATABASE_URL`) | Service: `app/services/holds.py` → `place_hold` |
| | `pytest tests/test_service_place_hold.py tests/test_place_hold_api.py` | API: `app/api/routes/holds.py` |
| | Conformance: `tests/conformance/test_place_hold.py` | UI: `pages/HoldPage.jsx`, `holds.js` |

**Demo line:** “The slot is locked with `FOR UPDATE`; 20 parallel holds → one winner.”

---

## 7. Confirm my hold (US-4.2)

**What:** View hold + countdown; confirm before expiry → `CONFIRMED` reservation. Confirm again is naturally idempotent.

| How to test (browser) | How to test (API / pytest) | Where in code |
|---|---|---|
| After hold → `/holds/:holdId` → Confirm → lands on reservations | `GET /holds/{holdId}` · `POST /holds/{holdId}/confirm` | Domain: `MachineSlot.confirm` |
| Confirm twice → same `res_N` | `pytest tests/test_service_holds.py tests/test_holds_api.py` | Service: `HoldService.get_hold` / `confirm` |
| Bob opens Alice’s hold URL → not found | Conformance: `tests/conformance/test_holds.py` | UI: `pages/HoldReviewPage.jsx` |

---

## 8. My reservations — only mine (US-4.3) — @Lemonada10

**What:** List the caller’s bookings (newest first); fetch one by id; anyone else’s id → `404 not_found` (no leak).

| How to test (browser) | How to test (API / pytest) | Where in code |
|---|---|---|
| As Alice: confirm a hold → **My reservations** shows it | `GET /me/reservations` | Service: `app/services/reservations.py` |
| As Bob: same list does **not** show Alice’s booking | `GET /reservations/{id}` as other user → 404 | API: `app/api/routes/reservations.py` |
| Logged out → prompted to log in | `pytest tests/test_service_reservations.py tests/test_reservations_api.py` | List query: `SqlSlotRepository.list_for_user` |
| HELD row → opens hold page (timer + Confirm) | Conformance: `tests/conformance/test_reservations.py` | UI: `pages/ReservationsPage.jsx`, `reservations.js` |

---

## 9. Cancel a future reservation (US-5.3) — @Lemonada10

**What:** `DELETE /reservations/{id}` cancels **only before the slot starts** (proposal + contract). After start → `409 too_late_to_cancel`. Already cancelled → `204` again. Someone else’s → `404`. Slot becomes free again.

| How to test (browser) | How to test (API / pytest) | Where in code |
|---|---|---|
| Confirm a booking → **Cancel** → confirm dialog → status CANCELLED | `DELETE /reservations/{id}` | Domain: `MachineSlot.cancel` |
| Browse that slot → AVAILABLE again | `pytest` domain/service/API reservation tests | Service + route: `reservations.py` |
| | Conformance cancel cases in `test_reservations.py` | UI: Cancel button on `/reservations` |

---

## 10. Safe retries with an idempotency key (US-5.2)

**What:** If a hold's response is lost, the client retries with the **same** `Idempotency-Key` and gets the first answer back (same status and body, plus `Idempotency-Replayed: true`). It never gets a second hold. Whatever the first attempt got (201, 404 or 409) is replayed. The same key with another slot or email is `422 idempotency_key_reuse`. Keys are kept at least 24 hours, then the worker deletes them.

| How to test (browser) | How to test (API / pytest) | Where in code |
|---|---|---|
| Stop the API, click **Hold** → error + **Try again**; start the API, click **Try again** → one hold (same key reused) | Send the same `POST /slots/{slotId}/holds` twice with one `Idempotency-Key` → same `holdId`, 2nd has `Idempotency-Replayed: true` | Service: `app/services/idempotency.py` → `run_once` |
| | `pytest tests/test_service_idempotency.py tests/test_idempotency_api.py tests/test_idempotency_retention.py` | Table: `idempotency_records` (migration `0002`) |
| | `pytest tests/test_hold_race.py -k eight` (8 parallel copies → 1 hold, 7 replays; needs `TEST_DATABASE_URL`) | Worker job: `forget_old_idempotency_keys` in `worker.py` |
| | Conformance: replay cases in `tests/conformance/test_place_hold.py` | UI: `pages/HoldPage.jsx`, `holds.js` (`newAttemptKey`, retries) |

**Demo line:** “8 copies of one request at the same moment → one hold; the 7 others get the same hold replayed, never a 409.”

---

## 11. Today view, check-in and no-shows (US-7.2)

1. Start the API, frontend and `python worker.py`. On a development database, seed users first
   and then seed laundromats so the demo operator is assigned to the seeded locations.
2. In one browser session, log in as `alice@example.com` / `customer123`. Hold and confirm three
   different slots for today at the same laundromat. On **My reservations**, click **I'm here**
   for the first booking. Its status should become **Checked in**.
3. In a second browser session, log in as `operator@example.com` / `operator123`. Open **Today**
   in the navigation and select the same laundromat. Confirm that the first booking shows the
   arrival time and that the second says **Awaiting check-in**. Click **Mark present** on the second
   booking and refresh **My reservations** in the customer session to see **Checked in** there too.
4. Leave the third booking unchecked. At 15 minutes after the slot starts, allow up to 30 seconds
   for the worker and click **Refresh bookings**. Expect **No-show · Released to walk-ins**.
   Refresh **My reservations** to see `NO_SHOW`. The machine is released for in-person walk-ins
   for the rest of that slot. Online booking for a slot closes when it starts.
5. In a customer session, open `/operator/today` directly and confirm the site shows a permission error.

Check-in is allowed on a confirmed booking before the cutoff, including before the slot starts.
At the API, repeating the same check-in preserves its original `checkedInAt`. A cancelled
booking returns `409 already_cancelled`.

Run `python -m pytest tests/test_check_in.py` from `backend/` for the deadline and persistence
tests. The [backend test guide](../backend/README.md#contract-and-conformance) covers live HTTP tests.

## End-to-end happy path (all features)

1. Seed: `seed_users.py` + `seed_laundromats.py`
2. Open app → Register or login as Alice  
3. Laundromats → location → tomorrow → **Free**  
4. Hold → Confirm  
5. My reservations → see CONFIRMED row → **Cancel** (before start) → slot free again  
6. Logout → login as Bob → reservations empty / Alice’s `res_…` URL → error  
7. (Optional) Race pytest with `TEST_DATABASE_URL`

## Not required for Milestone 2 (later weeks)

Hold expiry worker, idempotency replay store, confirmation email (Resend), operator tools, check-in, health/Docker — Weeks 10–12 ([PROJECT_PLAN.md](../PROJECT_PLAN.md)).

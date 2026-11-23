# Proof tests: where each guarantee is tested

WashSlot promises five things: one booking per slot (**concurrency**), no double effects from a repeat
(**idempotency**), you only reach what's yours (**auth**), an abandoned hold frees its slot
(**expiry**), and a confirmed booking always gets its email (**outbox**). Each one is tested at three
levels, and a booking also survives a restart of every container (**persistence**).

- **Domain:** the rule itself, on plain objects. No database or HTTP, and it runs in microseconds.
- **Service:** a use case on the in-memory unit of work (`app/data/memory.py`), with a clock the test controls.
- **Conformance:** HTTP only, against any running server. Every response is judged by `contract/openapi.yaml`.

Some guarantees also need a real database (locks, constraints and races). Those tests are in the
**Database** row. They run when `TEST_DATABASE_URL` is set.

All paths are under `backend/tests/`.

## Concurrency: one slot, one booking

| Level | Tests |
|---|---|
| Domain | `test_domain_slot.py`: `test_live_hold_and_confirmed_reservation_take_the_slot`, `test_place_hold_on_a_taken_slot_is_slot_unavailable`, `test_the_same_customer_cannot_hold_the_same_slot_twice` |
| Service | `test_service_locks.py`: every write reads its row with `lock=True` first (hold, confirm, cancel, check-in by the customer or the operator, no-show, email retry). The memory store refuses any other save, and the tests fail if a service drops the lock. |
| Database | `test_hold_race.py`: 20 customers at once give 1 hold. 8 copies with one key give 1 hold and 7 replays. A control run without the lock shows only the unique index saves us. `test_emails.py::test_two_workers_never_claim_the_same_message`, `test_failed_emails.py` (the retry locks the row) |
| Conformance | `conformance/test_concurrency.py`: 10 customers hold one slot at the same moment: one 201, nine 409. Also: one key sent 8 times at once, 4 confirms at once, 4 cancels at once |

## Idempotency: a repeat changes nothing

| Level | Tests |
|---|---|
| Domain | `test_domain_slot.py`: `test_confirm_twice_returns_the_same_reservation_unchanged`, `test_cancel_twice_is_idempotent` · `test_failed_emails.py::test_retry_leaves_a_pending_or_sent_email_alone` · `test_check_in.py::test_first_arrival_just_before_deadline_and_retry_after_deadline` |
| Service | `test_service_idempotency.py`: replay, the stored answer, the same key for another request, keys per user. Also `test_service_holds.py::test_confirm_twice_gives_the_same_reservation`, `test_service_reservations.py::test_cancel_twice_is_ok`, `test_service_operator.py` (`test_the_switch_is_idempotent`, `test_creating_the_same_slots_again_creates_nothing`), `test_emails.py::test_confirming_again_does_not_write_a_second_email` |
| Database | `test_idempotency_api.py` (one hold and one record), `test_idempotency_retention.py` (keys are kept 24 h) |
| Conformance | `conformance/test_place_hold.py` (replays a 201 and a 404, a reused key is 422), `test_holds.py` (confirm again), `test_reservations.py` (cancel again), `test_check_in.py`, `test_operator.py` (create slots twice), `test_notifications.py` (retrying a SENT email), `test_concurrency.py` |

## Auth: you only reach what's yours

| Level | Tests |
|---|---|
| Domain | `test_domain_operator.py::test_only_the_laundromats_own_operator_runs_it` |
| Service | `test_service_auth.py` (registration can't pick a role; a wrong password and an unknown email give the same answer). Someone else's resource is `not_found` in `test_service_holds.py`, `test_service_reservations.py`, `test_service_operator.py`, `test_check_in.py` and `test_failed_emails.py` |
| Interface | `test_security.py`: tampered payload or subject, `alg=none`, HS256 signed with our public key, wrong audience or issuer, expired, another key, missing scope (403). `test_tokens.py`: password hashing and keys |
| Conformance | `conformance/test_token_tampering.py`: a customer who edits their token to add operator rights, use another user's id, or live longer gets 401 `invalid_token`, and so does an `alg=none` token. Every file also checks 401 without a token and 403 for a customer on operator routes |

## Expiry: an abandoned hold frees the slot

| Level | Tests |
|---|---|
| Domain | `test_domain_slot.py`: `test_a_hold_expires_exactly_at_expires_at`, `test_expire_stale_holds_marks_only_stale_holds`, `test_confirm_at_or_after_expiry_is_hold_expired`, `test_a_stale_hold_is_expired_first_and_the_slot_can_be_held` |
| Service | `test_expiry.py`: the slot is free again without the worker, a stale hold shows EXPIRED, a confirm exactly at expiry fails and one second before works, and the worker job is safe to run twice. `test_service_place_hold.py::test_the_hold_lasts_hold_minutes` |
| Database | `test_expiry.py` (the worker job on Postgres) |
| Conformance | `conformance/test_holds.py::test_a_new_hold_lasts_ten_minutes_by_the_servers_clock`. A black-box test can't wait 10 minutes, so it checks the window by the server's `Date` header. Expiry itself is proven above with a fake clock |

## Outbox: a confirmed booking gets exactly one email

| Level | Tests |
|---|---|
| Domain | `test_domain_outbox.py`: one PENDING email, due now, with everything needed to send it. Failed tries wait 30 s, 1, 2, 4 and 8 min, and the 6th failure is final. A 4xx fails at once. A sent email keeps no error. `test_failed_emails.py` covers the operator's retry rule |
| Service | `test_emails.py`: confirm writes one email (none when confirm is refused or repeated), the worker sends it once, two failures then SENT, FAILED after 6 tries, Resend gets `Idempotency-Key: outbox-{id}`. `test_failed_emails.py` covers the retry use case |
| Database | `test_emails.py`: the outbox row is written with the reservation, sent and recorded |
| Conformance | `conformance/test_outbox.py`: after a confirm (repeated, or 4 at once) the operator sees exactly one email for that booking, and none for a hold that was never confirmed. `test_notifications.py` covers the list and retry |

## Persistence: a booking survives the restart

`scripts/restart_check.py` (from the repository root, with Docker running):

1. It runs `docker compose up`, then books a slot as a new customer.
2. It runs `docker compose down` and `up` again, so every container is deleted and recreated.
3. It reads the booking back with the old token and logs in again.
4. It cancels the booking, so the slot is free.

The check fails if the data is lost: with `down --volumes` it stops at a 401.

It uses the database compose uses. By default that is Neon (`backend/.env`), so each local run leaves a
`restart-check-…@example.com` customer and a cancelled booking there. CI adds `compose.ci.yaml`, a
Postgres container with a named volume, so the database restarts too.

## How to run them

```bash
cd backend
pytest                                   # domain, service, interface; database tests too if TEST_DATABASE_URL is set
CONFORMANCE_BASE_URL=http://localhost:8000 pytest tests/conformance tests/conformance_v1_0   # a running server
cd .. && python scripts/restart_check.py                                                   # Docker running
```

CI runs all four on every pull request (`.github/workflows/ci.yml`):

- **Backend:** `pytest`.
- **Conformance:** both suites against a fresh, seeded Postgres.
- **Restart check:** the stack with `compose.ci.yaml`.
- **Frontend:** the build.

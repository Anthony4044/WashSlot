# WashSlot coding guide

How we build WashSlot. If the code and this guide disagree, fix the code or update the guide in the same PR.

## 1. The contract comes first

- **`contract/openapi.yaml` is the source of truth.** We write it by hand *before* the endpoint. FastAPI's generated `/docs` is not the contract: CI checks the generated document against the authored one.
- **Conformance tests** in `backend/tests/conformance/` call the running API and validate every response against the contract with JSON Schema. They **never import `app`**, so they would judge a Java implementation the same way.
- **Old conformance tests stay in CI forever.** If one fails, we broke a promise.
- **Schemas are strict.** Every object lists `required` and has `additionalProperties: false`. Every id has a `pattern`.
- **Descriptions carry meaning.** Every operation says whether it is safe, idempotent, or neither, and what a timed-out caller should do.
- **Changes:**
  - Additive changes are fine: a new path, a new *optional* field or parameter, a new error code.
  - Renaming, removing, retyping, or making something required is **breaking**. It needs `/v2` and a deprecation plan.

## 2. What goes on the wire

| Rule | Example |
|---|---|
| JSON is **camelCase**; Python stays snake_case | `expiresAt` on the wire, `expires_at` in code (`ResponseModel` / `RequestModel` do this) |
| Ids are **prefix + opaque number**, never meaningful | `lm_3`, `mch_12`, `slot_1842`, `hold_7251`, `res_7251`, `usr_9` (`app/services/ids.py`) |
| A malformed or wrong-prefix id | `404 not_found` |
| Lists are **wrapped in an object** | `{"laundromats": [...]}`, never a bare `[...]` |
| Times are RFC 3339 with offset, stored UTC | `"2026-11-20T18:00:00-05:00"` |
| Request bodies are strict | unknown fields → `422 invalid_request` |
| The caller is taken **from the token, never from the body** | no `userId` in request bodies |

## 3. Errors

- Every error body is exactly `{"error": "<code>"}`. The code is a stable, machine-readable word, never prose.
- **Who decides what:**
  - The domain and services raise or return the **code only**.
  - `app/api/errors.py` (`CATALOG`) is the **one** place that maps a code to a status.
  - The contract documents each code and whether it is retryable.
- **What the status tells the caller:**
  - **4xx** means fix the request and don't retry it as-is. **5xx** means retry with the same `Idempotency-Key`.
  - **401** (`missing_token`, `invalid_token`) means "we don't know who you are".
  - **403** (`insufficient_scope`) means "we know you, but you may not do this".
- Clients treat an unknown code as **not retryable**. That is what lets us add codes later.
- **Adding a code:** add it to `CATALOG`, then to the contract's error catalog, then use it.

## 4. Layers and the dependency rule

```
api/  ──►  services/  ──►  domain/  ◄──  data/
(HTTP)     (use cases)     (rules)       (SQLAlchemy)
```

| Layer | Folder | Owns | Must not |
|---|---|---|---|
| Interface | `app/api/` | routes, request/response DTOs, auth checks, code→status mapping | contain business rules or SQL |
| Service | `app/services/` | one method per use case, the transaction (unit of work), idempotency, ownership checks, building DTOs | import FastAPI or SQLAlchemy, know HTTP statuses |
| Domain | `app/domain/` | the rules, as methods on the aggregate (`MachineSlot`) | import **anything** from FastAPI, SQLAlchemy, Pydantic or other layers |
| Data | `app/data/` | row classes (`*Row`), repositories (Data Mapper), unit of work, in-memory doubles | know HTTP |

`tests/test_layers.py` reads the imports and fails CI if a layer breaks this rule.

- **Rich domain model, not anemic.**
  - A rule lives **on the object it protects**, as a method (`slot.place_hold(...)`, `slot.cancel(...)`).
  - It never lives in a `...Manager` or in a route.
  - It is stated **once**: `MachineSlot.is_available(now)` is *the* availability rule.
- **The aggregate.** `MachineSlot` is the root and its `Reservation`s live inside it.
  - Reservations are changed only through the slot.
  - There is no `ReservationRepository`: one aggregate, one repository (`uow.slots`).
- **The service hands out DTOs, never domain objects or rows.** It returns `Outcome.success(dto)` or `Outcome.failure("code")`, and `to_response()` in the API turns that into HTTP.
- **Where a rule belongs.** If it would still hold in a batch import or a migration script, it is domain. If it changes when HTTP becomes gRPC, it is interface.

### Writing a use case

```python
# app/services/holds.py
class HoldService:
    def __init__(self, uow_factory: UnitOfWorkFactory):
        self.uow_factory = uow_factory

    def place_hold(self, user_id: int, slot_id: int, email: str) -> Outcome:
        with self.uow_factory() as uow:                 # BEGIN: one use case, one transaction
            slot = uow.slots.get(slot_id, lock=True)    # SELECT ... FOR UPDATE on the root
            if slot is None:
                return Outcome.failure("not_found")
            now = uow.slots.now()                       # the database clock decides expiry
            hold = slot.place_hold(user_id, email, now) # the domain rule (raises SlotUnavailable)
            uow.slots.save(slot)
        return Outcome.success(hold_dto(hold))          # COMMIT happened on leaving the block
```

```python
# app/api/routes/holds.py — thin
@router.post("/slots/{slot_id}/holds", status_code=201)
def place_hold(slot_id: str, body: HoldRequest, user=Depends(require_scope("reservations:write")),
               uow_factory=Depends(get_uow_factory)):
    service = HoldService(uow_factory)
    return to_response(service.place_hold(user.id, parse_id(SLOT, slot_id), body.confirmation_email), 201)
```

## 5. Data

- **Data Mapper.** `app/data/repositories.py` turns rows into domain objects and back. The domain never sees a `*Row`.
- **Unit of work: the service layer opens it, one per use case.**
  - It commits when the block exits normally and rolls back on an exception.
  - Everything that must land together goes in one unit of work: the reservation **and** its idempotency record **and** its outbox event.
- **Commands load aggregates; queries may use read models.**
  - A list screen can compute availability in one SQL query (no N+1).
  - A test must then pin that read model to the domain rule, so the two can never drift.
  - Load eagerly what the rules read.
- **Migrations.**
  - Every table change is a new Alembic migration plus the matching row-class change. `test_schema.py` fails if they differ.
  - Changes are **expand → contract**: add the new thing, migrate, and drop the old thing only once nothing uses it. Never a one-step rename.
- **Tests use the in-memory doubles in `app/data/memory.py`.** Like the database, they copy on read, so an unsaved change is lost.

## 6. Concurrency

- **The contended resource is the slot.** We use **pessimistic locking**: `uow.slots.get(id, lock=True)` (`SELECT … FOR UPDATE` on the slot row). Read, decide and write all happen inside **one** unit of work.
- The decision (`if` / domain rule) runs in Python. The lock only keeps its premise true until commit.
- **Keep the transaction short.** No email, HTTP call or sleep inside it.
- To reach a reservation, **lock its slot**, never just the reservation row (`get_for_reservation(..., lock=True)`).
- **Lazy expiry.** `slot.expire_stale_holds(now)` runs before placing a hold, in the same transaction. Otherwise the partial unique index still counts the stale hold.
- The database rules (`CHECK`s, foreign keys, the partial unique index) are the **safety net**. The lock is the protection.
- **Race test pattern:** `threading.Barrier(n)` starts *n* threads at once against the real database. Then assert exactly one 201, the rest 409, and one row.

## 7. Idempotency

- `POST /slots/{slotId}/holds` **requires** `Idempotency-Key` (8–128 characters).
  - A missing key is `422 idempotency_key_required`.
  - The same key with a different body is `422 idempotency_key_reuse`.
- **"Same attempt"** means the same user, the same endpoint and the same body hash.
- **Replay the stored outcome, whatever it was.** A 201, a 404 or a 409 is replayed with the same status and body, plus the header `Idempotency-Replayed: true`.
- The record is written **in the same transaction** as the hold (`INSERT … ON CONFLICT DO NOTHING`). If 0 rows are inserted, a twin request won: roll back and replay its result.
- Keys are kept **at least 24 hours** (`IDEMPOTENCY_RETENTION_HOURS`). The sweep job deletes only older rows, using the database clock.
- **Lives in the service layer.** Not in the domain (it knows nothing about requests) and not in the route (another protocol would skip it).
- **Some operations are already idempotent, so no key is needed:**
  - Confirm: confirming again returns the same reservation.
  - Cancel (`DELETE`): cancelling again ends in the same state.
  - Check-in: checking in again does nothing.

## 8. Authentication, authorization, delegation

- **Tokens are JWTs signed with RS256**, using a key pair, never a shared secret.
  - The login endpoint signs with the **private** key (`keys/jwt_private.pem`, git-ignored).
  - Every other request is checked with the **public** key.
- **Every request checks everything:**
  - The signature, with `algorithms=["RS256"]`. We pick the algorithm, never the token.
  - `iss`, `aud` and `exp`.
  - The claims we rely on: `sub` (user id, e.g. `usr_9`) and `scope` (space-separated).
- **Never** use `verify_signature: False`, `alg: none`, or skip the audience check. There is a test for each of the three attacks: tampered payload, `alg=none`, wrong audience.
- **Scopes** pair an action with a resource:
  - `reservations:read`
  - `reservations:write`
  - `operator:manage`

  Give each token the least it needs. Browsing laundromats and slots is public and needs no token.
- **Registration always creates a CUSTOMER.** Operators are created only by the seed script.
- **Auth lives in the interface layer** as FastAPI dependencies. The domain never sees a token.
- **Ownership** ("is this *your* reservation?") is a **service-layer** check after loading the aggregate. Someone else's resource returns `404 not_found`, so we don't reveal that it exists.

## 9. Tests

| Level | Where | Speed | Pins |
|---|---|---|---|
| Domain | `tests/test_domain_*.py` | microseconds, no fixtures | the rules (`is_available`, `place_hold`, …) |
| Service | `tests/test_service_*.py` with `memory_uow` | milliseconds | use cases, idempotency, ownership |
| Database | `uow_factory`, `db_session` | ~1 s | repositories, locks, constraints, race tests |
| Conformance | `tests/conformance/` | against a running server | the contract, response by response |

Pin tests to **public interfaces**: the contract, the service methods, the domain methods. Never test private internals.

## 10. Checklist for every PR

- [ ] The contract was updated first, and the conformance tests cover the new or changed operations.
- [ ] Each rule sits on the domain object, the route is thin, and the service returns an `Outcome` with a DTO.
- [ ] New error codes are in `CATALOG` and in the contract.
- [ ] Table changes come with a new migration.
- [ ] Any write to a slot locks the slot, inside one unit of work.
- [ ] The user comes from the token, the ownership check is in the service, and the scope check is on the route.
- [ ] `ruff check .` and `pytest` pass.
- [ ] AI suggestions that were wrong are noted in `docs/ai-log.md`.

"""Service layer: one method per use case.

It orchestrates the domain, owns the transaction (opens one unit of work per use case), owns
idempotency, and returns DTOs / Outcomes - never live domain objects, never HTTP status codes.
It depends on app.domain and on the UnitOfWork interface below, never on FastAPI.
"""

"""Data source layer: Data Mapper over SQLAlchemy.

- tables/        SQLAlchemy row classes (*Row). They mirror the tables, carry no business rules.
- repositories   translate rows <-> pure domain objects (app.domain). The domain never sees a Row.
- unit_of_work   one transaction per use case; the service layer opens it, commit on exit.
- memory         in-memory doubles with the same interface, for fast service-layer tests.
"""

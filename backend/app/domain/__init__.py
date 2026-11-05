"""Domain model: the business rules, and nothing else.

Rule: this package imports NOTHING from fastapi, sqlalchemy, pydantic or app.api/app.data.
It never knows a database or HTTP exists (dependencies point inward). Check: read the imports.
"""

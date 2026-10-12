"""Shared fixtures for the model test suite.

These tests run against in-memory SQLite for speed and portability; they do
not need a real Postgres. That covers the structure, defaults, constraints
and relationships of the SQLAlchemy models. What SQLite CANNOT validate are
the Postgres triggers defined in database/schema.sql (the `expiration_date`
calculation and the native ENUMs) - those are covered in
tests/test_integration_postgres.py, which skips automatically when no test
Postgres database is configured (see that file).
"""
from __future__ import annotations

import pytest
from sqlalchemy import BigInteger, Column, String, Table, create_engine, event
from sqlalchemy.orm import Session

from app.models import Base, ShelfLifeRule

# `users` is not an ORM model of this app: in production it already exists
# in Postgres via database/schema.sql (or the real auth system). To exercise
# the full `pantry_inventory.user_id -> users.id` foreign key against the
# tests' SQLite, an equivalent stub is registered here in the same `MetaData`
# as Base.
users_table = Table(
    "users",
    Base.metadata,
    Column("id", BigInteger, primary_key=True),
    Column("email", String(255), nullable=False, unique=True),
    extend_existing=True,
)


@pytest.fixture()
def engine():
    """In-memory SQLite engine with the full `app.models` schema."""
    eng = create_engine("sqlite:///:memory:")

    # SQLite ships with foreign keys disabled; without this, the
    # ON DELETE SET NULL / CASCADE tests would exercise nothing real.
    @event.listens_for(eng, "connect")
    def _enable_sqlite_fk(dbapi_connection, connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def session(engine):
    with Session(engine) as db_session:
        yield db_session


@pytest.fixture()
def user_id(session) -> int:
    """Insert a stub user and return its id, for use as a foreign key."""
    session.execute(users_table.insert().values(id=1, email="test@example.com"))
    session.commit()
    return 1


@pytest.fixture()
def milk_rule(session) -> ShelfLifeRule:
    """Reference shelf-life rule (milk) reused across several tests."""
    rule = ShelfLifeRule(
        ingredient_name="Whole milk",
        category="dairy",
        default_storage="refrigerator",
        shelf_life_days_unopened=10,
        open_shelf_life_multiplier="0.70",
        frozen_shelf_life_days=90,
    )
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return rule

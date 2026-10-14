"""Integration tests against a real Postgres (optional; skipped without a DB).

These tests validate the one thing SQLite cannot: the
`calculate_pantry_expiration` trigger and the native ENUMs defined in
database/schema.sql. They skip automatically when no test database is
configured.

How to run them:
    1. Start the database (it applies the schema and both seeds on first boot):
         docker compose up -d
    2. Install the test dependencies, which include the psycopg driver these
       tests need:
         python -m pip install -r requirements-dev.txt
    3. Point the suite at the database and run it:
         $env:TEST_DATABASE_URL = "postgresql+psycopg://postgres:changeme@localhost:5432/zero_waste_sous_chef"
         python -m pytest tests/test_integration_postgres.py

Note the driver: `postgresql+psycopg://` is synchronous, unlike the
`postgresql+asyncpg://` URL the application itself uses. These assertions read
rows back inside one transaction and gain nothing from an event loop.

These tests only READ `shelf_life_rules`; they never modify the seed. They do
create one disposable `users` row per test and delete it afterwards, which
cascades to the `pantry_inventory` rows they inserted.
"""
from __future__ import annotations

import os
import uuid
from datetime import date, timedelta

import pytest

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason=(
        "TEST_DATABASE_URL is not configured: skipping the integration "
        "tests against a real Postgres (see the module docstring)."
    ),
)

if TEST_DATABASE_URL:
    from sqlalchemy import create_engine, select, text
    from sqlalchemy.orm import Session

    from app.models import PantryInventory, ShelfLifeRule


@pytest.fixture()
def pg_session():
    engine = create_engine(TEST_DATABASE_URL)
    with Session(engine) as session:
        yield session
        session.rollback()
    engine.dispose()


@pytest.fixture()
def seeded_milk_rule(pg_session) -> "ShelfLifeRule":
    rule = pg_session.scalar(
        select(ShelfLifeRule).where(ShelfLifeRule.ingredient_name == "Whole milk")
    )
    assert rule is not None, (
        "The seed is missing: apply database/seed_shelf_life_rules.sql to "
        "TEST_DATABASE_URL (or run `docker compose up -d`) before these tests."
    )
    return rule


@pytest.fixture()
def test_user_id(pg_session) -> int:
    """Create a throwaway user and remove it, with its rows, afterwards.

    The email carries a random suffix rather than the date, because a unique
    constraint on `users.email` would otherwise make a second run on the same
    day fail on the fixture instead of on an assertion.
    """
    # SQLAlchemy 2.0 refuses a bare SQL string: it must be wrapped in text().
    row = pg_session.execute(
        text("INSERT INTO users (email) VALUES (:email) RETURNING id"),
        {"email": f"pytest-{uuid.uuid4().hex[:12]}@example.com"},
    ).first()
    pg_session.commit()
    user_id = row[0]

    yield user_id

    # The tests commit, so a rollback would not undo them. Deleting the user
    # cascades to pantry_inventory (ON DELETE CASCADE in database/schema.sql),
    # which keeps repeated runs from accumulating rows.
    pg_session.rollback()
    pg_session.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
    pg_session.commit()


def test_trigger_sets_expiration_for_unopened_item(pg_session, test_user_id, seeded_milk_rule):
    item = PantryInventory(
        user_id=test_user_id,
        shelf_life_rule_id=seeded_milk_rule.id,
        display_name="Whole milk (test)",
        storage_location="refrigerator",
        purchase_date=date.today(),
    )
    pg_session.add(item)
    pg_session.commit()
    pg_session.refresh(item)

    expected = date.today() + timedelta(days=seeded_milk_rule.shelf_life_days_unopened)
    assert item.expiration_date == expected


def test_trigger_recalculates_when_item_is_opened(pg_session, test_user_id, seeded_milk_rule):
    item = PantryInventory(
        user_id=test_user_id,
        shelf_life_rule_id=seeded_milk_rule.id,
        display_name="Whole milk (test)",
        storage_location="refrigerator",
        purchase_date=date.today(),
    )
    pg_session.add(item)
    pg_session.commit()

    item.is_opened = True
    item.opened_date = date.today()
    pg_session.commit()
    pg_session.refresh(item)

    opened_days = round(
        seeded_milk_rule.shelf_life_days_unopened * float(seeded_milk_rule.open_shelf_life_multiplier)
    )
    expected = date.today() + timedelta(days=max(1, opened_days))
    assert item.expiration_date == expected


def test_custom_expiration_date_always_wins(pg_session, test_user_id, seeded_milk_rule):
    forced_date = date.today() + timedelta(days=999)
    item = PantryInventory(
        user_id=test_user_id,
        shelf_life_rule_id=seeded_milk_rule.id,
        display_name="Whole milk (test, manual date)",
        storage_location="refrigerator",
        custom_expiration_date=forced_date,
    )
    pg_session.add(item)
    pg_session.commit()
    pg_session.refresh(item)

    assert item.expiration_date == forced_date

"""Integration tests against a real Postgres (optional; skipped without a DB).

These tests validate the one thing SQLite cannot: the
`calculate_pantry_expiration` trigger and the native ENUMs defined in
database/schema.sql. They skip automatically when no test database is
configured.

How to run them:
    1. Create a disposable Postgres database for tests.
    2. Apply the schema and the seed:
         psql -d your_test_db -f database/schema.sql
         psql -d your_test_db -f database/seed_shelf_life_rules.sql
    3. Export the environment variable and run pytest:
         export TEST_DATABASE_URL="postgresql+psycopg://user:pass@localhost:5432/your_test_db"
         pytest tests/test_integration_postgres.py

These tests only READ, and add or delete rows in `pantry_inventory`; they do
not touch the seed contents of `shelf_life_rules`.
"""
from __future__ import annotations

import os
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
    from sqlalchemy import create_engine, select
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
        "Falta el seed: corre database/seed_shelf_life_rules.sql contra "
        "TEST_DATABASE_URL antes de ejecutar estos tests."
    )
    return rule


@pytest.fixture()
def test_user_id(pg_session) -> int:
    row = pg_session.execute(
        "INSERT INTO users (email) VALUES (:email) RETURNING id",
        {"email": f"pytest-{date.today().isoformat()}@example.com"},
    ).first()
    pg_session.commit()
    return row[0]


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

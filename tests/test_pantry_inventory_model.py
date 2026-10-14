"""Tests for the `PantryInventory` ORM model (the user's stock).

Note: `expiration_date` is calculated by a Postgres trigger
(`calculate_pantry_expiration`, see database/schema.sql) that does not exist
in the SQLite used here, so nothing is asserted about its computed value -
that is covered in tests/test_integration_postgres.py against a real
Postgres. What is validated here is everything that depends only on the
model: defaults, constraints and relationships.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import PantryInventory


def _make_item(**overrides):
    # `purchase_date` is set explicitly in Python (the same thing
    # `PantryInventoryCreate` does via Pydantic in the API layer) instead of
    # relying on the column's `server_default=CURRENT_DATE`: that default is
    # a fallback for direct SQL inserts, but comparing a date computed by the
    # database engine (UTC) against one computed in Python (local timezone)
    # is a race near UTC midnight, and not something a test should depend on.
    defaults = dict(
        display_name="Alqueria milk",
        storage_location="refrigerator",
        purchase_date=date.today(),
    )
    defaults.update(overrides)
    return PantryInventory(**defaults)


def test_create_item_with_defaults(session, user_id, milk_rule):
    item = _make_item(user_id=user_id, shelf_life_rule_id=milk_rule.id)
    session.add(item)
    session.commit()
    session.refresh(item)

    assert item.id is not None
    assert item.quantity == Decimal("1")
    assert item.unit == "unit"
    assert item.is_opened is False
    assert item.is_consumed is False
    assert item.consumed_at is None
    assert item.purchase_date == date.today()


def test_purchase_date_has_a_database_level_fallback_default(session, user_id, milk_rule):
    """When the caller omits it, the column still fills itself in.

    This is the `server_default=CURRENT_DATE` fallback, see
    app/models/pantry_inventory.py. It is deliberately not compared against
    Python's `date.today()`: `CURRENT_DATE` on SQLite and Postgres is
    evaluated in UTC and can differ by a day from the local clock right
    around UTC midnight. Only that it is populated is asserted.
    """
    item = PantryInventory(
        user_id=user_id,
        shelf_life_rule_id=milk_rule.id,
        display_name="Alqueria milk",
        storage_location="refrigerator",
    )
    session.add(item)
    session.commit()
    session.refresh(item)

    assert item.purchase_date is not None
    assert isinstance(item.purchase_date, date)


def test_shelf_life_rule_relationship(session, user_id, milk_rule):
    item = _make_item(user_id=user_id, shelf_life_rule_id=milk_rule.id)
    session.add(item)
    session.commit()
    session.refresh(item)

    assert item.shelf_life_rule is not None
    assert item.shelf_life_rule.ingredient_name == "Whole milk"
    assert item in milk_rule.pantry_items


def test_item_without_catalog_rule_is_allowed(session, user_id):
    """A "free" (uncatalogued) item must be creatable without `shelf_life_rule_id`."""
    item = _make_item(user_id=user_id, shelf_life_rule_id=None)
    session.add(item)
    session.commit()
    assert item.shelf_life_rule is None


def test_quantity_cannot_be_negative(session, user_id, milk_rule):
    item = _make_item(user_id=user_id, shelf_life_rule_id=milk_rule.id, quantity=Decimal("-1"))
    session.add(item)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_opened_date_cannot_precede_purchase_date(session, user_id, milk_rule):
    today = date.today()
    item = _make_item(
        user_id=user_id,
        shelf_life_rule_id=milk_rule.id,
        purchase_date=today,
        is_opened=True,
        opened_date=today - timedelta(days=1),
    )
    session.add(item)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_is_opened_requires_opened_date(session, user_id, milk_rule):
    item = _make_item(
        user_id=user_id,
        shelf_life_rule_id=milk_rule.id,
        is_opened=True,
        opened_date=None,
    )
    session.add(item)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_is_opened_with_opened_date_is_valid(session, user_id, milk_rule):
    item = _make_item(
        user_id=user_id,
        shelf_life_rule_id=milk_rule.id,
        is_opened=True,
        opened_date=date.today(),
    )
    session.add(item)
    session.commit()
    assert item.is_opened is True


def test_consumed_at_requires_is_consumed_true(session, user_id, milk_rule):
    item = _make_item(
        user_id=user_id,
        shelf_life_rule_id=milk_rule.id,
        is_consumed=False,
        consumed_at=date.today(),  # any non-null value must fail
    )
    session.add(item)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_deleting_shelf_life_rule_sets_fk_null(session, user_id, milk_rule):
    """`ON DELETE SET NULL`: deleting the catalog rule must not delete the stock."""
    item = _make_item(user_id=user_id, shelf_life_rule_id=milk_rule.id)
    session.add(item)
    session.commit()
    item_id = item.id

    session.delete(milk_rule)
    session.commit()

    refreshed = session.get(PantryInventory, item_id)
    assert refreshed is not None
    assert refreshed.shelf_life_rule_id is None


def test_repr_contains_display_name(session, user_id, milk_rule):
    item = _make_item(user_id=user_id, shelf_life_rule_id=milk_rule.id)
    session.add(item)
    session.commit()
    assert "Alqueria milk" in repr(item)

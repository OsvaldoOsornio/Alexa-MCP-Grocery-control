"""Tests for the `pantry_inventory` Pydantic v2 schemas."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas import PantryInventoryCreate, PantryInventoryUpdate


def _valid_payload(**overrides) -> dict:
    payload = dict(display_name="Alqueria milk", shelf_life_rule_id=1)
    payload.update(overrides)
    return payload


def test_create_schema_accepts_minimal_valid_payload():
    item = PantryInventoryCreate(**_valid_payload())
    assert item.quantity == Decimal("1")
    assert item.unit == "unit"
    assert item.storage_location == "pantry"
    assert item.is_opened is False
    assert item.purchase_date == date.today()


def test_negative_quantity_is_rejected():
    with pytest.raises(ValidationError):
        PantryInventoryCreate(**_valid_payload(quantity=Decimal("-1")))


def test_is_opened_without_opened_date_is_rejected():
    with pytest.raises(ValidationError):
        PantryInventoryCreate(**_valid_payload(is_opened=True, opened_date=None))


def test_is_opened_with_opened_date_is_accepted():
    item = PantryInventoryCreate(
        **_valid_payload(is_opened=True, opened_date=date.today())
    )
    assert item.is_opened is True
    assert item.opened_date == date.today()


def test_opened_date_before_purchase_date_is_rejected():
    today = date.today()
    with pytest.raises(ValidationError):
        PantryInventoryCreate(
            **_valid_payload(
                purchase_date=today,
                is_opened=True,
                opened_date=today - timedelta(days=1),
            )
        )


def test_unknown_storage_location_is_rejected():
    with pytest.raises(ValidationError):
        PantryInventoryCreate(**_valid_payload(storage_location="cupboard_of_wonders"))


def test_update_schema_allows_marking_item_consumed():
    update = PantryInventoryUpdate(is_consumed=True)
    assert update.is_consumed is True
    assert update.quantity is None  # el resto de campos sigue opcional

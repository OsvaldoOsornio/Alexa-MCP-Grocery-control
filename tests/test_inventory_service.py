"""Pruebas unitarias de las operaciones de inventario para las tools MCP."""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models import StorageLocation
from app.services.inventory import get_inventory_status, modify_item_state


class MappingResult:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows


class ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


def test_get_inventory_status_uses_user_scope_and_serializable_values():
    session = SimpleNamespace(
        execute=AsyncMock(
            return_value=MappingResult(
                [
                    {
                        "id": 4,
                        "user_id": 12,
                        "display_name": "Leche",
                        "ingredient_name": "Leche entera",
                        "category": "dairy",
                        "storage_location": "refrigerator",
                        "quantity": Decimal("1.50"),
                        "unit": "litros",
                        "is_opened": False,
                        "expiration_date": date(2026, 10, 10),
                        "days_remaining": 3,
                        "status": "expiring_soon",
                    }
                ]
            )
        )
    )

    result = asyncio.run(get_inventory_status(session, user_id=12))

    statement, parameters = session.execute.await_args.args
    assert "v_pantry_inventory_status" in str(statement)
    assert "WHERE user_id = :user_id" in str(statement)
    assert parameters == {"user_id": 12, "include_consumed": False}
    assert result["count"] == 1
    assert result["items"][0]["quantity"] == "1.50"
    assert result["items"][0]["expiration_date"] == "2026-10-10"


def test_modify_item_state_updates_opened_consumed_and_location():
    item = SimpleNamespace(
        id=4,
        user_id=12,
        display_name="Leche",
        purchase_date=date(2026, 10, 1),
        is_opened=False,
        opened_date=None,
        storage_location=StorageLocation.REFRIGERATOR,
        is_consumed=False,
        consumed_at=None,
        expiration_date=date(2026, 10, 11),
    )
    session = SimpleNamespace(
        execute=AsyncMock(return_value=ScalarResult(item)),
        commit=AsyncMock(),
        refresh=AsyncMock(),
    )

    result = asyncio.run(
        modify_item_state(
            session,
            user_id=12,
            item_id=4,
            is_opened=True,
            storage_location=StorageLocation.FREEZER,
            is_consumed=True,
        )
    )

    assert item.is_opened is True
    assert item.opened_date == date.today()
    assert item.storage_location is StorageLocation.FREEZER
    assert item.is_consumed is True
    assert isinstance(item.consumed_at, datetime)
    assert item.consumed_at.tzinfo == timezone.utc
    assert result["success"] is True
    assert result["item"]["expiration_date"] == "2026-10-11"
    session.commit.assert_awaited_once()
    session.refresh.assert_awaited_once_with(item)


def test_modify_item_state_rejects_opened_date_without_opened_state():
    session = SimpleNamespace(execute=AsyncMock())

    with pytest.raises(ValueError, match="requiere is_opened=True"):
        asyncio.run(
            modify_item_state(
                session,
                user_id=12,
                item_id=4,
                opened_date=date.today(),
            )
        )

    session.execute.assert_not_awaited()
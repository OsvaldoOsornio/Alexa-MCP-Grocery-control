"""Pruebas unitarias de las operaciones de inventario para las tools MCP."""
from __future__ import annotations

import asyncio
import base64
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.models import PantryInventory, StorageLocation
from app.services import inventory as inventory_service
from app.services.inventory import (
    get_inventory_status,
    ingest_receipt_items,
    modify_item_state,
)


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


class ScalarCollectionResult:
    def __init__(self, values):
        self.values = values

    def scalars(self):
        return self

    def all(self):
        return self.values


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


def test_ingest_receipt_items_uses_bedrock_and_inserts_catalogued_models(monkeypatch):
    extracted_items = {
        "items": [
            {
                "display_name": "Leche entera",
                "ingredient_name": "Leche entera",
                "quantity": 2,
                "unit": "litros",
            },
            {
                "display_name": "Galletas",
                "ingredient_name": None,
                "quantity": 1,
                "unit": "paquete",
            },
        ]
    }

    class FakeBedrockClient:
        request = None

        def converse(self, **kwargs):
            self.request = kwargs
            return {
                "output": {
                    "message": {
                        "content": [
                            {
                                "text": (
                                    "```json\n"
                                    f"{json.dumps(extracted_items)}\n"
                                    "```"
                                )
                            }
                        ]
                    }
                }
            }

    bedrock_client = FakeBedrockClient()
    monkeypatch.setattr(
        inventory_service.boto3,
        "client",
        lambda service_name, region_name: bedrock_client,
    )
    milk_rule = SimpleNamespace(
        id=8,
        ingredient_name="Leche entera",
        default_storage=StorageLocation.REFRIGERATOR,
        shelf_life_days_unopened=10,
    )
    refreshed_items = []

    async def refresh_from_database(item):
        assert item.expiration_date is None
        item.id = 100 + len(refreshed_items)
        if item.shelf_life_rule_id == milk_rule.id:
            item.expiration_date = date.today() + timedelta(
                days=milk_rule.shelf_life_days_unopened
            )
        refreshed_items.append(item)

    session = SimpleNamespace(
        execute=AsyncMock(return_value=ScalarCollectionResult([milk_rule])),
        add_all=Mock(),
        commit=AsyncMock(),
        rollback=AsyncMock(),
        refresh=AsyncMock(side_effect=refresh_from_database),
    )
    receipt_image = b"fake-receipt-image"
    image_base64 = base64.b64encode(receipt_image).decode("ascii")

    result = asyncio.run(
        ingest_receipt_items(
            session,
            user_id=17,
            image_base64=image_base64,
            media_type="image/jpeg",
        )
    )

    request = bedrock_client.request
    assert request["modelId"] == inventory_service.get_settings().bedrock_model_id
    image_block = request["messages"][0]["content"][1]["image"]
    assert image_block == {
        "format": "jpeg",
        "source": {"bytes": receipt_image},
    }
    assert "Leche entera" in request["messages"][0]["content"][0]["text"]

    session.execute.assert_awaited_once()
    session.commit.assert_awaited_once()
    inserted_items = session.add_all.call_args.args[0]
    assert len(inserted_items) == 2
    assert all(isinstance(item, PantryInventory) for item in inserted_items)
    assert inserted_items[0].user_id == 17
    assert inserted_items[0].shelf_life_rule_id == 8
    assert inserted_items[0].storage_location is StorageLocation.REFRIGERATOR
    assert inserted_items[1].shelf_life_rule_id is None
    assert inserted_items[1].storage_location is StorageLocation.PANTRY
    assert result["success"] is True
    assert result["count"] == 2
    assert result["items"][0]["expiration_date"] == (
        date.today() + timedelta(days=milk_rule.shelf_life_days_unopened)
    ).isoformat()
    assert result["items"][1]["expiration_date"] is None


def test_ingest_receipt_items_rejects_invalid_base64_before_database_access():
    session = SimpleNamespace(execute=AsyncMock())

    with pytest.raises(ValueError, match="base64 válido"):
        asyncio.run(
            ingest_receipt_items(
                session,
                user_id=17,
                image_base64="not base64!",
            )
        )

    session.execute.assert_not_awaited()
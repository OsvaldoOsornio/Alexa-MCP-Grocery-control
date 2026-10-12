"""Inventory operations used by the MCP tools."""
from __future__ import annotations

import asyncio
import base64
import binascii
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.config import get_settings
from app.models import PantryInventory, ShelfLifeRule, StorageLocation
from app.schemas import PantryInventoryCreate
from app.services import bedrock

MAX_RECEIPT_IMAGE_BYTES = 5 * 1024 * 1024
IMAGE_FORMATS = {
    "image/jpeg": "jpeg",
    "image/png": "png",
    "image/gif": "gif",
    "image/webp": "webp",
}


class ReceiptLineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=150)
    ingredient_name: str | None = Field(default=None, max_length=100)
    quantity: Decimal = Field(default=Decimal("1"), ge=0, max_digits=10, decimal_places=2)
    unit: str = Field(default="unit", min_length=1, max_length=20)

    @field_validator("display_name", "unit")
    @classmethod
    def strip_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Name and unit cannot be empty.")
        return stripped


class ReceiptExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ReceiptLineItem] = Field(max_length=100)


def _extract_receipt_items_from_bedrock(
    image_bytes: bytes, image_format: str, catalog_names: list[str]
) -> list[ReceiptLineItem]:
    settings = get_settings()
    client = bedrock.get_client()
    catalog = json.dumps(catalog_names, ensure_ascii=False)
    response = client.converse(
        modelId=settings.bedrock_model_id,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "text": (
                            "Extract the food products from this receipt. "
                            "Return valid JSON only, in exactly this shape: "
                            '{"items":[{"display_name":"name as printed",'
                            '"ingredient_name":"exact catalog name or null",'
                            '"quantity":1,"unit":"unit"}]}. '
                            "Do not invent products or quantities. Take quantity and "
                            "unit from the receipt; when no quantity is clear, use 1 "
                            'and "unit". ingredient_name may only be a name from this '
                            f"list, or null when nothing matches: {catalog}"
                        )
                    },
                    {
                        "image": {
                            "format": image_format,
                            "source": {"bytes": image_bytes},
                        }
                    },
                ],
            }
        ],
        inferenceConfig={"maxTokens": 2048, "temperature": 0},
    )
    extraction = bedrock.parse_json_response(response, ReceiptExtraction, "receipt")
    return extraction.items


def _decode_receipt_image(image_base64: str, media_type: str) -> tuple[bytes, str]:
    image_format = IMAGE_FORMATS.get(media_type.lower())
    if image_format is None:
        raise ValueError("media_type must be image/jpeg, image/png, image/gif or image/webp.")
    if not image_base64 or len(image_base64) > 4 * ((MAX_RECEIPT_IMAGE_BYTES + 2) // 3):
        raise ValueError("The image is empty or larger than the 5 MB maximum.")
    try:
        image_bytes = base64.b64decode(image_base64, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError("image_base64 does not contain valid base64.") from error
    if not image_bytes or len(image_bytes) > MAX_RECEIPT_IMAGE_BYTES:
        raise ValueError("The image is empty or larger than the 5 MB maximum.")
    return image_bytes, image_format


async def ingest_receipt_items(
    session: AsyncSession,
    user_id: int,
    image_base64: str,
    media_type: str = "image/jpeg",
) -> dict[str, Any]:
    """Extract products from a receipt with Bedrock and insert the inventory rows."""
    image_bytes, image_format = _decode_receipt_image(image_base64, media_type)
    rules_result = await session.execute(select(ShelfLifeRule))
    rules = rules_result.scalars().all()
    rules_by_name = {rule.ingredient_name.casefold(): rule for rule in rules}
    extracted_items = await asyncio.to_thread(
        _extract_receipt_items_from_bedrock,
        image_bytes,
        image_format,
        [rule.ingredient_name for rule in rules],
    )

    inventory_items: list[PantryInventory] = []
    for extracted in extracted_items:
        rule = rules_by_name.get((extracted.ingredient_name or "").strip().casefold())
        item_data = PantryInventoryCreate(
            shelf_life_rule_id=rule.id if rule else None,
            display_name=extracted.display_name,
            quantity=extracted.quantity,
            unit=extracted.unit,
            storage_location=rule.default_storage if rule else StorageLocation.PANTRY,
        )
        inventory_items.append(
            PantryInventory(user_id=user_id, **item_data.model_dump())
        )

    if not inventory_items:
        return {"success": True, "user_id": user_id, "count": 0, "items": []}

    try:
        session.add_all(inventory_items)
        await session.commit()
        for item in inventory_items:
            await session.refresh(item)
    except Exception:
        await session.rollback()
        raise

    return {
        "success": True,
        "user_id": user_id,
        "count": len(inventory_items),
        "items": [
            {
                "id": item.id,
                "display_name": item.display_name,
                "quantity": _serialize_value(item.quantity),
                "unit": item.unit,
                "shelf_life_rule_id": item.shelf_life_rule_id,
                "storage_location": _serialize_value(item.storage_location),
                "expiration_date": _serialize_value(item.expiration_date),
            }
            for item in inventory_items
        ],
    }


def _serialize_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


async def get_inventory_status(
    session: AsyncSession, user_id: int, include_consumed: bool = False
) -> dict[str, Any]:
    """Read the status PostgreSQL calculated for the user's inventory."""
    result = await session.execute(
        text(
            """
            SELECT id, user_id, display_name, ingredient_name, category,
                   storage_location, quantity, unit, is_opened, expiration_date,
                   days_remaining, status
            FROM v_pantry_inventory_status
            WHERE user_id = :user_id
              AND (:include_consumed OR status <> 'consumed')
            ORDER BY days_remaining NULLS LAST, expiration_date NULLS LAST, id
            """
        ),
        {"user_id": user_id, "include_consumed": include_consumed},
    )
    items = [
        {key: _serialize_value(value) for key, value in row.items()}
        for row in result.mappings().all()
    ]
    return {"user_id": user_id, "count": len(items), "items": items}


async def modify_item_state(
    session: AsyncSession,
    user_id: int,
    item_id: int,
    *,
    is_opened: bool | None = None,
    opened_date: date | None = None,
    storage_location: StorageLocation | None = None,
    is_consumed: bool | None = None,
) -> dict[str, Any]:
    """Modify the allowed state; the expiry date is left to the trigger."""
    if all(
        value is None
        for value in (is_opened, opened_date, storage_location, is_consumed)
    ):
        raise ValueError("Provide at least one state field to modify.")
    if opened_date is not None and is_opened is not True:
        raise ValueError("opened_date requires is_opened=True.")

    result = await session.execute(
        select(PantryInventory)
        .where(PantryInventory.id == item_id, PantryInventory.user_id == user_id)
        .with_for_update()
    )
    item = result.scalar_one_or_none()
    if item is None:
        return {"success": False, "error": "No such item for this user."}

    if is_opened is True:
        effective_opened_date = opened_date or item.opened_date or date.today()
        if effective_opened_date < item.purchase_date:
            raise ValueError("opened_date cannot be earlier than purchase_date.")
        item.is_opened = True
        item.opened_date = effective_opened_date
    elif is_opened is False:
        item.is_opened = False
        item.opened_date = None

    if storage_location is not None:
        item.storage_location = storage_location

    if is_consumed is not None:
        if is_consumed and not item.is_consumed:
            item.consumed_at = datetime.now(timezone.utc)
        elif not is_consumed:
            item.consumed_at = None
        item.is_consumed = is_consumed

    await session.commit()
    await session.refresh(item)
    return {
        "success": True,
        "item": {
            "id": item.id,
            "user_id": item.user_id,
            "display_name": item.display_name,
            "storage_location": _serialize_value(item.storage_location),
            "is_opened": item.is_opened,
            "opened_date": _serialize_value(item.opened_date),
            "is_consumed": item.is_consumed,
            "consumed_at": _serialize_value(item.consumed_at),
            "expiration_date": _serialize_value(item.expiration_date),
        },
    }
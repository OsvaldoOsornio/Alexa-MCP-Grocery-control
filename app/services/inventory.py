"""Operaciones de inventario utilizadas por las tools MCP."""
from __future__ import annotations

import asyncio
import base64
import binascii
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any

import boto3
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.config import get_settings
from app.models import PantryInventory, ShelfLifeRule, StorageLocation
from app.schemas import PantryInventoryCreate

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
    unit: str = Field(default="unidad", min_length=1, max_length=20)

    @field_validator("display_name", "unit")
    @classmethod
    def strip_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("El nombre y la unidad no pueden estar vacíos.")
        return stripped


class ReceiptExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ReceiptLineItem] = Field(max_length=100)


def _extract_receipt_items_from_bedrock(
    image_bytes: bytes, image_format: str, catalog_names: list[str]
) -> list[ReceiptLineItem]:
    settings = get_settings()
    client = boto3.client("bedrock-runtime", region_name=settings.aws_region)
    catalog = json.dumps(catalog_names, ensure_ascii=False)
    response = client.converse(
        modelId=settings.bedrock_model_id,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "text": (
                            "Extrae los productos alimentarios de este recibo. "
                            "Devuelve únicamente JSON válido con esta forma: "
                            '{"items":[{"display_name":"nombre visible",'
                            '"ingredient_name":"nombre exacto del catálogo o null",'
                            '"quantity":1,"unit":"unidad"}]}. '
                            "No inventes productos ni cantidades. Usa quantity y unit "
                            "según el recibo; si no hay cantidad clara usa 1 y unidad. "
                            "ingredient_name solo puede ser un nombre de esta lista, "
                            f"o null si no coincide: {catalog}"
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
    content = response.get("output", {}).get("message", {}).get("content", [])
    response_text = "\n".join(
        block["text"] for block in content if isinstance(block.get("text"), str)
    ).strip()
    if response_text.startswith("```") and response_text.endswith("```"):
        response_text = response_text[3:-3].strip()
        if response_text.startswith("json"):
            response_text = response_text[4:].strip()
    if not response_text:
        raise ValueError("Bedrock no devolvió contenido JSON con artículos.")

    try:
        payload = json.loads(response_text)
        extraction = ReceiptExtraction.model_validate(payload)
    except (json.JSONDecodeError, ValueError) as error:
        raise ValueError("Bedrock devolvió un JSON de recibo inválido.") from error
    return extraction.items


def _decode_receipt_image(image_base64: str, media_type: str) -> tuple[bytes, str]:
    image_format = IMAGE_FORMATS.get(media_type.lower())
    if image_format is None:
        raise ValueError("media_type debe ser image/jpeg, image/png, image/gif o image/webp.")
    if not image_base64 or len(image_base64) > 4 * ((MAX_RECEIPT_IMAGE_BYTES + 2) // 3):
        raise ValueError("La imagen está vacía o supera el máximo de 5 MB.")
    try:
        image_bytes = base64.b64decode(image_base64, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError("image_base64 no contiene base64 válido.") from error
    if not image_bytes or len(image_bytes) > MAX_RECEIPT_IMAGE_BYTES:
        raise ValueError("La imagen está vacía o supera el máximo de 5 MB.")
    return image_bytes, image_format


async def ingest_receipt_items(
    session: AsyncSession,
    user_id: int,
    image_base64: str,
    media_type: str = "image/jpeg",
) -> dict[str, Any]:
    """Extrae productos de un recibo con Bedrock e inserta las filas del inventario."""
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
    """Lee el estado calculado por PostgreSQL para el inventario del usuario."""
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
    """Modifica estado permitido; la fecha de caducidad queda a cargo del trigger."""
    if all(
        value is None
        for value in (is_opened, opened_date, storage_location, is_consumed)
    ):
        raise ValueError("Indica al menos un campo de estado para modificar.")
    if opened_date is not None and is_opened is not True:
        raise ValueError("opened_date requiere is_opened=True.")

    result = await session.execute(
        select(PantryInventory)
        .where(PantryInventory.id == item_id, PantryInventory.user_id == user_id)
        .with_for_update()
    )
    item = result.scalar_one_or_none()
    if item is None:
        return {"success": False, "error": "No existe ese artículo para este usuario."}

    if is_opened is True:
        effective_opened_date = opened_date or item.opened_date or date.today()
        if effective_opened_date < item.purchase_date:
            raise ValueError("opened_date no puede ser anterior a purchase_date.")
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
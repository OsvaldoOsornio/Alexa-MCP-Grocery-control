"""Operaciones de inventario utilizadas por las tools MCP."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PantryInventory, StorageLocation


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
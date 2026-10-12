"""Spoken context that overrides the catalog's shelf-life estimate.

This is the cheapest high-value operation in the project because the database
already supports it. The `calculate_pantry_expiration` trigger honours
`custom_expiration_date` above every other branch (see database/schema.sql),
so writing that single column overrides the whole rules engine. No schema
change is needed.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PantryInventory, RipenessModifier, ShelfLifeRule

# Days from today that each spoken modifier implies. `UNDERRIPE` is the only
# one that extends rather than shortens, so it is handled separately below.
RIPENESS_DAYS: dict[RipenessModifier, int] = {
    RipenessModifier.VERY_RIPE: 1,
    RipenessModifier.RIPE: 3,
    RipenessModifier.SMELLS_OFF: 0,
    RipenessModifier.OPENED_LONG_AGO: 1,
}

UNDERRIPE_EXTRA_DAYS = 3

# More than this many candidates and we ask the caller to be specific rather
# than listing an unusable number of names back to a voice interface.
MAX_CANDIDATES = 5


def _resolve_target_date(
    modifier: RipenessModifier, current_expiration: date | None, today: date
) -> date:
    """Translate a spoken modifier into the date to write."""
    if modifier is RipenessModifier.UNDERRIPE:
        # Extends from whichever is later: the computed date or today. An
        # already-expired item does not become fresh by being called unripe.
        base = max(current_expiration, today) if current_expiration else today
        return base + timedelta(days=UNDERRIPE_EXTRA_DAYS)
    return today + timedelta(days=RIPENESS_DAYS[modifier])


async def update_pantry_context(
    session: AsyncSession,
    user_id: int,
    item_name: str,
    modifier: RipenessModifier,
) -> dict[str, Any]:
    """Adjust an item's shelf life from what the person observed out loud.

    `item_name` is matched case-insensitively against both the display name
    and the catalog ingredient name. An ambiguous match writes nothing and
    returns the candidates, so a conversational client can ask a follow-up
    question instead of guessing.
    """
    needle = item_name.strip()
    if not needle:
        raise ValueError("item_name cannot be empty.")

    pattern = f"%{needle}%"
    result = await session.execute(
        select(PantryInventory)
        .outerjoin(
            ShelfLifeRule, ShelfLifeRule.id == PantryInventory.shelf_life_rule_id
        )
        .where(
            PantryInventory.user_id == user_id,
            PantryInventory.is_consumed.is_(False),
            or_(
                PantryInventory.display_name.ilike(pattern),
                ShelfLifeRule.ingredient_name.ilike(pattern),
            ),
        )
        .order_by(PantryInventory.purchase_date.desc(), PantryInventory.id.desc())
    )
    matches = list(result.scalars().all())

    if not matches:
        return {
            "success": False,
            "error": f"No unconsumed item matching {needle!r} for this user.",
            "candidates": [],
        }

    # An exact display-name match wins outright; it is the common case when a
    # client echoes back a name it previously read from the inventory.
    exact = [item for item in matches if item.display_name.casefold() == needle.casefold()]
    if len(exact) == 1:
        matches = exact
    elif len(matches) > 1:
        return {
            "success": False,
            "error": (
                f"{len(matches)} items match {needle!r}. "
                "Repeat the request with one of the candidate names."
            ),
            "candidates": [item.display_name for item in matches[:MAX_CANDIDATES]],
        }

    item = matches[0]
    today = date.today()
    previous_expiration = item.expiration_date
    item.custom_expiration_date = _resolve_target_date(
        modifier, previous_expiration, today
    )

    await session.commit()
    await session.refresh(item)

    new_expiration = item.expiration_date
    return {
        "success": True,
        "item": {
            "id": item.id,
            "display_name": item.display_name,
            "modifier": modifier.value,
            "previous_expiration_date": (
                previous_expiration.isoformat() if previous_expiration else None
            ),
            "expiration_date": (
                new_expiration.isoformat() if new_expiration else None
            ),
            "days_remaining": (
                (new_expiration - today).days if new_expiration else None
            ),
            "discard_recommended": modifier is RipenessModifier.SMELLS_OFF,
        },
    }

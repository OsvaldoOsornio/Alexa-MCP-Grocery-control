"""Recipe generation and adaptation over the live pantry.

This is the second Amazon Bedrock call in the project, and it is a different
kind of call from the first. `ingest_receipt_items` extracts; this one
reasons: it is given the inventory ordered by how soon each item expires and
asked to build a dish that consumes the most urgent ones first.

Two modes share one tool so a mid-cook re-plan is a single round trip:

* no `prior_recipe`      -> generate a recipe from what is in the pantry
* `prior_recipe` present -> adapt it, dropping anything in `exclude_items`
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.services import bedrock
from app.services.inventory import get_inventory_status

# Assumed to be in every kitchen, so the model may use them without them
# appearing in the inventory. Anything else it wants goes in `missing`.
ASSUMED_STAPLES = ["salt", "pepper", "cooking oil", "water"]

# Statuses worth cooking with. `expired` and `consumed` are excluded: the
# product exists to prevent waste, not to recommend eating spoiled food.
COOKABLE_STATUSES = {"fresh", "expiring_soon", "unknown"}

MAX_INVENTORY_ITEMS = 60


class RecipeIngredient(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=150)
    quantity: str = Field(min_length=1, max_length=50)
    from_pantry: bool = True


class Recipe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=150)
    servings: int = Field(ge=1, le=12)
    total_minutes: int = Field(ge=1, le=600)
    # Required on purpose: this is what the UI highlights and what shows the
    # agent actually prioritised by expiry rather than inventing a dish.
    uses_expiring: list[str] = Field(max_length=20)
    ingredients: list[RecipeIngredient] = Field(max_length=40)
    steps: list[str] = Field(min_length=1, max_length=25)
    missing: list[str] = Field(default_factory=list, max_length=20)


def _cookable(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep what is worth cooking, soonest-expiring first.

    `get_inventory_status` already orders by `days_remaining` with nulls
    last, so this preserves that order rather than re-sorting.
    """
    return [item for item in items if item.get("status") in COOKABLE_STATUSES][
        :MAX_INVENTORY_ITEMS
    ]


def _pantry_lines(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reduce inventory rows to the fields the model needs to plan a dish."""
    return [
        {
            "name": item["display_name"],
            "quantity": f"{item['quantity']} {item['unit']}",
            "days_remaining": item.get("days_remaining"),
            "status": item.get("status"),
        }
        for item in items
    ]


def _build_prompt(
    items: list[dict[str, Any]],
    servings: int,
    exclude_items: list[str],
    prior_recipe: str | None,
) -> str:
    pantry = json.dumps(_pantry_lines(items), ensure_ascii=False)
    staples = ", ".join(ASSUMED_STAPLES)

    shape = (
        '{"title":"dish name","servings":2,"total_minutes":25,'
        '"uses_expiring":["pantry item names this dish consumes"],'
        '"ingredients":[{"name":"...","quantity":"200 g","from_pantry":true}],'
        '"steps":["..."],"missing":["anything required but not available"]}'
    )

    rules = [
        "Return valid JSON only, in exactly this shape: " + shape,
        f"Cook for {servings} serving(s).",
        (
            "Use ONLY ingredients from the pantry list below, plus these "
            f"assumed staples: {staples}. Anything else you need must go in "
            '"missing" and must NOT appear in "ingredients".'
        ),
        (
            "Prioritise the items with the lowest days_remaining. Every item "
            'you consume that has status "expiring_soon" must be listed in '
            '"uses_expiring", using its exact pantry name.'
        ),
        "Do not invent pantry items, quantities or dates.",
    ]

    if prior_recipe:
        rules.append(
            "You are revising the recipe below, not starting over. Keep the "
            "dish recognisably the same where possible and change only what "
            "the exclusions force."
        )
    if exclude_items:
        excluded = ", ".join(exclude_items)
        rules.append(
            f"These are unavailable and must not appear anywhere: {excluded}."
        )

    parts = [" ".join(rules), f"PANTRY: {pantry}"]
    if prior_recipe:
        parts.append(f"PREVIOUS RECIPE: {prior_recipe}")
    return "\n\n".join(parts)


def _call_bedrock(prompt: str) -> Recipe:
    settings = get_settings()
    client = bedrock.get_client()
    response = client.converse(
        modelId=settings.bedrock_model_id,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 2048, "temperature": 0},
    )
    return bedrock.parse_json_response(response, Recipe, "recipe")


async def generate_and_adapt_recipe(
    session: AsyncSession,
    user_id: int,
    servings: int = 2,
    exclude_items: list[str] | None = None,
    prior_recipe: str | None = None,
) -> dict[str, Any]:
    """Build a recipe around what expires soonest, or re-plan an existing one."""
    if servings < 1 or servings > 12:
        raise ValueError("servings must be between 1 and 12.")

    excluded = [name.strip() for name in (exclude_items or []) if name.strip()]
    excluded_folded = {name.casefold() for name in excluded}

    status = await get_inventory_status(session, user_id, include_consumed=False)
    available = [
        item
        for item in _cookable(status["items"])
        if item["display_name"].casefold() not in excluded_folded
    ]

    if not available:
        return {
            "success": False,
            "error": "No usable pantry items for this user.",
            "user_id": user_id,
        }

    prompt = _build_prompt(available, servings, excluded, prior_recipe)
    recipe = await asyncio.to_thread(_call_bedrock, prompt)

    expiring_soon = [
        item["display_name"]
        for item in available
        if item.get("status") == "expiring_soon"
    ]

    return {
        "success": True,
        "user_id": user_id,
        "adapted": prior_recipe is not None,
        "excluded_items": excluded,
        # What the pantry said was urgent, independent of what the model
        # chose. A client can compare the two and say so if they diverge.
        "expiring_soon_in_pantry": expiring_soon,
        "recipe": recipe.model_dump(),
    }

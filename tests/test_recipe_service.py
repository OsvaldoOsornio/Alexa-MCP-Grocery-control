"""Unit tests for `generate_and_adapt_recipe`.

Bedrock is replaced by a fake client that records the prompt it was given,
so these tests need no AWS credentials. What they mostly assert is what the
prompt contains, because that is what decides whether the agent prioritises
by expiry or just invents a dish.
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import recipe as recipe_service
from app.services.recipe import generate_and_adapt_recipe

RECIPE_JSON = {
    "title": "Spinach and tomato frittata",
    "servings": 2,
    "total_minutes": 25,
    "uses_expiring": ["Vine tomatoes", "Baby spinach"],
    "ingredients": [
        {"name": "Vine tomatoes", "quantity": "3", "from_pantry": True},
        {"name": "Free-range eggs", "quantity": "4", "from_pantry": True},
    ],
    "steps": ["Beat the eggs.", "Fold in the vegetables.", "Bake 15 minutes."],
    "missing": [],
}

INVENTORY = {
    "user_id": 7,
    "count": 4,
    "items": [
        {
            "id": 1,
            "display_name": "Vine tomatoes",
            "quantity": "6.00",
            "unit": "units",
            "days_remaining": 1,
            "status": "expiring_soon",
        },
        {
            "id": 2,
            "display_name": "Baby spinach",
            "quantity": "120.00",
            "unit": "grams",
            "days_remaining": 2,
            "status": "expiring_soon",
        },
        {
            "id": 3,
            "display_name": "Free-range eggs",
            "quantity": "10.00",
            "unit": "units",
            "days_remaining": 12,
            "status": "fresh",
        },
        {
            "id": 4,
            "display_name": "Old lettuce",
            "quantity": "1.00",
            "unit": "units",
            "days_remaining": -3,
            "status": "expired",
        },
    ],
}


class FakeBedrockClient:
    """Records the prompt and returns a fenced JSON payload, as Converse does."""

    def __init__(self, payload=None, fenced=True):
        self.payload = payload if payload is not None else RECIPE_JSON
        self.fenced = fenced
        self.prompt = None

    def converse(self, **kwargs):
        self.prompt = kwargs["messages"][0]["content"][0]["text"]
        body = json.dumps(self.payload)
        if self.fenced:
            body = "```json\n" + body + "\n```"
        return {"output": {"message": {"content": [{"text": body}]}}}


@pytest.fixture()
def fake_bedrock(monkeypatch):
    client = FakeBedrockClient()
    monkeypatch.setattr(recipe_service.bedrock, "get_client", lambda: client)
    return client


@pytest.fixture()
def inventory(monkeypatch):
    mock = AsyncMock(return_value=INVENTORY)
    monkeypatch.setattr(recipe_service, "get_inventory_status", mock)
    return mock


def _run(**kwargs):
    return asyncio.run(generate_and_adapt_recipe(SimpleNamespace(), 7, **kwargs))


def test_generates_a_recipe_and_reports_what_the_pantry_says_is_urgent(
    fake_bedrock, inventory
):
    result = _run()

    assert result["success"] is True
    assert result["adapted"] is False
    assert result["recipe"]["title"] == "Spinach and tomato frittata"
    # Derived from the inventory, not from the model's answer, so a client can
    # tell when the two disagree.
    assert result["expiring_soon_in_pantry"] == ["Vine tomatoes", "Baby spinach"]


def test_prompt_carries_the_soonest_expiring_item_first(fake_bedrock, inventory):
    _run()

    pantry = fake_bedrock.prompt.split("PANTRY: ", 1)[1].split("\n\n")[0]
    rows = json.loads(pantry)
    assert [row["name"] for row in rows][:2] == ["Vine tomatoes", "Baby spinach"]
    assert rows[0]["days_remaining"] == 1


def test_expired_items_are_never_offered_to_the_model(fake_bedrock, inventory):
    """The product exists to prevent waste, not to suggest eating spoiled food."""
    _run()

    assert "Old lettuce" not in fake_bedrock.prompt


def test_prompt_pins_the_model_to_pantry_items_plus_staples(fake_bedrock, inventory):
    _run()

    assert "Use ONLY ingredients from the pantry list" in fake_bedrock.prompt
    for staple in recipe_service.ASSUMED_STAPLES:
        assert staple in fake_bedrock.prompt
    assert "Do not invent pantry items" in fake_bedrock.prompt


def test_adapt_mode_excludes_the_named_item_and_flags_itself(fake_bedrock, inventory):
    result = _run(
        exclude_items=["Free-range eggs"],
        prior_recipe="Spinach and tomato frittata",
    )

    assert result["adapted"] is True
    assert result["excluded_items"] == ["Free-range eggs"]

    pantry = fake_bedrock.prompt.split("PANTRY: ", 1)[1].split("\n\n")[0]
    assert "Free-range eggs" not in pantry
    assert "must not appear anywhere: Free-range eggs" in fake_bedrock.prompt
    assert "PREVIOUS RECIPE: Spinach and tomato frittata" in fake_bedrock.prompt
    assert "revising the recipe below" in fake_bedrock.prompt


def test_exclusion_is_case_insensitive(fake_bedrock, inventory):
    result = _run(exclude_items=["  free-range EGGS  "])

    pantry = fake_bedrock.prompt.split("PANTRY: ", 1)[1].split("\n\n")[0]
    assert "Free-range eggs" not in pantry
    assert result["excluded_items"] == ["free-range EGGS"]


def test_servings_reaches_the_prompt(fake_bedrock, inventory):
    _run(servings=6)

    assert "Cook for 6 serving(s)." in fake_bedrock.prompt


def test_unfenced_json_is_accepted_too(monkeypatch, inventory):
    client = FakeBedrockClient(fenced=False)
    monkeypatch.setattr(recipe_service.bedrock, "get_client", lambda: client)

    assert _run()["recipe"]["title"] == "Spinach and tomato frittata"


def test_invalid_model_output_is_rejected_rather_than_passed_through(
    monkeypatch, inventory
):
    client = FakeBedrockClient(payload={"title": "No steps, no servings"})
    monkeypatch.setattr(recipe_service.bedrock, "get_client", lambda: client)

    with pytest.raises(ValueError, match="invalid recipe JSON"):
        _run()


def test_extra_fields_from_the_model_are_rejected(monkeypatch, inventory):
    payload = dict(RECIPE_JSON, wine_pairing="Chardonnay")
    client = FakeBedrockClient(payload=payload)
    monkeypatch.setattr(recipe_service.bedrock, "get_client", lambda: client)

    with pytest.raises(ValueError, match="invalid recipe JSON"):
        _run()


def test_empty_pantry_returns_a_failure_without_calling_bedrock(monkeypatch):
    monkeypatch.setattr(
        recipe_service,
        "get_inventory_status",
        AsyncMock(return_value={"user_id": 7, "count": 0, "items": []}),
    )

    def explode():
        raise AssertionError("Bedrock must not be called with an empty pantry")

    monkeypatch.setattr(recipe_service.bedrock, "get_client", explode)

    result = _run()
    assert result["success"] is False
    assert "No usable pantry items" in result["error"]


def test_servings_out_of_range_is_rejected_before_reading_the_pantry(monkeypatch):
    mock = AsyncMock(return_value=INVENTORY)
    monkeypatch.setattr(recipe_service, "get_inventory_status", mock)

    with pytest.raises(ValueError, match="servings must be between 1 and 12"):
        _run(servings=0)

    mock.assert_not_awaited()

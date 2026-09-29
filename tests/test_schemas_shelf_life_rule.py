"""Tests de los esquemas Pydantic v2 de `shelf_life_rules`."""
from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas import ShelfLifeRuleCreate, ShelfLifeRuleRead, ShelfLifeRuleUpdate


def _valid_payload(**overrides) -> dict:
    payload = dict(
        ingredient_name="Leche entera",
        category="dairy",
        default_storage="refrigerator",
        shelf_life_days_unopened=10,
        open_shelf_life_multiplier=Decimal("0.70"),
        frozen_shelf_life_days=90,
    )
    payload.update(overrides)
    return payload


def test_create_schema_accepts_valid_payload():
    rule = ShelfLifeRuleCreate(**_valid_payload())
    assert rule.ingredient_name == "Leche entera"
    assert rule.open_shelf_life_multiplier == Decimal("0.70")
    assert rule.requires_refrigeration_after_opening is False  # default


def test_create_schema_applies_multiplier_default():
    # `open_shelf_life_multiplier` no se pasa -> debe usar el default 1.00
    payload = _valid_payload()
    payload.pop("open_shelf_life_multiplier")
    rule = ShelfLifeRuleCreate(**payload)
    assert rule.open_shelf_life_multiplier == Decimal("1.00")


@pytest.mark.parametrize("bad_days", [0, -5])
def test_shelf_life_days_unopened_must_be_positive(bad_days):
    with pytest.raises(ValidationError):
        ShelfLifeRuleCreate(**_valid_payload(shelf_life_days_unopened=bad_days))


@pytest.mark.parametrize("bad_multiplier", [Decimal("0"), Decimal("-0.1"), Decimal("1.01")])
def test_open_shelf_life_multiplier_must_be_in_range(bad_multiplier):
    with pytest.raises(ValidationError):
        ShelfLifeRuleCreate(**_valid_payload(open_shelf_life_multiplier=bad_multiplier))


def test_unknown_category_is_rejected():
    with pytest.raises(ValidationError):
        ShelfLifeRuleCreate(**_valid_payload(category="not_a_real_category"))


def test_unknown_storage_location_is_rejected():
    with pytest.raises(ValidationError):
        ShelfLifeRuleCreate(**_valid_payload(default_storage="cupboard_of_wonders"))


def test_update_schema_allows_partial_payload():
    update = ShelfLifeRuleUpdate(notes="Se degrada más rápido en verano")
    assert update.notes == "Se degrada más rápido en verano"
    assert update.category is None
    assert update.shelf_life_days_unopened is None


@pytest.mark.parametrize(
    "unopened_days, multiplier, expected",
    [
        (10, Decimal("0.70"), 7),   # round(7.0) == 7
        (14, Decimal("0.50"), 7),
        (1, Decimal("0.10"), 1),     # el mínimo garantizado es 1 día
        (365, Decimal("1.00"), 365),
    ],
)
def test_estimated_opened_shelf_life_days_computed_field(unopened_days, multiplier, expected):
    rule = ShelfLifeRuleRead(
        id=1,
        **_valid_payload(
            shelf_life_days_unopened=unopened_days,
            open_shelf_life_multiplier=multiplier,
            frozen_shelf_life_days=None,
        ),
    )
    assert rule.estimated_opened_shelf_life_days == expected


def test_read_schema_builds_from_orm_like_object():
    class _FakeOrmRule:
        id = 42
        ingredient_name = "Mantequilla"
        category = "dairy"
        default_storage = "refrigerator"
        shelf_life_days_unopened = 60
        open_shelf_life_multiplier = Decimal("0.50")
        frozen_shelf_life_days = 180
        requires_refrigeration_after_opening = False
        notes = None

    read = ShelfLifeRuleRead.model_validate(_FakeOrmRule())
    assert read.id == 42
    assert read.ingredient_name == "Mantequilla"
    assert read.estimated_opened_shelf_life_days == 30

"""Tests del modelo ORM `ShelfLifeRule` (catálogo maestro de caducidad)."""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import ShelfLifeRule


def test_create_rule_with_defaults(session):
    rule = ShelfLifeRule(
        ingredient_name="Arroz blanco",
        category="pantry_staple",
        default_storage="pantry",
        shelf_life_days_unopened=730,
    )
    session.add(rule)
    session.commit()
    session.refresh(rule)

    assert rule.id is not None
    # Defaults definidos en server_default deben aplicarse tras el refresh.
    assert rule.open_shelf_life_multiplier == Decimal("1.00")
    assert rule.requires_refrigeration_after_opening is False
    assert rule.frozen_shelf_life_days is None
    assert rule.created_at is not None
    assert rule.updated_at is not None


def test_ingredient_name_is_unique(session, milk_rule):
    duplicate = ShelfLifeRule(
        ingredient_name=milk_rule.ingredient_name,
        category="dairy",
        default_storage="refrigerator",
        shelf_life_days_unopened=5,
    )
    session.add(duplicate)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


@pytest.mark.parametrize("invalid_days", [0, -1])
def test_shelf_life_days_unopened_must_be_positive(session, invalid_days):
    rule = ShelfLifeRule(
        ingredient_name="Ingrediente inválido",
        category="other",
        default_storage="pantry",
        shelf_life_days_unopened=invalid_days,
    )
    session.add(rule)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


@pytest.mark.parametrize("invalid_multiplier", ["0.00", "-0.10", "1.01", "2.00"])
def test_open_shelf_life_multiplier_must_be_in_range(session, invalid_multiplier):
    rule = ShelfLifeRule(
        ingredient_name="Ingrediente multiplicador inválido",
        category="other",
        default_storage="pantry",
        shelf_life_days_unopened=10,
        open_shelf_life_multiplier=invalid_multiplier,
    )
    session.add(rule)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_frozen_shelf_life_days_must_be_positive_when_set(session):
    rule = ShelfLifeRule(
        ingredient_name="Ingrediente congelado inválido",
        category="other",
        default_storage="pantry",
        shelf_life_days_unopened=10,
        frozen_shelf_life_days=0,
    )
    session.add(rule)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_frozen_shelf_life_days_accepts_null(session):
    rule = ShelfLifeRule(
        ingredient_name="Huevos",
        category="dairy",
        default_storage="refrigerator",
        shelf_life_days_unopened=30,
        frozen_shelf_life_days=None,
    )
    session.add(rule)
    session.commit()
    assert rule.frozen_shelf_life_days is None


def test_pantry_items_relationship_starts_empty(milk_rule):
    assert milk_rule.pantry_items == []


def test_repr_contains_ingredient_name(milk_rule):
    assert "Leche entera" in repr(milk_rule)

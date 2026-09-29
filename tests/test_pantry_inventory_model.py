"""Tests del modelo ORM `PantryInventory` (stock del usuario).

Nota: `expiration_date` es calculada por un trigger de Postgres
(`calculate_pantry_expiration`, ver database/schema.sql) que no existe en el
SQLite de estos tests, así que aquí no se afirma nada sobre su valor
calculado — eso se cubre en tests/test_integration_postgres.py contra un
Postgres real. Aquí se valida todo lo que sí depende únicamente del modelo:
defaults, constraints y relaciones.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import PantryInventory


def _make_item(**overrides):
    # `purchase_date` se fija explícitamente en Python (igual que hace
    # `PantryInventoryCreate` vía Pydantic en la capa de API) en lugar de
    # depender del `server_default=CURRENT_DATE` de la columna: ese default
    # es un respaldo para inserts SQL directos, pero comparar una fecha
    # calculada por el motor de la base de datos (UTC) contra una fecha
    # calculada en Python (huso horario local) es una carrera cerca de la
    # medianoche UTC y no algo que un test deba depender.
    defaults = dict(
        display_name="Leche Alqueria",
        storage_location="refrigerator",
        purchase_date=date.today(),
    )
    defaults.update(overrides)
    return PantryInventory(**defaults)


def test_create_item_with_defaults(session, user_id, milk_rule):
    item = _make_item(user_id=user_id, shelf_life_rule_id=milk_rule.id)
    session.add(item)
    session.commit()
    session.refresh(item)

    assert item.id is not None
    assert item.quantity == Decimal("1")
    assert item.unit == "unidad"
    assert item.is_opened is False
    assert item.is_consumed is False
    assert item.consumed_at is None
    assert item.purchase_date == date.today()


def test_purchase_date_has_a_database_level_fallback_default(session, user_id, milk_rule):
    """Si el caller no lo especifica, la columna debe autocompletarse igual
    (respaldo `server_default=CURRENT_DATE`, ver app/models/pantry_inventory.py).
    No se compara contra `date.today()` de Python: `CURRENT_DATE` en SQLite/
    Postgres se evalúa en UTC y puede diferir en un día del reloj local justo
    alrededor de la medianoche UTC; solo se verifica que quede poblada.
    """
    item = PantryInventory(
        user_id=user_id,
        shelf_life_rule_id=milk_rule.id,
        display_name="Leche Alqueria",
        storage_location="refrigerator",
    )
    session.add(item)
    session.commit()
    session.refresh(item)

    assert item.purchase_date is not None
    assert isinstance(item.purchase_date, date)


def test_shelf_life_rule_relationship(session, user_id, milk_rule):
    item = _make_item(user_id=user_id, shelf_life_rule_id=milk_rule.id)
    session.add(item)
    session.commit()
    session.refresh(item)

    assert item.shelf_life_rule is not None
    assert item.shelf_life_rule.ingredient_name == "Leche entera"
    assert item in milk_rule.pantry_items


def test_item_without_catalog_rule_is_allowed(session, user_id):
    """Un ítem "libre" (no catalogado) debe poder crearse sin `shelf_life_rule_id`."""
    item = _make_item(user_id=user_id, shelf_life_rule_id=None)
    session.add(item)
    session.commit()
    assert item.shelf_life_rule is None


def test_quantity_cannot_be_negative(session, user_id, milk_rule):
    item = _make_item(user_id=user_id, shelf_life_rule_id=milk_rule.id, quantity=Decimal("-1"))
    session.add(item)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_opened_date_cannot_precede_purchase_date(session, user_id, milk_rule):
    today = date.today()
    item = _make_item(
        user_id=user_id,
        shelf_life_rule_id=milk_rule.id,
        purchase_date=today,
        is_opened=True,
        opened_date=today - timedelta(days=1),
    )
    session.add(item)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_is_opened_requires_opened_date(session, user_id, milk_rule):
    item = _make_item(
        user_id=user_id,
        shelf_life_rule_id=milk_rule.id,
        is_opened=True,
        opened_date=None,
    )
    session.add(item)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_is_opened_with_opened_date_is_valid(session, user_id, milk_rule):
    item = _make_item(
        user_id=user_id,
        shelf_life_rule_id=milk_rule.id,
        is_opened=True,
        opened_date=date.today(),
    )
    session.add(item)
    session.commit()
    assert item.is_opened is True


def test_consumed_at_requires_is_consumed_true(session, user_id, milk_rule):
    item = _make_item(
        user_id=user_id,
        shelf_life_rule_id=milk_rule.id,
        is_consumed=False,
        consumed_at=date.today(),  # cualquier valor no nulo debe fallar
    )
    session.add(item)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_deleting_shelf_life_rule_sets_fk_null(session, user_id, milk_rule):
    """`ON DELETE SET NULL`: borrar la regla de catálogo no debe borrar el stock."""
    item = _make_item(user_id=user_id, shelf_life_rule_id=milk_rule.id)
    session.add(item)
    session.commit()
    item_id = item.id

    session.delete(milk_rule)
    session.commit()

    refreshed = session.get(PantryInventory, item_id)
    assert refreshed is not None
    assert refreshed.shelf_life_rule_id is None


def test_repr_contains_display_name(session, user_id, milk_rule):
    item = _make_item(user_id=user_id, shelf_life_rule_id=milk_rule.id)
    session.add(item)
    session.commit()
    assert "Leche Alqueria" in repr(item)

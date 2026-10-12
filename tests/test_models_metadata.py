"""Structural tests of the models via metadata introspection.

They need no database connection: they check that the columns, types,
foreign keys and constraints declared in the SQLAlchemy models match what is
documented in database/schema.sql. They act as a "contract" that catches
someone changing one without updating the other.
"""
from __future__ import annotations

from app.models import PantryInventory, ShelfLifeRule


def _column_names(model) -> set[str]:
    return {c.name for c in model.__table__.columns}


def test_shelf_life_rules_table_name():
    assert ShelfLifeRule.__tablename__ == "shelf_life_rules"


def test_shelf_life_rules_expected_columns():
    expected = {
        "id",
        "ingredient_name",
        "category",
        "default_storage",
        "shelf_life_days_unopened",
        "open_shelf_life_multiplier",
        "frozen_shelf_life_days",
        "requires_refrigeration_after_opening",
        "notes",
        "created_at",
        "updated_at",
    }
    assert expected <= _column_names(ShelfLifeRule)


def test_shelf_life_rules_ingredient_name_is_unique():
    col = ShelfLifeRule.__table__.c.ingredient_name
    assert col.unique or any(
        set(uc.columns) == {col} for uc in ShelfLifeRule.__table__.constraints
        if uc.__class__.__name__ == "UniqueConstraint"
    )


def test_pantry_inventory_table_name():
    assert PantryInventory.__tablename__ == "pantry_inventory"


def test_pantry_inventory_expected_columns():
    expected = {
        "id",
        "user_id",
        "shelf_life_rule_id",
        "display_name",
        "quantity",
        "unit",
        "storage_location",
        "is_opened",
        "purchase_date",
        "opened_date",
        "custom_expiration_date",
        "expiration_date",
        "is_consumed",
        "consumed_at",
        "notes",
        "created_at",
        "updated_at",
    }
    assert expected <= _column_names(PantryInventory)


def test_pantry_inventory_foreign_keys_target_expected_tables():
    fks = {fk.target_fullname for fk in PantryInventory.__table__.foreign_keys}
    assert "users.id" in fks
    assert "shelf_life_rules.id" in fks


def test_pantry_inventory_user_id_cascades_on_delete():
    fk = next(
        fk for fk in PantryInventory.__table__.foreign_keys
        if fk.target_fullname == "users.id"
    )
    assert fk.ondelete == "CASCADE"


def test_pantry_inventory_shelf_life_rule_id_sets_null_on_delete():
    fk = next(
        fk for fk in PantryInventory.__table__.foreign_keys
        if fk.target_fullname == "shelf_life_rules.id"
    )
    assert fk.ondelete == "SET NULL"


def test_no_column_is_left_as_undetermined_type():
    """Regression: `user_id` once resolved to NullType() because it depended on
    `users` being registered in the same MetaData (see the history of
    app/models/pantry_inventory.py). This test stops that going unnoticed
    again for any column of either model.
    """
    from sqlalchemy.sql.sqltypes import NullType

    for model in (ShelfLifeRule, PantryInventory):
        for column in model.__table__.columns:
            assert not isinstance(column.type, NullType), (
                f"{model.__tablename__}.{column.name} has no explicit type "
                "resolvable without another model being imported."
            )

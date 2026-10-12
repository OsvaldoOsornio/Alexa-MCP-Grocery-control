"""Enums shared between the SQLAlchemy models and the Pydantic schemas.

The values (lower case) must match exactly the ones defined in the
PostgreSQL ENUM types created in database/schema.sql
(`ingredient_category` and `storage_location`).
"""
from __future__ import annotations

import enum


class IngredientCategory(str, enum.Enum):
    PRODUCE = "produce"
    DAIRY = "dairy"
    MEAT_POULTRY = "meat_poultry"
    SEAFOOD = "seafood"
    BAKERY = "bakery"
    PANTRY_STAPLE = "pantry_staple"
    CONDIMENT_SAUCE = "condiment_sauce"
    BEVERAGE = "beverage"
    FROZEN = "frozen"
    OTHER = "other"


class StorageLocation(str, enum.Enum):
    PANTRY = "pantry"
    REFRIGERATOR = "refrigerator"
    FREEZER = "freezer"

"""Enums compartidos entre los modelos SQLAlchemy y los esquemas Pydantic.

Los valores (en minúsculas) deben coincidir exactamente con los definidos en
los tipos ENUM de PostgreSQL creados en database/schema.sql
(`ingredient_category` y `storage_location`).
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

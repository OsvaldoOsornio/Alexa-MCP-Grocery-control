"""Pydantic v2 schemas for `shelf_life_rules`."""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.models.enums import IngredientCategory, StorageLocation


class ShelfLifeRuleBase(BaseModel):
    ingredient_name: str = Field(..., max_length=100, examples=["Whole milk"])
    category: IngredientCategory
    default_storage: StorageLocation
    shelf_life_days_unopened: int = Field(
        ..., gt=0, le=3650, description="Shelf life in days while unopened, counted from purchase."
    )
    open_shelf_life_multiplier: Decimal = Field(
        Decimal("1.00"),
        gt=0,
        le=1,
        description="Multiplicador sobre `shelf_life_days_unopened` una vez abierto.",
    )
    frozen_shelf_life_days: Optional[int] = Field(
        None, gt=0, le=3650, description="Shelf life in days if frozen."
    )
    requires_refrigeration_after_opening: bool = False
    notes: Optional[str] = None


class ShelfLifeRuleCreate(ShelfLifeRuleBase):
    pass


class ShelfLifeRuleUpdate(BaseModel):
    """All fields optional: for a partial PATCH."""

    category: Optional[IngredientCategory] = None
    default_storage: Optional[StorageLocation] = None
    shelf_life_days_unopened: Optional[int] = Field(None, gt=0, le=3650)
    open_shelf_life_multiplier: Optional[Decimal] = Field(None, gt=0, le=1)
    frozen_shelf_life_days: Optional[int] = Field(None, gt=0, le=3650)
    requires_refrigeration_after_opening: Optional[bool] = None
    notes: Optional[str] = None


class ShelfLifeRuleRead(ShelfLifeRuleBase):
    model_config = ConfigDict(from_attributes=True)

    id: int

    @computed_field  # type: ignore[misc]
    @property
    def estimated_opened_shelf_life_days(self) -> int:
        """Preview of what the Postgres trigger will compute when the item is opened.

        A Python mirror of the `calculate_pantry_expiration()` logic in
        database/schema.sql, useful for showing in the UI before inserting.
        """
        return max(1, round(self.shelf_life_days_unopened * float(self.open_shelf_life_multiplier)))

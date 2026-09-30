"""Esquemas Pydantic v2 para `shelf_life_rules`."""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.models.enums import IngredientCategory, StorageLocation


class ShelfLifeRuleBase(BaseModel):
    ingredient_name: str = Field(..., max_length=100, examples=["Leche entera"])
    category: IngredientCategory
    default_storage: StorageLocation
    shelf_life_days_unopened: int = Field(
        ..., gt=0, le=3650, description="Días de vida útil sin abrir, desde la compra."
    )
    open_shelf_life_multiplier: Decimal = Field(
        Decimal("1.00"),
        gt=0,
        le=1,
        description="Multiplicador sobre `shelf_life_days_unopened` una vez abierto.",
    )
    frozen_shelf_life_days: Optional[int] = Field(
        None, gt=0, le=3650, description="Días de vida útil si se congela."
    )
    requires_refrigeration_after_opening: bool = False
    notes: Optional[str] = None


class ShelfLifeRuleCreate(ShelfLifeRuleBase):
    pass


class ShelfLifeRuleUpdate(BaseModel):
    """Todos los campos opcionales: para PATCH parcial."""

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
        """Vista previa de lo que calculará el trigger de Postgres al abrir el ítem.

        Espejo en Python de la lógica de `calculate_pantry_expiration()` en
        database/schema.sql, útil para mostrarlo en UI antes de insertar.
        """
        return max(1, round(self.shelf_life_days_unopened * float(self.open_shelf_life_multiplier)))

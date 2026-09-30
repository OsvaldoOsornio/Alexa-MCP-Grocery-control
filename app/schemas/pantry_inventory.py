"""Esquemas Pydantic v2 para `pantry_inventory`."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import StorageLocation

from .shelf_life_rule import ShelfLifeRuleRead


class PantryInventoryBase(BaseModel):
    shelf_life_rule_id: Optional[int] = Field(
        None, description="Referencia al catálogo shelf_life_rules; NULL si es un ítem libre."
    )
    display_name: str = Field(..., max_length=150, examples=["Leche entera Alqueria"])
    quantity: Decimal = Field(Decimal("1"), ge=0)
    unit: str = Field("unidad", max_length=20)
    storage_location: StorageLocation = StorageLocation.PANTRY
    is_opened: bool = False
    purchase_date: date = Field(default_factory=date.today)
    opened_date: Optional[date] = None
    custom_expiration_date: Optional[date] = Field(
        None, description="Fecha manual (ej. impresa en el empaque); siempre prevalece."
    )
    notes: Optional[str] = None

    @model_validator(mode="after")
    def _validate_opened_state(self) -> "PantryInventoryBase":
        if self.is_opened and self.opened_date is None:
            raise ValueError("opened_date es obligatorio cuando is_opened=True")
        if self.opened_date is not None and self.opened_date < self.purchase_date:
            raise ValueError("opened_date no puede ser anterior a purchase_date")
        return self


class PantryInventoryCreate(PantryInventoryBase):
    pass


class PantryInventoryUpdate(BaseModel):
    """Todos los campos opcionales: para PATCH parcial (ej. marcar como abierto/consumido)."""

    shelf_life_rule_id: Optional[int] = None
    display_name: Optional[str] = Field(None, max_length=150)
    quantity: Optional[Decimal] = Field(None, ge=0)
    unit: Optional[str] = Field(None, max_length=20)
    storage_location: Optional[StorageLocation] = None
    is_opened: Optional[bool] = None
    opened_date: Optional[date] = None
    custom_expiration_date: Optional[date] = None
    is_consumed: Optional[bool] = None
    notes: Optional[str] = None


class PantryInventoryRead(PantryInventoryBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int

    # Calculada en la base de datos por el trigger `calculate_pantry_expiration`.
    expiration_date: Optional[date] = None

    is_consumed: bool
    consumed_at: Optional[datetime] = None

    created_at: datetime
    updated_at: datetime

    shelf_life_rule: Optional[ShelfLifeRuleRead] = None

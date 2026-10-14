"""Pydantic v2 schemas for `pantry_inventory`."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import StorageLocation

from .shelf_life_rule import ShelfLifeRuleRead


class PantryInventoryBase(BaseModel):
    shelf_life_rule_id: Optional[int] = Field(
        None, description="Reference to the shelf_life_rules catalog; NULL for a free item."
    )
    display_name: str = Field(..., max_length=150, examples=["Alqueria whole milk"])
    quantity: Decimal = Field(Decimal("1"), ge=0)
    unit: str = Field("unit", max_length=20)
    storage_location: StorageLocation = StorageLocation.PANTRY
    is_opened: bool = False
    purchase_date: date = Field(default_factory=date.today)
    opened_date: Optional[date] = None
    custom_expiration_date: Optional[date] = Field(
        None,
        description=(
            "Manual date, for example the one printed on the pack; it always "
            "takes priority over the calculated expiry."
        ),
    )
    notes: Optional[str] = None

    @model_validator(mode="after")
    def _validate_opened_state(self) -> "PantryInventoryBase":
        if self.is_opened and self.opened_date is None:
            raise ValueError("opened_date is required when is_opened=True.")
        if self.opened_date is not None and self.opened_date < self.purchase_date:
            raise ValueError("opened_date cannot be earlier than purchase_date.")
        return self


class PantryInventoryCreate(PantryInventoryBase):
    pass


class PantryInventoryUpdate(BaseModel):
    """All fields optional: for a partial PATCH (e.g. mark opened/consumed)."""

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

    # Calculated in the database by the `calculate_pantry_expiration` trigger.
    expiration_date: Optional[date] = None

    is_consumed: bool
    consumed_at: Optional[datetime] = None

    created_at: datetime
    updated_at: datetime

    shelf_life_rule: Optional[ShelfLifeRuleRead] = None

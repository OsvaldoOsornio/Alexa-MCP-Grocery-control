"""Pydantic v2 schemas (API I/O) for the zero-waste kitchen inventory."""
from .pantry_inventory import (
    PantryInventoryBase,
    PantryInventoryCreate,
    PantryInventoryRead,
    PantryInventoryUpdate,
)
from .shelf_life_rule import (
    ShelfLifeRuleBase,
    ShelfLifeRuleCreate,
    ShelfLifeRuleRead,
    ShelfLifeRuleUpdate,
)

__all__ = [
    "ShelfLifeRuleBase",
    "ShelfLifeRuleCreate",
    "ShelfLifeRuleUpdate",
    "ShelfLifeRuleRead",
    "PantryInventoryBase",
    "PantryInventoryCreate",
    "PantryInventoryUpdate",
    "PantryInventoryRead",
]

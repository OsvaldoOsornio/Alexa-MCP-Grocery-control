"""ORM models (SQLAlchemy 2.0) for the zero-waste kitchen inventory."""
from .base import Base, TimestampMixin
from .enums import IngredientCategory, RipenessModifier, StorageLocation
from .pantry_inventory import PantryInventory
from .shelf_life_rule import ShelfLifeRule

# Imported for its side effect: registering `users` in Base.metadata so the
# pantry_inventory.user_id foreign key can resolve. See app/models/user.py.
from .user import users_table

__all__ = [
    "Base",
    "TimestampMixin",
    "IngredientCategory",
    "RipenessModifier",
    "StorageLocation",
    "ShelfLifeRule",
    "PantryInventory",
    "users_table",
]

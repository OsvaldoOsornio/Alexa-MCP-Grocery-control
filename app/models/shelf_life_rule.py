"""ORM model for the master catalog `shelf_life_rules`."""
from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Enum,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin
from .enums import IngredientCategory, StorageLocation

if TYPE_CHECKING:
    from .pantry_inventory import PantryInventory


class ShelfLifeRule(Base, TimestampMixin):
    """Master catalog: default shelf life in days per ingredient.

    `create_type=False` on the ENUMs because database/schema.sql already
    creates the `ingredient_category` / `storage_location` types in
    Postgres; this model assumes the DDL was applied separately (migration
    or psql), not via `Base.metadata.create_all`.
    """

    __tablename__ = "shelf_life_rules"
    __table_args__ = (
        CheckConstraint(
            "shelf_life_days_unopened > 0",
            name="ck_shelf_life_rules_unopened_positive",
        ),
        CheckConstraint(
            "open_shelf_life_multiplier > 0 AND open_shelf_life_multiplier <= 1",
            name="ck_shelf_life_rules_multiplier_range",
        ),
        CheckConstraint(
            "frozen_shelf_life_days IS NULL OR frozen_shelf_life_days > 0",
            name="ck_shelf_life_rules_frozen_positive",
        ),
    )

    # `with_variant(Integer, "sqlite")`: on Postgres this compiles to BIGINT
    # (the same as `BIGINT GENERATED ALWAYS AS IDENTITY` in schema.sql); on
    # SQLite (used in the tests) it compiles to INTEGER, the only type SQLite
    # autoincrements as a rowid alias.
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True
    )

    ingredient_name: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    category: Mapped[IngredientCategory] = mapped_column(
        Enum(
            IngredientCategory,
            name="ingredient_category",
            create_type=False,
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    default_storage: Mapped[StorageLocation] = mapped_column(
        Enum(
            StorageLocation,
            name="storage_location",
            create_type=False,
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )

    # Shelf life in days while unopened, in `default_storage`.
    shelf_life_days_unopened: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    # Multiplier applied to `shelf_life_days_unopened` once opened
    # (e.g. 0.50 = half the days, counted from the opened date).
    open_shelf_life_multiplier: Mapped[Decimal] = mapped_column(
        Numeric(3, 2), nullable=False, server_default="1.00"
    )

    # Shelf life in days if frozen; NULL when not advisable/applicable.
    frozen_shelf_life_days: Mapped[Optional[int]] = mapped_column(
        SmallInteger, nullable=True
    )

    requires_refrigeration_after_opening: Mapped[bool] = mapped_column(
        nullable=False, server_default=false()
    )

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    pantry_items: Mapped[List["PantryInventory"]] = relationship(
        back_populates="shelf_life_rule"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ShelfLifeRule id={self.id} ingredient_name={self.ingredient_name!r}>"

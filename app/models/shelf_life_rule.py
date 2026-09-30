"""Modelo ORM para el catálogo maestro `shelf_life_rules`."""
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
    """Catálogo maestro: días de caducidad por defecto por ingrediente.

    `create_type=False` en los ENUM porque database/schema.sql ya crea los
    tipos `ingredient_category` / `storage_location` en Postgres; este
    modelo asume que la DDL fue aplicada por separado (migración/psql), no
    vía `Base.metadata.create_all`.
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

    # `with_variant(Integer, "sqlite")`: en Postgres compila a BIGINT (igual
    # que `BIGINT GENERATED ALWAYS AS IDENTITY` en schema.sql); en SQLite
    # (usado en tests) compila a INTEGER, el único tipo que SQLite
    # autoincrementa como alias de rowid.
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

    # Días de vida útil sin abrir, en `default_storage`.
    shelf_life_days_unopened: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    # Multiplicador aplicado a `shelf_life_days_unopened` una vez abierto
    # (ej. 0.50 = la mitad de días desde la fecha de apertura).
    open_shelf_life_multiplier: Mapped[Decimal] = mapped_column(
        Numeric(3, 2), nullable=False, server_default="1.00"
    )

    # Días de vida útil si se congela; NULL si no es recomendable/aplicable.
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

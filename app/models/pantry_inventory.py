"""Modelo ORM para el stock del usuario `pantry_inventory`."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    FetchedValue,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    false,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin
from .enums import StorageLocation

if TYPE_CHECKING:
    from .shelf_life_rule import ShelfLifeRule


class PantryInventory(Base, TimestampMixin):
    """Stock actual de despensa/refrigerador/congelador por usuario.

    `expiration_date` NO se calcula en Python: lo recalcula el trigger de
    Postgres `calculate_pantry_expiration` en cada INSERT/UPDATE (ver
    database/schema.sql), a partir de `shelf_life_rule`, `is_opened`,
    `purchase_date`/`opened_date` y `storage_location`. Se marca con
    `FetchedValue()` para que SQLAlchemy sepa que debe refrescar la columna
    desde el servidor tras cada flush (vía RETURNING) en lugar de asumir
    el valor que tenía en memoria.
    """

    __tablename__ = "pantry_inventory"
    __table_args__ = (
        CheckConstraint("quantity >= 0", name="ck_pantry_inventory_quantity_non_negative"),
        CheckConstraint(
            "opened_date IS NULL OR opened_date >= purchase_date",
            name="ck_pantry_inventory_opened_after_purchase",
        ),
        CheckConstraint(
            "is_opened = FALSE OR opened_date IS NOT NULL",
            name="ck_pantry_inventory_opened_requires_date",
        ),
        CheckConstraint(
            "consumed_at IS NULL OR is_consumed = TRUE",
            name="ck_pantry_inventory_consumed_consistency",
        ),
        Index("ix_pantry_inventory_user_id", "user_id"),
        Index(
            "ix_pantry_inventory_user_expiration_active",
            "user_id",
            "expiration_date",
            postgresql_where=("is_consumed = FALSE"),
        ),
    )

    # `with_variant(Integer, "sqlite")`: ver nota equivalente en ShelfLifeRule.id.
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True
    )

    # BigInteger explícito (no inferido del FK): `users` no es un modelo ORM
    # de esta app (ver nota de la clase), así que si `users` no está
    # registrada en este `MetaData` el tipo quedaría en NullType y la DDL
    # fallaría al compilar. Ajusta el tipo (p. ej. UUID) si tu tabla `users`
    # real usa otra PK.
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    shelf_life_rule_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("shelf_life_rules.id", ondelete="SET NULL"), nullable=True
    )

    display_name: Mapped[str] = mapped_column(String(150), nullable=False)

    quantity: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, server_default="1"
    )
    unit: Mapped[str] = mapped_column(String(20), nullable=False, server_default="unidad")

    storage_location: Mapped[StorageLocation] = mapped_column(
        Enum(
            StorageLocation,
            name="storage_location",
            create_type=False,
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        server_default=StorageLocation.PANTRY.value,
    )

    is_opened: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())
    purchase_date: Mapped[date] = mapped_column(
        Date, nullable=False, server_default=func.current_date()
    )
    opened_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Fijada manualmente por el usuario; siempre gana sobre el cálculo automático.
    custom_expiration_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Calculada por trigger — no escribir directamente desde la app.
    expiration_date: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True,
        server_default=FetchedValue(),
        server_onupdate=FetchedValue(),
    )

    is_consumed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())
    consumed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    shelf_life_rule: Mapped[Optional["ShelfLifeRule"]] = relationship(
        back_populates="pantry_items"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<PantryInventory id={self.id} display_name={self.display_name!r} "
            f"expires={self.expiration_date}>"
        )

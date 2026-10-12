"""ORM model for the user stock table `pantry_inventory`."""
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
    """Current pantry/refrigerator/freezer stock per user.

    `expiration_date` is NOT calculated in Python: the Postgres trigger
    `calculate_pantry_expiration` recomputes it on every INSERT/UPDATE (see
    database/schema.sql) from `shelf_life_rule`, `is_opened`,
    `purchase_date`/`opened_date` and `storage_location`. It is marked with
    `FetchedValue()` so SQLAlchemy knows to refresh the column from the
    server after each flush (via RETURNING) instead of trusting the value
    it held in memory.
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

    # `with_variant(Integer, "sqlite")`: see the equivalent note on ShelfLifeRule.id.
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True
    )

    # Explicit BigInteger (not inferred from the FK): `users` is not an ORM
    # model of this app (see the class note), so if `users` is not registered
    # in this `MetaData` the type would fall back to NullType and the DDL
    # would fail to compile. Change the type (e.g. UUID) if your real `users`
    # table uses a different primary key.
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
    unit: Mapped[str] = mapped_column(String(20), nullable=False, server_default="unit")

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

    # Set manually by the user; always wins over the automatic calculation.
    custom_expiration_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Calculated by the trigger - do not write it directly from the app.
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

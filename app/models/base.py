"""Declarative base and mixins shared by every ORM model."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """SQLAlchemy 2.0 declarative base for the whole app."""


class TimestampMixin:
    """Adds `created_at` / `updated_at`.

    `updated_at` is also maintained by a Postgres trigger (`set_updated_at`,
    see database/schema.sql) so it stays correct even when the row is
    modified outside the ORM (direct SQL, another app, a maintenance job,
    and so on). The `onupdate` here is only a convenience for purely
    in-memory sessions before the flush.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

"""Base declarativa y mixins compartidos por todos los modelos ORM."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base declarativa de SQLAlchemy 2.0 para toda la app."""


class TimestampMixin:
    """Agrega `created_at` / `updated_at`.

    `updated_at` también se mantiene vía trigger de Postgres
    (`set_updated_at`, ver database/schema.sql) para que quede correcto
    incluso si la fila se modifica fuera del ORM (SQL directo, otra app,
    un job de mantenimiento, etc.). El `onupdate` aquí es solo una
    conveniencia para sesiones puramente en memoria antes del flush.
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

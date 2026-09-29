"""Fixtures compartidas para la suite de tests de los modelos (Fase 1).

Los tests corren contra SQLite en memoria por velocidad y portabilidad (no
requieren un Postgres real). Esto cubre estructura, defaults, constraints y
relaciones de los modelos SQLAlchemy. Lo que SQLite NO puede validar son los
triggers de Postgres definidos en database/schema.sql (cálculo de
`expiration_date`, ENUMs nativos) — eso se cubre en
tests/test_integration_postgres.py, que se salta automáticamente si no hay
una base de datos Postgres de prueba configurada (ver ese archivo).
"""
from __future__ import annotations

import pytest
from sqlalchemy import BigInteger, Column, String, Table, create_engine, event
from sqlalchemy.orm import Session

from app.models import Base, ShelfLifeRule

# `users` no es un modelo ORM de esta app: en producción ya existe en
# Postgres vía database/schema.sql (o el sistema de auth real). Para poder
# ejercitar la FK completa `pantry_inventory.user_id -> users.id` en el
# SQLite de los tests, se registra aquí un stub equivalente en el mismo
# `MetaData` de Base.
users_table = Table(
    "users",
    Base.metadata,
    Column("id", BigInteger, primary_key=True),
    Column("email", String(255), nullable=False, unique=True),
    extend_existing=True,
)


@pytest.fixture()
def engine():
    """Motor SQLite en memoria con el esquema completo de `app.models`."""
    eng = create_engine("sqlite:///:memory:")

    # SQLite trae las foreign keys desactivadas por defecto; sin esto, los
    # tests de ON DELETE SET NULL / CASCADE no ejercitarían nada real.
    @event.listens_for(eng, "connect")
    def _enable_sqlite_fk(dbapi_connection, connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def session(engine):
    with Session(engine) as db_session:
        yield db_session


@pytest.fixture()
def user_id(session) -> int:
    """Inserta un usuario stub y devuelve su id, para usar como FK."""
    session.execute(users_table.insert().values(id=1, email="test@example.com"))
    session.commit()
    return 1


@pytest.fixture()
def milk_rule(session) -> ShelfLifeRule:
    """Regla de caducidad de referencia (leche) reutilizada en varios tests."""
    rule = ShelfLifeRule(
        ingredient_name="Leche entera",
        category="dairy",
        default_storage="refrigerator",
        shelf_life_days_unopened=10,
        open_shelf_life_multiplier="0.70",
        frozen_shelf_life_days=90,
    )
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return rule

"""Minimal `users` table definition, registered so foreign keys resolve.

`users` is not owned by this app. It exists in PostgreSQL via
database/schema.sql as a stub, and in a real deployment it would belong to an
identity provider (Cognito, Auth0, Supabase). This app never reads or writes
it, so there is no ORM model and no mapped class here.

It still has to be present in `Base.metadata`. `pantry_inventory.user_id`
carries a foreign key to `users.id`, and SQLAlchemy resolves that target
lazily -- the first query that forces table sorting raises
`NoReferencedTableError` if nothing registered it. A plain
`select(PantryInventory).where(...)` does not trigger that, but a query with
an `outerjoin` does, which is why `update_pantry_context` failed against a
real database while `modify_item_state` succeeded.

This was previously declared only in tests/conftest.py, so the whole suite
passed while the deployed server raised on a tool call.
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Column, String, Table

from app.models.base import Base

users_table = Table(
    "users",
    Base.metadata,
    Column("id", BigInteger, primary_key=True),
    Column("email", String(255), nullable=False, unique=True),
    extend_existing=True,
)

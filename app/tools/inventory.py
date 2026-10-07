"""Tools MCP para consultar y modificar el estado del inventario."""
from __future__ import annotations

from datetime import date
from typing import Any

from mcp.server.fastmcp import FastMCP

from app.db.session import async_session_factory
from app.models import StorageLocation
from app.services import inventory


def register_inventory_tools(server: FastMCP) -> None:
    """Registra las tools de inventario en el servidor MCP."""

    @server.tool()
    async def get_inventory_status(
        user_id: int, include_consumed: bool = False
    ) -> dict[str, Any]:
        """Devuelve el inventario y su estado de caducidad calculado por PostgreSQL."""
        async with async_session_factory() as session:
            return await inventory.get_inventory_status(
                session, user_id, include_consumed
            )

    @server.tool()
    async def modify_item_state(
        user_id: int,
        item_id: int,
        is_opened: bool | None = None,
        opened_date: date | None = None,
        storage_location: StorageLocation | None = None,
        is_consumed: bool | None = None,
    ) -> dict[str, Any]:
        """Marca un artículo como abierto/consumido o cambia su ubicación."""
        async with async_session_factory() as session:
            return await inventory.modify_item_state(
                session,
                user_id,
                item_id,
                is_opened=is_opened,
                opened_date=opened_date,
                storage_location=storage_location,
                is_consumed=is_consumed,
            )

    @server.tool()
    async def ingest_receipt_items(
        user_id: int,
        image_base64: str,
        media_type: str = "image/jpeg",
    ) -> dict[str, Any]:
        """Extrae artículos de un recibo en base64 y los agrega al inventario."""
        async with async_session_factory() as session:
            return await inventory.ingest_receipt_items(
                session, user_id, image_base64, media_type
            )
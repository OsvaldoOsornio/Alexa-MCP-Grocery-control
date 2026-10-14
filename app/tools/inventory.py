"""MCP tools for reading and modifying the inventory state."""
from __future__ import annotations

from datetime import date
from typing import Any

from mcp.server.fastmcp import FastMCP

from app.db.session import async_session_factory
from app.models import RipenessModifier, StorageLocation
from app.services import context, inventory
from app.tools.errors import sanitize_tool_errors


def register_inventory_tools(server: FastMCP) -> None:
    """Register the inventory tools on the MCP server."""

    @server.tool()
    @sanitize_tool_errors("Could not read the inventory - see the server log.")
    async def get_inventory_status(
        user_id: int, include_consumed: bool = False
    ) -> dict[str, Any]:
        """Return the inventory and the expiry status PostgreSQL calculated."""
        async with async_session_factory() as session:
            return await inventory.get_inventory_status(
                session, user_id, include_consumed
            )

    @server.tool()
    @sanitize_tool_errors("Could not update the item - see the server log.")
    async def modify_item_state(
        user_id: int,
        item_id: int,
        is_opened: bool | None = None,
        opened_date: date | None = None,
        storage_location: StorageLocation | None = None,
        is_consumed: bool | None = None,
    ) -> dict[str, Any]:
        """Mark an item opened or consumed, or change where it is stored."""
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
    @sanitize_tool_errors("Could not adjust the item shelf life - see the server log.")
    async def update_pantry_context(
        user_id: int,
        item_name: str,
        modifier: RipenessModifier,
    ) -> dict[str, Any]:
        """Adjust an item's shelf life from what the user observed out loud."""
        async with async_session_factory() as session:
            return await context.update_pantry_context(
                session, user_id, item_name, modifier
            )

    @server.tool()
    @sanitize_tool_errors(
        "Receipt extraction failed - check that AWS credentials with Bedrock "
        "access are configured, then see the server log."
    )
    async def ingest_receipt_items(
        user_id: int,
        image_base64: str,
        media_type: str = "image/jpeg",
    ) -> dict[str, Any]:
        """Extract items from a base64 receipt image and add them to the inventory."""
        async with async_session_factory() as session:
            return await inventory.ingest_receipt_items(
                session, user_id, image_base64, media_type
            )
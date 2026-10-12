"""MCP tool for generating and adapting recipes around the live pantry."""
from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from app.db.session import async_session_factory
from app.services import recipe


def register_recipe_tools(server: FastMCP) -> None:
    """Register the recipe tools on the MCP server."""

    @server.tool()
    async def generate_and_adapt_recipe(
        user_id: int,
        servings: int = 2,
        exclude_items: list[str] | None = None,
        prior_recipe: str | None = None,
    ) -> dict[str, Any]:
        """Build a recipe around what expires soonest, or re-plan an existing one.

        Pass `prior_recipe` together with `exclude_items` to adapt a recipe
        mid-cook when an ingredient has run out.
        """
        async with async_session_factory() as session:
            return await recipe.generate_and_adapt_recipe(
                session,
                user_id,
                servings=servings,
                exclude_items=exclude_items,
                prior_recipe=prior_recipe,
            )

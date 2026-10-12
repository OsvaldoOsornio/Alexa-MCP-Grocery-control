"""Entry point for the MCP server (Streamable HTTP transport)."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from app.core.config import get_settings
from app.tools.inventory import register_inventory_tools
from app.tools.recipe import register_recipe_tools

settings = get_settings()

mcp = FastMCP(
    settings.mcp_server_name,
    host=settings.mcp_server_host,
    port=settings.mcp_server_port,
)
register_inventory_tools(mcp)
register_recipe_tools(mcp)


def main() -> None:
    """Start the MCP server."""
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()

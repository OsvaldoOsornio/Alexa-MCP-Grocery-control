"""Entry point del servidor MCP (transporte Streamable HTTP)."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from app.core.config import get_settings
from app.tools.inventory import register_inventory_tools

settings = get_settings()

mcp = FastMCP(
    settings.mcp_server_name,
    host=settings.mcp_server_host,
    port=settings.mcp_server_port,
)
register_inventory_tools(mcp)


def main() -> None:
    """Arranca el servidor MCP."""
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()

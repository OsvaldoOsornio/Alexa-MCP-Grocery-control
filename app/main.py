"""Entry point for the MCP server (Streamable HTTP transport)."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from app.core.config import get_settings
from app.tools.inventory import register_inventory_tools
from app.tools.recipe import register_recipe_tools


def build_server() -> FastMCP:
    """Build a configured `FastMCP` instance with every tool registered.

    Running the server at all needs only the `mcp` singleton below. This
    factory exists for the tests: a FastMCP's `session_manager.run()` may be
    entered exactly once per instance, so two tests that serve the app
    in-process cannot share one server. Without a factory the second test to
    run fails with "run() can only be called once per instance", which makes
    the suite order-dependent rather than wrong in any obvious way.
    """
    settings = get_settings()
    server = FastMCP(
        settings.mcp_server_name,
        host=settings.mcp_server_host,
        port=settings.mcp_server_port,
    )
    register_inventory_tools(server)
    register_recipe_tools(server)
    return server


mcp = build_server()


def main() -> None:
    """Start the MCP server."""
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()

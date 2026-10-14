"""Drive the running server with the official MCP Python SDK client.

Why a script and not another test: the suite serves the app in-process over
ASGI, which proves the handler logic but not that a real client can negotiate
a real session over a real socket. This connects the way Alexa+ or any
MCP-capable desktop client would -- `mcp.client.streamable_http` plus
`ClientSession` from the SDK, no hand-rolled JSON-RPC -- so what it prints is
evidence about the protocol, not about our own HTTP code.

Run it against a server already started with `python -m app.main`:

    python scripts/mcp_smoke.py
    python scripts/mcp_smoke.py --url http://127.0.0.1:8000/mcp --user-id 1

The URL host must be one the SDK's DNS rebinding protection allows --
`127.0.0.1`, `localhost` or `[::1]` -- because the server binds to loopback
and the SDK then rejects any other Host header with HTTP 421.

Exit codes: 0 when the session negotiated and every tool call succeeded,
1 when a tool call came back as an error, 2 when the server could not be
reached at all. A tool error still exits non-zero but is reported in full,
because a readable failure (such as the database not running) is a result
worth seeing rather than a crash.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import CallToolResult

DEFAULT_URL = "http://127.0.0.1:8000/mcp"
DEFAULT_USER_ID = 1

RULE = "-" * 72


def _section(title: str) -> None:
    print(f"\n{RULE}\n{title}\n{RULE}")


def _render_tool_result(result: CallToolResult) -> None:
    """Print a tool reply, preferring the structured payload over the text."""
    if result.isError:
        print("  RESULT: error")
        for block in result.content:
            text = getattr(block, "text", None)
            if text:
                print(f"  {text}")
        return

    print("  RESULT: ok")
    # structuredContent is what a programmatic client consumes; the text
    # blocks are the same data rendered for a human or a model.
    if result.structuredContent is not None:
        rendered = json.dumps(result.structuredContent, indent=2, default=str)
        for line in rendered.splitlines():
            print(f"  {line}")
    else:
        for block in result.content:
            text = getattr(block, "text", None)
            if text:
                print(f"  {text}")


async def run_smoke(url: str, user_id: int) -> int:
    print(f"Connecting to {url} with the MCP Python SDK client")

    async with streamablehttp_client(url) as (read_stream, write_stream, get_session_id):
        async with ClientSession(read_stream, write_stream) as session:
            _section("1. initialize")
            init = await session.initialize()
            print(f"  server          : {init.serverInfo.name} {init.serverInfo.version}")
            print(f"  protocolVersion : {init.protocolVersion}")
            print(f"  capabilities    : {init.capabilities.model_dump(exclude_none=True)}")
            # Proof of a negotiated protocol session rather than stateless
            # request/response: the transport is carrying an Mcp-Session-Id.
            print(f"  Mcp-Session-Id  : {get_session_id()}")

            _section("2. tools/list")
            listed = await session.list_tools()
            for tool in listed.tools:
                required = tool.inputSchema.get("required", [])
                summary = (tool.description or "").strip().splitlines()
                print(f"  {tool.name}")
                print(f"      required: {required or '(none)'}")
                if summary:
                    print(f"      {summary[0]}")
            print(f"  {len(listed.tools)} tools advertised")

            failures = 0

            _section("3. tools/call get_inventory_status")
            print(f"  arguments: {{'user_id': {user_id}}}")
            status = await session.call_tool(
                "get_inventory_status", {"user_id": user_id}
            )
            _render_tool_result(status)
            failures += bool(status.isError)

            # A second call with a deliberately invalid argument. This is the
            # other half of the contract: validation text must come back
            # readable, not as a sanitized stand-in or a stack trace.
            _section("4. tools/call generate_and_adapt_recipe (invalid servings)")
            print(f"  arguments: {{'user_id': {user_id}, 'servings': 99}}")
            print("  expecting a readable validation message, not a traceback")
            invalid = await session.call_tool(
                "generate_and_adapt_recipe", {"user_id": user_id, "servings": 99}
            )
            _render_tool_result(invalid)

            _section("Summary")
            if failures:
                print(f"  Session negotiated; {failures} tool call(s) returned an error.")
                print("  If the database is down, start it with: docker compose up -d")
                return 1
            print("  Session negotiated and every tool call succeeded.")
            return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default=DEFAULT_URL, help=f"default: {DEFAULT_URL}")
    parser.add_argument(
        "--user-id",
        type=int,
        default=DEFAULT_USER_ID,
        help=f"user_id passed to the tools; default: {DEFAULT_USER_ID}",
    )
    args = parser.parse_args(argv)

    try:
        return asyncio.run(run_smoke(args.url, args.user_id))
    except Exception as error:
        print("\nCould not complete the MCP session:", file=sys.stderr)
        for leaf in _leaf_errors(error):
            print(f"  {type(leaf).__name__}: {leaf}", file=sys.stderr)
        print(
            "\nIs the server running? Start it with: python -m app.main"
            f"\nIt must be listening on {args.url}",
            file=sys.stderr,
        )
        return 2


def _leaf_errors(error: BaseException) -> list[BaseException]:
    """Flatten an exception group into the real failures inside it.

    The SDK runs its transport in a task group, so a refused connection
    surfaces as a nested ExceptionGroup. Printing the leaves is the difference
    between "server not running" and six frames of anyio internals. Detected
    by attribute rather than against `ExceptionGroup`, so the script still
    runs on Python 3.10, which the README supports and which lacks that
    builtin -- and `except*` is not available there either.
    """
    nested = getattr(error, "exceptions", None)
    if nested is None:
        return [error]
    leaves: list[BaseException] = []
    for child in nested:
        leaves.extend(_leaf_errors(child))
    return leaves


if __name__ == "__main__":
    raise SystemExit(main())

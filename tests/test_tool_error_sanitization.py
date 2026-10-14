"""What a failing tool actually puts on the wire.

These tests go through the real Streamable HTTP transport rather than calling
the decorator directly, because the thing being guarded is the *client's*
view. FastMCP wraps whatever escapes a tool body into "Error executing tool
<name>: <exc>" and sends it, so the only honest assertion is on the text a
client receives.

Two behaviours have to hold at once, and they pull in opposite directions:
a deliberate `ValueError` is the product speaking to the user and must survive
verbatim, while anything unexpected must be reduced to an instruction before
it leaves the process.
"""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest

from app.main import build_server
from app.services import inventory
from app.tools import errors as tool_errors
from app.tools import inventory as inventory_tools

# The repr that must never reach a client. It carries a Windows error code and
# a connection string, which is the shape of the leak these tests exist for.
LEAKED_SECRET = "postgresql://postgres:changeme@10.0.0.7:5432"


class _SessionContext:
    """Stand in for `async_session_factory` so no database is needed."""

    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False


def _response_json(response: httpx.Response) -> dict[str, Any]:
    if "application/json" in response.headers.get("content-type", ""):
        return response.json()

    data_lines = [
        line.removeprefix("data:").strip()
        for line in response.text.splitlines()
        if line.startswith("data:")
    ]
    assert data_lines, f"No JSON-RPC event found in: {response.text!r}"
    return json.loads(data_lines[-1])


async def _call_inventory_status(client: httpx.AsyncClient) -> dict[str, Any]:
    """Negotiate a session and call `get_inventory_status` once."""
    headers = {
        "accept": "application/json, text/event-stream",
        "content-type": "application/json",
    }
    initialized = await client.post(
        "/mcp",
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "qa-error-test", "version": "1.0"},
            },
        },
    )
    assert initialized.status_code == 200
    session_headers = {**headers, "mcp-session-id": initialized.headers["mcp-session-id"]}

    await client.post(
        "/mcp",
        headers=session_headers,
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
    )

    called = await client.post(
        "/mcp",
        headers=session_headers,
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "get_inventory_status",
                "arguments": {"user_id": 17},
            },
        },
    )
    assert called.status_code == 200
    return _response_json(called)


async def _text_of_failed_call(monkeypatch: pytest.MonkeyPatch, raised: Exception) -> str:
    """Make `get_inventory_status` raise `raised` and return the client's text."""
    monkeypatch.setattr(inventory_tools, "async_session_factory", _SessionContext)
    monkeypatch.setattr(
        inventory, "get_inventory_status", AsyncMock(side_effect=raised)
    )

    # Three things are load-bearing here. A fresh server, because
    # `session_manager.run()` may only be entered once per instance. Both
    # `streamable_http_app()` and that separate `run()`, because the app alone
    # serves nothing. And a base URL whose host the SDK's DNS rebinding
    # protection allows, or every request answers 421 (see app/core/config.py).
    mcp = build_server()
    app = mcp.streamable_http_app()
    async with mcp.session_manager.run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://127.0.0.1:8000",
        ) as client:
            payload = await _call_inventory_status(client)

    result = payload["result"]
    assert result["isError"] is True, f"Expected a tool error, got: {payload!r}"
    return " ".join(
        block["text"] for block in result["content"] if block["type"] == "text"
    )


@pytest.mark.asyncio
async def test_value_error_message_still_reaches_the_client(monkeypatch):
    """Validation text is the product talking; it must survive the guard."""
    message = "Provide at least one state field to modify."
    text = await _text_of_failed_call(monkeypatch, ValueError(message))

    assert message in text
    assert tool_errors.DATABASE_UNAVAILABLE not in text


@pytest.mark.asyncio
async def test_unexpected_exception_does_not_leak_its_repr(monkeypatch):
    """An internal failure is reduced to an instruction, not a stack detail."""
    boom = RuntimeError(f"[WinError 1225] refused while dialling {LEAKED_SECRET}")
    text = await _text_of_failed_call(monkeypatch, boom)

    assert LEAKED_SECRET not in text
    assert "WinError" not in text
    assert "1225" not in text
    assert "RuntimeError" not in text
    # The client still learns which tool failed, and what to do next.
    assert "get_inventory_status" in text
    assert "see the server log" in text


@pytest.mark.asyncio
async def test_connection_failure_names_the_one_command_that_fixes_it(monkeypatch):
    """Connection refused is the common case, so it gets the specific remedy."""
    text = await _text_of_failed_call(
        monkeypatch, ConnectionRefusedError(1225, f"dialling {LEAKED_SECRET}")
    )

    assert tool_errors.DATABASE_UNAVAILABLE in text
    assert "docker compose up -d" in text
    assert LEAKED_SECRET not in text
    assert "1225" not in text


@pytest.mark.asyncio
async def test_unexpected_failures_are_logged_server_side(monkeypatch, caplog):
    """Sanitizing the client's view must not throw the diagnosis away."""
    with caplog.at_level("ERROR", logger="app.tools.errors"):
        await _text_of_failed_call(
            monkeypatch, RuntimeError(f"broken: {LEAKED_SECRET}")
        )

    assert any(
        "get_inventory_status" in record.getMessage() and record.exc_info
        for record in caplog.records
    ), "The server log should keep the tool name and the traceback."

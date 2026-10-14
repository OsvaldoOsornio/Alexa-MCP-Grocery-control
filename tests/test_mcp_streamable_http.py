"""HTTP integration tests for the MCP Streamable HTTP protocol."""
from __future__ import annotations

import json
from datetime import date
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from mcp.shared.version import LATEST_PROTOCOL_VERSION

from app.main import build_server
from app.models import RipenessModifier, StorageLocation
from app.services import context, inventory, recipe
from app.tools import inventory as inventory_tools
from app.tools import recipe as recipe_tools


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


@pytest.mark.asyncio
async def test_streamable_http_negotiates_lists_and_calls_inventory_tools(monkeypatch):
    fake_session = object()

    class SessionContext:
        async def __aenter__(self):
            return fake_session

        async def __aexit__(self, exc_type, exc_value, traceback):
            return False

    status_result = {"user_id": 17, "count": 0, "items": []}
    modify_result = {"success": True, "item": {"id": 42}}
    get_status_mock = AsyncMock(return_value=status_result)
    modify_state_mock = AsyncMock(return_value=modify_result)
    monkeypatch.setattr(inventory_tools, "async_session_factory", SessionContext)
    monkeypatch.setattr(recipe_tools, "async_session_factory", SessionContext)
    monkeypatch.setattr(inventory, "get_inventory_status", get_status_mock)
    monkeypatch.setattr(inventory, "modify_item_state", modify_state_mock)

    # A fresh server per test: `session_manager.run()` may only be entered
    # once per FastMCP instance, so sharing the module singleton would make
    # whichever test ran second fail.
    mcp = build_server()
    app = mcp.streamable_http_app()
    headers = {
        "accept": "application/json, text/event-stream",
        "content-type": "application/json",
    }
    transport = httpx.ASGITransport(app=app)

    async with mcp.session_manager.run():
        # The host must be one allowed by the DNS rebinding protection the
        # SDK enables automatically when the server listens on 127.0.0.1
        # (see app/core/config.py). "testserver" would be rejected with 421.
        async with httpx.AsyncClient(
            transport=transport, base_url="http://127.0.0.1:8000"
        ) as client:
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
                        "clientInfo": {"name": "qa-test", "version": "1.0"},
                    },
                },
            )
            assert initialized.status_code == 200
            initialize_result = _response_json(initialized)["result"]
            assert initialize_result["protocolVersion"] == LATEST_PROTOCOL_VERSION
            assert initialize_result["protocolVersion"] == "2025-11-25"

            session_id = initialized.headers.get("mcp-session-id")
            assert session_id
            session_headers = {**headers, "mcp-session-id": session_id}

            notification = await client.post(
                "/mcp",
                headers=session_headers,
                json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            )
            assert notification.status_code == 202

            listed = await client.post(
                "/mcp",
                headers=session_headers,
                json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            )
            assert listed.status_code == 200
            tools = _response_json(listed)["result"]["tools"]
            tools_by_name = {tool["name"]: tool for tool in tools}
            assert set(tools_by_name) == {
                "get_inventory_status",
                "modify_item_state",
                "ingest_receipt_items",
                "update_pantry_context",
                "generate_and_adapt_recipe",
            }

            status_schema = tools_by_name["get_inventory_status"]["inputSchema"]
            assert status_schema["required"] == ["user_id"]
            assert status_schema["properties"]["user_id"]["type"] == "integer"
            assert (
                status_schema["properties"]["include_consumed"]["default"] is False
            )

            modify_schema = tools_by_name["modify_item_state"]["inputSchema"]
            assert set(modify_schema["required"]) == {"user_id", "item_id"}
            assert modify_schema["$defs"]["StorageLocation"]["enum"] == [
                "pantry",
                "refrigerator",
                "freezer",
            ]

            context_schema = tools_by_name["update_pantry_context"]["inputSchema"]
            assert set(context_schema["required"]) == {
                "user_id",
                "item_name",
                "modifier",
            }
            assert context_schema["$defs"]["RipenessModifier"]["enum"] == [
                "very_ripe",
                "ripe",
                "underripe",
                "smells_off",
                "opened_long_ago",
            ]

            recipe_schema = tools_by_name["generate_and_adapt_recipe"]["inputSchema"]
            assert recipe_schema["required"] == ["user_id"]
            assert recipe_schema["properties"]["servings"]["default"] == 2

            receipt_schema = tools_by_name["ingest_receipt_items"]["inputSchema"]
            assert set(receipt_schema["required"]) == {"user_id", "image_base64"}
            assert (
                receipt_schema["properties"]["media_type"]["default"]
                == "image/jpeg"
            )

            status_call = await client.post(
                "/mcp",
                headers=session_headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "get_inventory_status",
                        "arguments": {"user_id": 17},
                    },
                },
            )
            assert status_call.status_code == 200
            status_rpc_result = _response_json(status_call)["result"]
            assert not status_rpc_result.get("isError", False)
            assert status_rpc_result["structuredContent"] == status_result
            get_status_mock.assert_awaited_once_with(fake_session, 17, False)

            modify_call = await client.post(
                "/mcp",
                headers=session_headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {
                        "name": "modify_item_state",
                        "arguments": {
                            "user_id": 17,
                            "item_id": 42,
                            "is_opened": True,
                            "opened_date": "2026-10-07",
                            "storage_location": "freezer",
                            "is_consumed": False,
                        },
                    },
                },
            )
            assert modify_call.status_code == 200
            modify_rpc_result = _response_json(modify_call)["result"]
            assert not modify_rpc_result.get("isError", False)
            assert modify_rpc_result["structuredContent"] == modify_result
            modify_state_mock.assert_awaited_once_with(
                fake_session,
                17,
                42,
                is_opened=True,
                opened_date=date(2026, 10, 7),
                storage_location=StorageLocation.FREEZER,
                is_consumed=False,
            )

            receipt_result = {
                "success": True,
                "user_id": 17,
                "count": 1,
                "items": [{"id": 43, "display_name": "Milk"}],
            }
            receipt_mock = AsyncMock(return_value=receipt_result)
            monkeypatch.setattr(inventory, "ingest_receipt_items", receipt_mock)
            receipt_call = await client.post(
                "/mcp",
                headers=session_headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "tools/call",
                    "params": {
                        "name": "ingest_receipt_items",
                        "arguments": {
                            "user_id": 17,
                            "image_base64": "ZmFrZS1pbWFnZQ==",
                        },
                    },
                },
            )
            assert receipt_call.status_code == 200
            receipt_rpc_result = _response_json(receipt_call)["result"]
            assert not receipt_rpc_result.get("isError", False)
            assert receipt_rpc_result["structuredContent"] == receipt_result
            receipt_mock.assert_awaited_once_with(
                fake_session, 17, "ZmFrZS1pbWFnZQ==", "image/jpeg"
            )

            context_result = {"success": True, "item": {"id": 44}}
            context_mock = AsyncMock(return_value=context_result)
            monkeypatch.setattr(context, "update_pantry_context", context_mock)
            context_call = await client.post(
                "/mcp",
                headers=session_headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 6,
                    "method": "tools/call",
                    "params": {
                        "name": "update_pantry_context",
                        "arguments": {
                            "user_id": 17,
                            "item_name": "Avocados",
                            "modifier": "very_ripe",
                        },
                    },
                },
            )
            assert context_call.status_code == 200
            context_rpc_result = _response_json(context_call)["result"]
            assert not context_rpc_result.get("isError", False)
            assert context_rpc_result["structuredContent"] == context_result
            # The string on the wire must arrive as the enum member.
            context_mock.assert_awaited_once_with(
                fake_session, 17, "Avocados", RipenessModifier.VERY_RIPE
            )

            recipe_result = {"success": True, "adapted": True, "recipe": {"title": "X"}}
            recipe_mock = AsyncMock(return_value=recipe_result)
            monkeypatch.setattr(recipe, "generate_and_adapt_recipe", recipe_mock)
            recipe_call = await client.post(
                "/mcp",
                headers=session_headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 7,
                    "method": "tools/call",
                    "params": {
                        "name": "generate_and_adapt_recipe",
                        "arguments": {
                            "user_id": 17,
                            "servings": 4,
                            "exclude_items": ["Cream"],
                            "prior_recipe": "Carbonara",
                        },
                    },
                },
            )
            assert recipe_call.status_code == 200
            recipe_rpc_result = _response_json(recipe_call)["result"]
            assert not recipe_rpc_result.get("isError", False)
            assert recipe_rpc_result["structuredContent"] == recipe_result
            recipe_mock.assert_awaited_once_with(
                fake_session,
                17,
                servings=4,
                exclude_items=["Cream"],
                prior_recipe="Carbonara",
            )
"""Pruebas de integración HTTP para el protocolo MCP Streamable HTTP."""
from __future__ import annotations

import json
from datetime import date
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from mcp.shared.version import LATEST_PROTOCOL_VERSION

from app.main import mcp
from app.models import StorageLocation
from app.services import inventory
from app.tools import inventory as inventory_tools


def _response_json(response: httpx.Response) -> dict[str, Any]:
    if "application/json" in response.headers.get("content-type", ""):
        return response.json()

    data_lines = [
        line.removeprefix("data:").strip()
        for line in response.text.splitlines()
        if line.startswith("data:")
    ]
    assert data_lines, f"No se encontró un evento JSON-RPC en: {response.text!r}"
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
    monkeypatch.setattr(inventory, "get_inventory_status", get_status_mock)
    monkeypatch.setattr(inventory, "modify_item_state", modify_state_mock)

    app = mcp.streamable_http_app()
    headers = {
        "accept": "application/json, text/event-stream",
        "content-type": "application/json",
    }
    transport = httpx.ASGITransport(app=app)

    async with mcp.session_manager.run():
        # El host debe ser uno de los permitidos por la protección anti DNS
        # rebinding que el SDK activa automáticamente cuando el servidor
        # escucha en 127.0.0.1 (ver app/core/config.py). "testserver" se
        # rechazaría con 421.
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
                "items": [{"id": 43, "display_name": "Leche"}],
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
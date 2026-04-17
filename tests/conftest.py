"""Shared fixtures and async helpers for synapse-todo-board tests.

Mirrors the pattern used by upjack's own test suite (see
`products/upjack/code/lib/python/tests/test_server.py`): an in-memory
`fastmcp.Client` drives the server, and async interactions are dispatched
through a tiny `_run()` helper so individual tests stay synchronous.
"""

from __future__ import annotations

import asyncio
import importlib
import json
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Async helpers — identical shape to upjack's own test helpers
# ---------------------------------------------------------------------------


def _run(coro):
    """Run a coroutine synchronously."""
    return asyncio.run(coro)


async def _list_tool_names(mcp) -> set[str]:
    from fastmcp import Client

    async with Client(mcp) as client:
        tools = await client.list_tools()
        return {t.name for t in tools}


async def _call_tool(mcp, name: str, arguments: dict | None = None) -> Any:
    from fastmcp import Client

    async with Client(mcp) as client:
        result = await client.call_tool(name, arguments or {})
        if not result.content:
            return None
        return json.loads(result.content[0].text)


# ---------------------------------------------------------------------------
# mcp fixture — isolated workspace per test
# ---------------------------------------------------------------------------


@pytest.fixture
def mcp(tmp_path, monkeypatch):
    """Build a fresh synapse-todo-board MCP server bound to a tmp workspace.

    `synapse_todo_board.server` constructs its `FastMCP` instance at module
    import time, so we set `UPJACK_ROOT` and `MPAK_WORKSPACE` to the test's
    `tmp_path` and reload the module to force a re-bind.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("UPJACK_ROOT", str(workspace))
    monkeypatch.setenv("MPAK_WORKSPACE", str(workspace))

    import synapse_todo_board.server as server_module

    importlib.reload(server_module)
    return server_module.mcp

"""Contract tests for synapse-todo-board's MCP server.

Phase 1 of the synapse-tests initiative — prevents the class of drift that
went undetected during the upjack 0.4.4 → 0.5.1 upgrade (the `{data: {...}}`
contract flatten). These tests verify:

1. Server instantiates cleanly from the manifest.
2. The published tool surface and each tool's argument contract match the
   snapshot in `tests/fixtures/tool-contract.json`.
3. All hand-written domain tools are registered.
4. Flat kwargs are the accepted create shape.
5. The legacy `{data: {...}}` wrapper is rejected via JSON Schema validation.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from tests.conftest import _call_tool, _list_tool_names, _run


# ---------------------------------------------------------------------------
# Published tool contract
# ---------------------------------------------------------------------------

# Every tool a host sees in tools/list. Task creation is board-scoped through
# `create_board_task`, so a raw `create_task` must never be listed.
EXPECTED_TOOLS = {
    "create_board",
    "get_board",
    "update_board",
    "list_boards",
    "search_boards",
    "delete_board",
    "get_task",
    "update_task",
    "list_tasks",
    "search_tasks",
    "delete_task",
    "seed_data",
    "add_field",
    "query_boards_by_relationship",
    "get_related_board",
    "get_board_composite",
    "query_tasks_by_relationship",
    "get_related_task",
    "get_task_composite",
    "rebuild_index",
    "create_board_task",
    "find_board_task",
    "move_task",
    "reorder_column",
    "board_summary",
    "batch_archive",
    "archive_task",
    "set_custom_instructions",
}

_CONTRACT_PATH = Path(__file__).parent / "fixtures" / "tool-contract.json"


def _property_type(prop: dict):
    """Return a property's JSON Schema type, the types of its `anyOf`, or "any"."""
    if "type" in prop:
        return prop["type"]
    if "anyOf" in prop:
        return sorted(option.get("type", "any") for option in prop["anyOf"])
    return "any"


async def _tool_contract(mcp) -> dict[str, dict]:
    """Reduce each listed tool to its required arguments and argument types."""
    from fastmcp import Client

    async with Client(mcp) as client:
        tools = await client.list_tools()
    return {
        tool.name: {
            "required": sorted(tool.inputSchema.get("required", [])),
            "properties": {
                name: _property_type(prop)
                for name, prop in sorted(tool.inputSchema.get("properties", {}).items())
            },
        }
        for tool in sorted(tools, key=lambda t: t.name)
    }


# ---------------------------------------------------------------------------
# Contract tests
# ---------------------------------------------------------------------------


def test_server_instantiates(mcp):
    """`create_server(manifest, root=tmp_path)` produces a FastMCP instance."""
    assert isinstance(mcp, FastMCP)


def test_published_tool_surface_is_preserved(mcp):
    """tools/list publishes exactly `EXPECTED_TOOLS`, nothing more or less."""
    assert _run(_list_tool_names(mcp)) == EXPECTED_TOOLS


def test_tool_argument_contract_matches_snapshot(mcp):
    """Argument names, required arguments and types match the snapshot.

    A renamed, dropped or retyped argument breaks every caller that still
    uses the old shape, so the change must show up here first. When a
    change is intended, rewrite the fixture with
    `UPDATE_TOOL_CONTRACT=1 pytest tests/test_server.py -k argument_contract`
    and review its diff.
    """
    actual = _run(_tool_contract(mcp))
    if os.environ.get("UPDATE_TOOL_CONTRACT"):
        lines = [f"  {json.dumps(name)}: {json.dumps(entry)}" for name, entry in actual.items()]
        _CONTRACT_PATH.write_text("{\n" + ",\n".join(lines) + "\n}\n")
    assert actual == json.loads(_CONTRACT_PATH.read_text())


def test_tool_schemas_have_explicit_object_roots_for_strict_hosts(mcp):
    """Every input and output schema declares `type: object` at its root."""
    from fastmcp import Client

    async def check():
        async with Client(mcp) as client:
            for tool in await client.list_tools():
                assert tool.inputSchema.get("type") == "object", tool.name
                if tool.outputSchema is not None:
                    assert tool.outputSchema.get("type") == "object", tool.name

    _run(check())


def test_hand_written_tools_registered(mcp):
    """All 6 custom domain tools are registered."""
    listed = _run(_list_tool_names(mcp))
    expected = {
        "archive_task",
        "batch_archive",
        "board_summary",
        "create_board_task",
        "find_board_task",
        "move_task",
        "reorder_column",
    }
    missing = expected - listed
    assert not missing, f"Missing hand-written tools: {sorted(missing)}"


def test_flat_kwargs_create_succeeds(mcp):
    """`create_board` accepts flat kwargs (the post-0.5.0 contract).

    Board columns require `key` (lowercase, regex `^[a-z][a-z0-9_]*$`) and
    `label` per the schema.
    """
    result = _run(
        _call_tool(
            mcp,
            "create_board",
            {
                "name": "Test Board",
                "columns": [{"key": "todo", "label": "To Do"}],
            },
        )
    )
    assert result["id"].startswith("bd_")
    assert result["name"] == "Test Board"
    assert result["columns"] == [{"key": "todo", "label": "To Do"}]
    assert result["type"] == "board"


def test_legacy_data_wrapper_rejected(mcp):
    """The pre-0.5.0 `{data: {...}}` envelope shape is no longer valid.

    With flat-kwargs as the contract, a call that passes only a `data` key is
    missing every required top-level field (`name`, `columns`) and fails JSON
    Schema validation before reaching the server. The client surfaces this
    as `fastmcp.exceptions.ToolError`.
    """
    with pytest.raises(ToolError):
        _run(
            _call_tool(
                mcp,
                "create_board",
                {
                    "data": {
                        "name": "Wrapped",
                        "columns": [{"key": "todo", "label": "To Do"}],
                    }
                },
            )
        )


# ---------------------------------------------------------------------------
# Regression locks for the 0.2.1 UI contract fixes.
#
# Each pair below pins both sides of a bug we just fixed: the flat-kwargs
# shape the UI now uses works end-to-end, AND the legacy shape it used to
# ship with fails validation. Together they make silent drift loud — a
# future Upjack upgrade or a partial revert of the UI fix would light up
# one of these tests instead of waiting for a customer to notice.
# ---------------------------------------------------------------------------


def _seed_board_and_task(mcp) -> tuple[str, str]:
    """Create a board + one task. Returns (board_id, task_id)."""
    board = _run(
        _call_tool(
            mcp,
            "create_board",
            {"name": "B", "columns": [{"key": "todo", "label": "To Do"}]},
        )
    )
    task = _run(
        _call_tool(
            mcp,
            "create_board_task",
            {"board_id": board["id"], "title": "Original"},
        )
    )
    return board["id"], task["id"]


def test_update_task_flat_kwargs_succeeds(mcp):
    """`update_task` accepts flat kwargs and mutates the targeted fields.

    Locks in the UI's current call shape: `{task_id, ...flat_fields}`.
    """
    _, task_id = _seed_board_and_task(mcp)
    updated = _run(
        _call_tool(
            mcp,
            "update_task",
            {"task_id": task_id, "title": "Updated", "priority": "high"},
        )
    )
    assert updated["title"] == "Updated"
    assert updated["priority"] == "high"


def test_update_task_entity_id_wrapper_shape_rejected(mcp):
    """The UI's pre-fix shape `{entity_id, data: {...}}` fails validation.

    `task_id` is the schema's required id param; `entity_id` is not a
    recognized property, so schema validation fails before dispatch.
    """
    with pytest.raises(ToolError):
        _run(
            _call_tool(
                mcp,
                "update_task",
                {"entity_id": "tk_01HXXX", "data": {"title": "ignored"}},
            )
        )


def test_delete_board_by_board_id_succeeds(mcp):
    """`delete_board` accepts `board_id` and soft-deletes the target."""
    board = _run(
        _call_tool(
            mcp,
            "create_board",
            {"name": "Doomed", "columns": [{"key": "todo", "label": "To Do"}]},
        )
    )
    _run(_call_tool(mcp, "delete_board", {"board_id": board["id"]}))

    # Default `list_boards` filters to status=active; soft-deleted boards
    # should no longer appear.
    listing = _run(_call_tool(mcp, "list_boards"))
    remaining = {b["id"] for b in listing["entities"]}
    assert board["id"] not in remaining


def test_delete_board_entity_id_rejected(mcp):
    """The UI's pre-fix shape `{entity_id: ...}` fails validation.

    Auto-generated delete tools use `{name}_id` (here: `board_id`) as the
    required id param. `entity_id` isn't a property of the schema.
    """
    with pytest.raises(ToolError):
        _run(_call_tool(mcp, "delete_board", {"entity_id": "bd_01HXXX"}))

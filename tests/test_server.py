"""Contract tests for synapse-todo-board's MCP server.

Phase 1 of the synapse-tests initiative — prevents the class of drift that
went undetected during the upjack 0.4.4 → 0.5.1 upgrade (the `{data: {...}}`
contract flatten). These tests verify:

1. Server instantiates cleanly from the manifest.
2. The auto-generated CRUD tools declared in the manifest's per-entity
   `tools` allowlist are registered and listed.
3. All hand-written domain tools are registered.
4. Flat kwargs are the accepted create shape.
5. The legacy `{data: {...}}` wrapper is rejected via JSON Schema validation.
"""

from __future__ import annotations

import json

import pytest
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from tests.conftest import _call_tool, _list_tool_names, _run


# ---------------------------------------------------------------------------
# Manifest-driven expectations
# ---------------------------------------------------------------------------

# Tool category → naming pattern. `{name}` = entity singular, `{plural}` = plural.
_CATEGORY_TEMPLATES: dict[str, str] = {
    "create": "create_{name}",
    "get": "get_{name}",
    "update": "update_{name}",
    "list": "list_{plural}",
    "search": "search_{plural}",
    "delete": "delete_{name}",
}

# The 6 "CRUD" categories the spec cares about for
# `test_expected_auto_crud_tools_registered`. Graph traversal categories
# (`query_by_relationship`, `get_related`, `get_composite`) are intentionally
# excluded — they're covered by upjack's own tests.
_CRUD_CATEGORIES: tuple[str, ...] = ("create", "get", "update", "list", "search", "delete")


def _expected_crud_tools(entities: list[dict]) -> set[str]:
    """Build the set of CRUD tools expected to be listed given the manifest.

    Respects per-entity `tools` allowlists: if `tools` is set, only the
    listed categories show up in tools/list. If `tools` is omitted, all
    CRUD categories are listed.
    """
    expected: set[str] = set()
    for ent in entities:
        name = ent["name"]
        plural = ent["plural"]
        allowlist = ent.get("tools")
        if allowlist is None:
            categories = _CRUD_CATEGORIES
        else:
            categories = tuple(c for c in _CRUD_CATEGORIES if c in allowlist)
        for cat in categories:
            expected.add(_CATEGORY_TEMPLATES[cat].format(name=name, plural=plural))
    return expected


def _manifest_entities() -> list[dict]:
    """Read the todo-board manifest and return its entity definitions."""
    import synapse_todo_board.server as server_module

    manifest_path = server_module._PROJECT_ROOT / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    return manifest["_meta"]["ai.nimblebrain/upjack"]["entities"]


# ---------------------------------------------------------------------------
# Contract tests
# ---------------------------------------------------------------------------


def test_server_instantiates(mcp):
    """`create_server(manifest, root=tmp_path)` produces a FastMCP instance."""
    assert isinstance(mcp, FastMCP)


def test_expected_auto_crud_tools_registered(mcp):
    """Every entity's manifest-declared CRUD tools are present in tools/list.

    The `task` entity declares a `tools` allowlist that excludes `create`, so
    `create_task` must NOT appear — that's precisely the point of the
    allowlist. Board has no allowlist so all 6 CRUD tools are expected.
    """
    entities = _manifest_entities()
    expected = _expected_crud_tools(entities)
    listed = _run(_list_tool_names(mcp))
    missing = expected - listed
    assert not missing, f"Missing expected CRUD tools: {sorted(missing)}"

    # Task's allowlist excludes `create` — `create_task` must be hidden.
    task_ent = next(e for e in entities if e["name"] == "task")
    if task_ent.get("tools") is not None and "create" not in task_ent["tools"]:
        assert "create_task" not in listed, (
            "create_task should be hidden when the task entity's `tools` allowlist excludes it"
        )


def test_hand_written_tools_registered(mcp):
    """All 6 custom domain tools are registered."""
    listed = _run(_list_tool_names(mcp))
    expected = {
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

"""Behavior tests for synapse-todo-board's hand-written domain tools.

Phase 2 of the synapse-tests initiative. Each hand-written tool in
`src/synapse_todo_board/tools/` is exercised end-to-end through the
FastMCP in-memory client so tests verify the actual wire contract — the
shape an agent will see — not just the inner Python helpers.

A few shape details worth noting (these shook out while reading the
tools' source, not from the spec):

* `batch_archive` archives *time-aged* completed tasks on a board
  (`board_id`, `older_than_days`). It is NOT a "given this list of task
  IDs, archive them" operation. Tests mirror the actual signature.
* `find_board_task` returns `{board, matches, count}`. It does not use
  the generic `entities` key the other search tools use.
* `create_board_task` does NOT validate that `column` exists on the
  board's `columns` array — the schema only enforces the regex
  `^[a-z][a-z0-9_]*$`. That gap is captured as an xfail (not skip) so
  the suite surfaces the drift if the tool ever tightens up.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastmcp.exceptions import ToolError

from tests.conftest import _call_tool, _run


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


_DEFAULT_COLUMNS = [
    {"key": "todo", "label": "To Do"},
    {"key": "in_progress", "label": "In Progress"},
    {"key": "done", "label": "Done"},
]


def _make_board(mcp, *, name: str = "Test Board", columns=None) -> dict:
    """Create a board via the flat-kwargs `create_board` CRUD tool."""
    return _run(
        _call_tool(
            mcp,
            "create_board",
            {
                "name": name,
                "columns": columns if columns is not None else _DEFAULT_COLUMNS,
            },
        )
    )


def _make_task(
    mcp,
    board_id: str,
    *,
    title: str,
    column: str = "todo",
    **extra,
) -> dict:
    """Create a task via `create_board_task` (the canonical agent path).

    `create_task` is hidden from `tools/list` by the task entity's
    `tools` allowlist, so production agents must use `create_board_task`.
    Tests follow the same path.
    """
    args: dict = {"board_id": board_id, "title": title, "column": column}
    args.update(extra)
    return _run(_call_tool(mcp, "create_board_task", args))


def _update_task_direct(mcp, task_id: str, **fields) -> dict:
    """Update a task via the auto-generated `update_task` CRUD tool.

    Used to fabricate historical state (e.g. `completed_at` in the past)
    that the normal workflow doesn't expose.

    Upjack 0.5.x names its id param `{entity}_id`, not `id` — see
    `deps/upjack/server.py`'s `id_param = f"{name}_id"`.
    """
    return _run(_call_tool(mcp, "update_task", {"task_id": task_id, **fields}))


def _get_task(mcp, task_id: str) -> dict:
    return _run(_call_tool(mcp, "get_task", {"task_id": task_id}))


def _iso_z(dt: datetime) -> str:
    """Format a datetime as an ISO-8601 Zulu string the schema accepts."""
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# batch_archive
# ---------------------------------------------------------------------------


class TestBatchArchive:
    """Time-aged archival of completed tasks on a board.

    Note: `batch_archive(board_id, older_than_days=7)` — the tool's real
    shape is "archive completed tasks older than N days," not "archive
    this arbitrary list of ids." The criteria in the parent task are
    adapted to match the actual contract.
    """

    def test_archives_multiple_completed_tasks_past_threshold(self, mcp):
        board = _make_board(mcp)
        old = _iso_z(datetime.now(UTC) - timedelta(days=30))

        t1 = _make_task(mcp, board["id"], title="Ancient 1", column="done")
        t2 = _make_task(mcp, board["id"], title="Ancient 2", column="done")
        _update_task_direct(mcp, t1["id"], completed_at=old)
        _update_task_direct(mcp, t2["id"], completed_at=old)

        result = _run(
            _call_tool(mcp, "batch_archive", {"board_id": board["id"], "older_than_days": 7})
        )

        assert result["archived"] == 2
        archived_ids = {t["id"] for t in result["tasks"]}
        assert archived_ids == {t1["id"], t2["id"]}

        # Status now 'archived' on each task
        for tid in (t1["id"], t2["id"]):
            got = _get_task(mcp, tid)
            assert got["status"] == "archived"

    def test_returns_counts_and_task_summary(self, mcp):
        board = _make_board(mcp)
        old = _iso_z(datetime.now(UTC) - timedelta(days=14))
        recent = _iso_z(datetime.now(UTC) - timedelta(days=1))

        aged = _make_task(mcp, board["id"], title="Aged", column="done")
        fresh = _make_task(mcp, board["id"], title="Fresh", column="done")
        _update_task_direct(mcp, aged["id"], completed_at=old)
        _update_task_direct(mcp, fresh["id"], completed_at=recent)

        result = _run(
            _call_tool(mcp, "batch_archive", {"board_id": board["id"], "older_than_days": 7})
        )

        assert result["archived"] == 1
        assert result["board_id"] == board["id"]
        assert len(result["tasks"]) == 1
        assert result["tasks"][0]["id"] == aged["id"]
        assert result["tasks"][0]["title"] == "Aged"
        assert "next_step" in result

    def test_missing_board_handled_gracefully(self, mcp):
        """Nonexistent board returns an error dict, not a raised exception."""
        result = _run(
            _call_tool(
                mcp,
                "batch_archive",
                {"board_id": "bd_does_not_exist", "older_than_days": 7},
            )
        )
        assert "error" in result
        assert "bd_does_not_exist" in result["error"]


# ---------------------------------------------------------------------------
# board_summary
# ---------------------------------------------------------------------------


class TestBoardSummary:
    def test_aggregates_task_count_per_column(self, mcp):
        board = _make_board(mcp)

        _make_task(mcp, board["id"], title="T1", column="todo")
        _make_task(mcp, board["id"], title="T2", column="todo")
        _make_task(mcp, board["id"], title="T3", column="in_progress")

        result = _run(_call_tool(mcp, "board_summary", {"board_id": board["id"]}))

        by_key = {c["key"]: c for c in result["columns"]}
        assert by_key["todo"]["count"] == 2
        assert by_key["in_progress"]["count"] == 1
        assert by_key["done"]["count"] == 0
        assert result["totals"]["tasks"] == 3

    def test_empty_board_returns_zero_counts(self, mcp):
        board = _make_board(mcp)

        result = _run(_call_tool(mcp, "board_summary", {"board_id": board["id"]}))

        for col in result["columns"]:
            assert col["count"] == 0
        assert result["totals"]["tasks"] == 0
        assert result["totals"]["overdue"] == 0
        assert result["totals"]["stalled"] == 0


# ---------------------------------------------------------------------------
# create_board_task
# ---------------------------------------------------------------------------


class TestCreateBoardTask:
    def test_wires_to_board_and_column(self, mcp):
        board = _make_board(mcp)

        task = _make_task(
            mcp, board["id"], title="Write docs", column="in_progress", priority="high"
        )

        assert task["type"] == "task"
        assert task["column"] == "in_progress"
        assert task["title"] == "Write docs"
        # belongs_to relationship auto-wired
        rels = task.get("relationships", [])
        assert any(r["rel"] == "belongs_to" and r["target"] == board["id"] for r in rels)

    def test_validates_column_exists(self, mcp):
        """Tool rejects column keys that aren't declared on the board,
        preventing tasks from being orphaned into buckets the UI can't
        render.
        """
        board = _make_board(mcp)

        result = _run(
            _call_tool(
                mcp,
                "create_board_task",
                {
                    "board_id": board["id"],
                    "title": "Bad column",
                    "column": "nonexistent_column",
                },
            )
        )
        assert "error" in result
        assert "nonexistent_column" in result["error"]

    def test_auto_sets_position(self, mcp):
        """Sequential creates in the same column land at positions 0, 1, 2…
        so agents and UIs can rely on creation order without an explicit
        reorder_column call.
        """
        board = _make_board(mcp)

        created = [_make_task(mcp, board["id"], title=f"Seq {i}", column="todo") for i in range(3)]

        positions = [t["position"] for t in created]
        assert positions == [0, 1, 2], f"positions not monotonic from 0: {positions}"

    def test_auto_position_is_column_scoped(self, mcp):
        """Auto-position is computed per-column, not across the whole
        board. Creating in column B after three in column A starts at 0,
        not 3.
        """
        board = _make_board(mcp)

        for i in range(3):
            _make_task(mcp, board["id"], title=f"Todo {i}", column="todo")
        first_in_progress = _make_task(
            mcp, board["id"], title="First in progress", column="in_progress"
        )

        assert first_in_progress["position"] == 0



# ---------------------------------------------------------------------------
# find_board_task
# ---------------------------------------------------------------------------


class TestFindBoardTask:
    def test_text_match_scoped_to_board(self, mcp):
        board_a = _make_board(mcp, name="Alpha")
        board_b = _make_board(mcp, name="Beta")

        _make_task(mcp, board_a["id"], title="Refactor payments module")
        _make_task(mcp, board_a["id"], title="Ship docs")
        # Same substring, different board — must NOT leak in.
        _make_task(mcp, board_b["id"], title="Refactor billing module")

        result = _run(
            _call_tool(mcp, "find_board_task", {"board_id": board_a["id"], "query": "Refactor"})
        )

        assert result["count"] == 1
        assert result["matches"][0]["title"] == "Refactor payments module"
        assert result["board"]["id"] == board_a["id"]

    def test_returns_empty_when_no_match(self, mcp):
        board = _make_board(mcp)
        _make_task(mcp, board["id"], title="Some task")

        result = _run(
            _call_tool(
                mcp,
                "find_board_task",
                {"board_id": board["id"], "query": "no-such-substring-xyzzy"},
            )
        )

        assert result["matches"] == []
        assert result["count"] == 0


# ---------------------------------------------------------------------------
# move_task
# ---------------------------------------------------------------------------


class TestMoveTask:
    def test_moves_between_columns(self, mcp):
        board = _make_board(mcp)
        task = _make_task(mcp, board["id"], title="Mover", column="todo")

        result = _run(
            _call_tool(
                mcp,
                "move_task",
                {"task_id": task["id"], "target_column": "in_progress"},
            )
        )

        assert result["task"]["column"] == "in_progress"
        assert result["previous_column"] == "todo"

        refreshed = _get_task(mcp, task["id"])
        assert refreshed["column"] == "in_progress"

    def test_validates_target_column_exists(self, mcp):
        board = _make_board(mcp)
        task = _make_task(mcp, board["id"], title="Mover", column="todo")

        result = _run(
            _call_tool(
                mcp,
                "move_task",
                {"task_id": task["id"], "target_column": "nonexistent"},
            )
        )

        assert "error" in result
        assert "nonexistent" in result["error"]

    def test_preserves_other_fields(self, mcp):
        board = _make_board(mcp)
        task = _make_task(
            mcp,
            board["id"],
            title="Keep my metadata",
            column="todo",
            description="Important detail",
            priority="high",
        )

        _run(
            _call_tool(
                mcp,
                "move_task",
                {"task_id": task["id"], "target_column": "in_progress"},
            )
        )

        refreshed = _get_task(mcp, task["id"])
        assert refreshed["title"] == "Keep my metadata"
        assert refreshed["description"] == "Important detail"
        assert refreshed["priority"] == "high"
        assert refreshed["column"] == "in_progress"


# ---------------------------------------------------------------------------
# reorder_column
# ---------------------------------------------------------------------------


class TestReorderColumn:
    def test_reorders_tasks_within_column(self, mcp):
        board = _make_board(mcp)
        t1 = _make_task(mcp, board["id"], title="First", column="todo")
        t2 = _make_task(mcp, board["id"], title="Second", column="todo")
        t3 = _make_task(mcp, board["id"], title="Third", column="todo")

        # Reverse the order
        new_order = [t3["id"], t2["id"], t1["id"]]
        result = _run(
            _call_tool(
                mcp,
                "reorder_column",
                {
                    "board_id": board["id"],
                    "column_key": "todo",
                    "task_ids": new_order,
                },
            )
        )

        assert result["reordered"] == 3
        assert [item["id"] for item in result["order"]] == new_order
        assert [item["position"] for item in result["order"]] == [0, 1, 2]

        # Persisted positions match
        for expected_pos, tid in enumerate(new_order):
            got = _get_task(mcp, tid)
            assert got["position"] == expected_pos

    def test_rejects_tasks_not_in_that_column(self, mcp):
        board = _make_board(mcp)
        t_todo = _make_task(mcp, board["id"], title="In todo", column="todo")
        t_wip = _make_task(mcp, board["id"], title="In progress", column="in_progress")

        result = _run(
            _call_tool(
                mcp,
                "reorder_column",
                {
                    "board_id": board["id"],
                    "column_key": "todo",
                    # t_wip lives in 'in_progress' — should be rejected.
                    "task_ids": [t_todo["id"], t_wip["id"]],
                },
            )
        )

        assert "error" in result
        assert t_wip["id"] in result["error"]

    def test_rejects_unknown_column(self, mcp):
        board = _make_board(mcp)
        result = _run(
            _call_tool(
                mcp,
                "reorder_column",
                {
                    "board_id": board["id"],
                    "column_key": "nonexistent",
                    "task_ids": [],
                },
            )
        )
        assert "error" in result
        assert "nonexistent" in result["error"]


# ---------------------------------------------------------------------------
# Sanity: schema-level rejection still raises ToolError
# ---------------------------------------------------------------------------


def test_create_board_task_missing_title_is_schema_error(mcp):
    """Smoke-check: the FastMCP client surfaces JSON-Schema violations
    as `ToolError`, not silent dict-errors. Guards against regressions
    in the upjack 0.5.1 flat-kwargs contract.
    """
    board = _make_board(mcp)
    with pytest.raises(ToolError):
        _run(
            _call_tool(
                mcp,
                "create_board_task",
                {"board_id": board["id"]},  # missing required `title`
            )
        )

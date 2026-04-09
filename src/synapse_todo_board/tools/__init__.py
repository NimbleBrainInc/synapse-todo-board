"""Custom domain tools for the Todo Board app.

Exports register_tools() which binds all tool functions to the MCP server.
"""

from synapse_todo_board.tools.batch_archive import batch_archive
from synapse_todo_board.tools.board_summary import board_summary
from synapse_todo_board.tools.create_board_task import create_board_task
from synapse_todo_board.tools.find_board_task import find_board_task
from synapse_todo_board.tools.move_task import move_task
from synapse_todo_board.tools.reorder_column import reorder_column

__all__ = ["register_tools"]


def register_tools(mcp, app):
    """Register all custom tools on the MCP server.

    Args:
        mcp: FastMCP server instance.
        app: UpjackApp instance for entity access.
    """

    @mcp.tool(
        name="create_board_task",
        description=(
            "Create a task on a specific board. ALWAYS use this instead of "
            "create_task — it auto-links the task to the board so it appears "
            "in the UI. Pass the board ID from visible state (selectedBoard.id). "
            "The column defaults to the board's default column if not specified."
        ),
    )
    def _create_board_task(
        board_id: str,
        title: str,
        description: str = "",
        column: str = "",
        priority: str = "medium",
        assignee: str = "",
        due_date: str = "",
        effort: str = "",
    ) -> dict:
        data: dict = {"title": title}
        if description:
            data["description"] = description
        if column:
            data["column"] = column
        if priority:
            data["priority"] = priority
        if assignee:
            data["assignee"] = assignee
        if due_date:
            data["due_date"] = due_date
        if effort:
            data["effort"] = effort
        return create_board_task(app, board_id, data)

    @mcp.tool(
        name="find_board_task",
        description=(
            "Find tasks on a specific board by title. ALWAYS use this instead of "
            "search_tasks when the user is viewing a board — pass the board ID from "
            "the visible state (selectedBoard.id). Only fall back to search_tasks "
            "if this returns no matches."
        ),
    )
    def _find_board_task(
        board_id: str,
        query: str,
    ) -> dict:
        return find_board_task(app, board_id, query)

    @mcp.tool(
        name="move_task",
        description=(
            "Move a task to a different column on its board. "
            "Validates the column exists, checks WIP limits (warns but doesn't block), "
            "and auto-sets completed_at when moving to done/complete/closed columns. "
            "Use instead of raw task update for column moves."
        ),
    )
    def _move_task(
        task_id: str,
        target_column: str,
        position: int | None = None,
    ) -> dict:
        return move_task(app, task_id, target_column, position)

    @mcp.tool(
        name="reorder_column",
        description=(
            "Batch-update positions of all tasks within a column after a "
            "drag-and-drop reorder. Pass task IDs in desired order; each gets "
            "position = its array index."
        ),
    )
    def _reorder_column(
        board_id: str,
        column_key: str,
        task_ids: list[str],
    ) -> dict:
        return reorder_column(app, board_id, column_key, task_ids)

    @mcp.tool(
        name="board_summary",
        description=(
            "Get an aggregate view of a board: per-column task counts, WIP status, "
            "overdue tasks, and stalled tasks (unchanged for >3 days). "
            "Read-only, no side effects."
        ),
    )
    def _board_summary(board_id: str) -> dict:
        return board_summary(app, board_id)

    @mcp.tool(
        name="batch_archive",
        description=(
            "Archive all completed tasks on a board that have been done for more "
            "than N days. Keeps boards clean by moving old finished work to archived status."
        ),
    )
    def _batch_archive(
        board_id: str,
        older_than_days: int = 7,
    ) -> dict:
        return batch_archive(app, board_id, older_than_days)

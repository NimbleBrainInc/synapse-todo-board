"""Batch-update task positions within a column after drag-and-drop reorder."""

from typing import Any

from upjack.app import UpjackApp


def reorder_column(
    app: UpjackApp,
    board_id: str,
    column_key: str,
    task_ids: list[str],
) -> dict[str, Any]:
    """Batch-update positions of all tasks within a column.

    Args:
        app: UpjackApp instance.
        board_id: ID of the board.
        column_key: Column to reorder.
        task_ids: Task IDs in desired order (index = new position).

    Returns:
        Context dict with column, board_id, reordered count, and ordered
        task list. Returns {"error": "..."} on failure.
    """
    # 1. Load board and validate column
    try:
        board = app.get_entity("board", board_id)
    except FileNotFoundError:
        return {"error": f"Board {board_id} not found"}

    columns = board.get("columns", [])
    column_keys = [c["key"] for c in columns]
    if column_key not in column_keys:
        return {"error": f"Column '{column_key}' does not exist on board {board_id}"}

    # 2. Validate each task belongs to this column, then update position
    order: list[dict[str, Any]] = []
    for idx, tid in enumerate(task_ids):
        try:
            task = app.get_entity("task", tid)
        except FileNotFoundError:
            return {"error": f"Task {tid} not found"}

        if task.get("column") != column_key:
            return {"error": f"Task {tid} is not in column '{column_key}'"}

        # Verify task belongs to this board
        belongs = any(
            r.get("rel") == "belongs_to" and r.get("target") == board_id
            for r in task.get("relationships", [])
        )
        if not belongs:
            return {"error": f"Task {tid} does not belong to board {board_id}"}

        app.update_entity("task", tid, {"position": idx})
        order.append({
            "id": tid,
            "title": task.get("title"),
            "position": idx,
        })

    return {
        "column": column_key,
        "board_id": board_id,
        "reordered": len(order),
        "order": order,
    }

"""Move a task between columns with WIP checks and completion side effects."""

from datetime import UTC, datetime
from typing import Any

from upjack.app import UpjackApp

_DONE_KEYWORDS = ("done", "complete", "closed")


def _is_done_column(key: str) -> bool:
    return any(kw in key for kw in _DONE_KEYWORDS)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def move_task(
    app: UpjackApp,
    task_id: str,
    target_column: str,
    position: int | None = None,
) -> dict[str, Any]:
    """Move a task to a different column with WIP limit checks.

    Args:
        app: UpjackApp instance.
        task_id: ID of the task to move.
        target_column: Column key to move the task to.
        position: Position within the target column (default: append to end).

    Returns:
        Context dict with task, board, previous_column, completion_set,
        wip_warning, and next_step. Returns {"error": "..."} on failure.
    """
    # 1. Load task
    try:
        task = app.get_entity("task", task_id)
    except FileNotFoundError:
        return {"error": f"Task {task_id} not found"}

    # 2. Load board via belongs_to relationship
    board_id = None
    for rel in task.get("relationships", []):
        if rel.get("rel") == "belongs_to":
            board_id = rel["target"]
            break

    if not board_id:
        return {"error": f"Task {task_id} has no board relationship"}

    try:
        board = app.get_entity("board", board_id)
    except FileNotFoundError:
        return {"error": f"Board {board_id} not found"}

    # 3. Validate target_column exists
    columns = board.get("columns", [])
    column_keys = [c["key"] for c in columns]
    if target_column not in column_keys:
        return {"error": f"Column '{target_column}' does not exist on board {board_id}"}

    # 4. Check WIP limit
    wip_warning = None
    target_col_def = next(c for c in columns if c["key"] == target_column)
    wip_limit = target_col_def.get("wip_limit", 0)

    if wip_limit and wip_limit > 0:
        # Count tasks currently in target column
        all_tasks = app.list_entities("task", status="active", limit=1000)
        count_in_column = sum(
            1
            for t in all_tasks
            if t.get("column") == target_column
            and t["id"] != task_id
            and any(
                r.get("rel") == "belongs_to" and r.get("target") == board_id
                for r in t.get("relationships", [])
            )
        )
        if count_in_column >= wip_limit:
            wip_warning = (
                f"Column '{target_column}' has {count_in_column}/{wip_limit} "
                f"tasks (WIP limit reached)"
            )

    # 5. Determine position
    previous_column = task.get("column")
    update_data: dict[str, Any] = {"column": target_column}

    if position is not None:
        update_data["position"] = position
    else:
        # Append to end: find max position in target column
        all_tasks = app.list_entities("task", status="active", limit=1000)
        positions = [
            t.get("position", 0)
            for t in all_tasks
            if t.get("column") == target_column
            and t["id"] != task_id
            and any(
                r.get("rel") == "belongs_to" and r.get("target") == board_id
                for r in t.get("relationships", [])
            )
        ]
        update_data["position"] = max(positions, default=-1) + 1

    # 6. Handle completed_at
    completion_set = False
    if _is_done_column(target_column) and not _is_done_column(previous_column or ""):
        update_data["completed_at"] = _now_iso()
        completion_set = True
    elif not _is_done_column(target_column) and _is_done_column(previous_column or ""):
        update_data["completed_at"] = None

    # 7. Apply update
    updated_task = app.update_entity("task", task_id, update_data)

    # 8. Build next_step
    if completion_set:
        next_step = "Task completed. Consider archiving if no follow-up needed."
    elif wip_warning:
        next_step = f"Task moved but WIP limit exceeded. {wip_warning}. Consider moving a task out."
    else:
        next_step = f"Task moved to '{target_column}'."

    return {
        "task": {
            "id": updated_task["id"],
            "title": updated_task.get("title"),
            "column": updated_task.get("column"),
            "position": updated_task.get("position"),
        },
        "board": {
            "id": board["id"],
            "name": board.get("name"),
        },
        "previous_column": previous_column,
        "completion_set": completion_set,
        "wip_warning": wip_warning,
        "next_step": next_step,
    }

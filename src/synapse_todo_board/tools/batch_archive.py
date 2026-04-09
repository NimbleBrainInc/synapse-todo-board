"""Archive completed tasks older than N days to keep boards clean."""

from datetime import UTC, datetime
from typing import Any

from upjack.app import UpjackApp


def _parse_datetime(value: str | None) -> datetime | None:
    """Parse an ISO datetime string, returning None on failure."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def batch_archive(
    app: UpjackApp,
    board_id: str,
    older_than_days: int = 7,
) -> dict[str, Any]:
    """Archive completed tasks on a board older than N days.

    Args:
        app: UpjackApp instance.
        board_id: ID of the board to clean.
        older_than_days: Archive tasks completed more than N days ago.

    Returns:
        Context dict with board_id, archived count, tasks list, and
        next_step. Returns {"error": "..."} on failure.
    """
    # 1. Load board
    try:
        app.get_entity("board", board_id)
    except FileNotFoundError:
        return {"error": f"Board {board_id} not found"}

    # 2. Query active tasks for this board via relationship index
    now = datetime.now(UTC)
    board_tasks = app.query_by_relationship("task", "belongs_to", board_id, limit=1000)

    to_archive: list[dict[str, Any]] = []
    for task in board_tasks:
        completed_at = _parse_datetime(task.get("completed_at"))
        if not completed_at:
            continue

        days_since = (now - completed_at).days
        if days_since >= older_than_days:
            to_archive.append(task)

    # 3. Archive each matching task
    archived_list: list[dict[str, Any]] = []
    for task in to_archive:
        app.update_entity("task", task["id"], {"status": "archived"})
        archived_list.append({
            "id": task["id"],
            "title": task.get("title"),
            "completed_at": task.get("completed_at"),
        })

    # 4. Build response
    count = len(archived_list)
    if count > 0:
        next_step = f"Archived {count} task{'s' if count != 1 else ''} completed more than {older_than_days} days ago."
    else:
        next_step = f"No completed tasks older than {older_than_days} days."

    return {
        "board_id": board_id,
        "archived": count,
        "tasks": archived_list,
        "next_step": next_step,
    }

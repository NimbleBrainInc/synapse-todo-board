"""Aggregate board metrics: column counts, WIP status, overdue/stalled tasks."""

from datetime import UTC, datetime
from typing import Any

from upjack.app import UpjackApp


def _parse_date(value: str | None) -> datetime | None:
    """Parse an ISO date or datetime string, returning None on failure."""
    if not value:
        return None
    try:
        # Try full ISO datetime first
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        pass
    try:
        # Try date-only (YYYY-MM-DD)
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError:
        return None


def board_summary(
    app: UpjackApp,
    board_id: str,
) -> dict[str, Any]:
    """Compute aggregate metrics for a board.

    Args:
        app: UpjackApp instance.
        board_id: ID of the board to summarize.

    Returns:
        Context dict with board, columns array (count, wip, overdue),
        totals, stalled_tasks, and next_step. Returns {"error": "..."} on failure.
    """
    # 1. Load board
    try:
        board = app.get_entity("board", board_id)
    except FileNotFoundError:
        return {"error": f"Board {board_id} not found"}

    # 2. Query all active tasks for this board via relationship index
    board_tasks = app.query_by_relationship("task", "belongs_to", board_id, limit=1000)

    # 3. Group by column
    now = datetime.now(UTC)
    today = now.date()
    columns_def = board.get("columns", [])
    col_lookup = {c["key"]: c for c in columns_def}

    # Initialize per-column stats
    col_stats: dict[str, dict[str, Any]] = {}
    for col in columns_def:
        col_stats[col["key"]] = {
            "key": col["key"],
            "label": col.get("label", col["key"]),
            "count": 0,
            "wip_limit": col.get("wip_limit", 0),
            "wip_ok": True,
            "overdue": 0,
        }

    stalled_tasks: list[dict[str, Any]] = []
    total_overdue = 0

    for task in board_tasks:
        col_key = task.get("column", "")
        if col_key in col_stats:
            col_stats[col_key]["count"] += 1

            # Check overdue
            due = _parse_date(task.get("due_date"))
            if due and due.date() < today and not task.get("completed_at"):
                col_stats[col_key]["overdue"] += 1
                total_overdue += 1

        # Check stalled (>3 days in same column based on updated_at)
        updated = _parse_date(task.get("updated_at"))
        if updated:
            days_since = (now - updated).days
            if days_since > 3:
                stalled_tasks.append({
                    "id": task["id"],
                    "title": task.get("title"),
                    "column": col_key,
                    "days_stalled": days_since,
                })

    # Check WIP status
    for key, stats in col_stats.items():
        wip = stats["wip_limit"]
        if wip and wip > 0 and stats["count"] > wip:
            stats["wip_ok"] = False

    # Build columns array preserving board column order
    columns_result = [col_stats[c["key"]] for c in columns_def if c["key"] in col_stats]

    total_tasks = len(board_tasks)
    total_stalled = len(stalled_tasks)

    # Build next_step
    parts = []
    if total_overdue:
        parts.append(f"{total_overdue} overdue task{'s' if total_overdue != 1 else ''}")
    if total_stalled:
        parts.append(f"{total_stalled} stalled task{'s' if total_stalled != 1 else ''}")
    wip_exceeded = [c for c in columns_result if not c["wip_ok"]]
    if wip_exceeded:
        names = ", ".join(f"'{c['label']}'" for c in wip_exceeded)
        parts.append(f"WIP exceeded in {names}")

    if parts:
        next_step = f"{'. '.join(parts)}. Consider re-prioritizing or unblocking."
    else:
        next_step = "Board looks healthy. No overdue or stalled tasks."

    return {
        "board": {
            "id": board["id"],
            "name": board.get("name"),
        },
        "columns": columns_result,
        "totals": {
            "tasks": total_tasks,
            "overdue": total_overdue,
            "stalled": total_stalled,
        },
        "stalled_tasks": stalled_tasks,
        "next_step": next_step,
    }

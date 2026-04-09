"""Find tasks on a specific board by title or query string."""

from typing import Any

from upjack.app import UpjackApp


def find_board_task(
    app: UpjackApp,
    board_id: str,
    query: str,
) -> dict[str, Any]:
    """Search for tasks on a specific board matching a query.

    Args:
        app: UpjackApp instance.
        board_id: Board to scope the search to.
        query: Case-insensitive substring to match against task titles.

    Returns:
        Dict with matched tasks or an error.
    """
    # Validate board exists
    try:
        board = app.get_entity("board", board_id)
    except FileNotFoundError:
        return {"error": f"Board {board_id} not found"}

    # Get all tasks on this board via relationship index
    board_tasks = app.query_by_relationship("task", "belongs_to", board_id)

    # Filter to active tasks matching the query
    q = query.lower()
    matches = [
        {
            "id": t["id"],
            "title": t.get("title", ""),
            "column": t.get("column", ""),
            "priority": t.get("priority", "none"),
            "assignee": t.get("assignee"),
            "due_date": t.get("due_date"),
        }
        for t in board_tasks
        if t.get("status", "active") == "active"
        and q in t.get("title", "").lower()
    ]

    return {
        "board": {"id": board["id"], "name": board.get("name")},
        "matches": matches,
        "count": len(matches),
    }

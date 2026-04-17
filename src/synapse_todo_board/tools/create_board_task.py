"""Create a task on a specific board with the relationship auto-wired."""

from typing import Any

from upjack.app import UpjackApp


def create_board_task(
    app: UpjackApp,
    board_id: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    """Create a task and automatically link it to the given board.

    Validates that ``column`` names a real column on the board and auto-sets
    ``position`` to the end of that column so sequentially created tasks
    appear in creation order without a follow-up ``reorder_column`` call.

    Args:
        app: UpjackApp instance.
        board_id: Board to create the task on.
        data: Task fields (title, column, priority, etc.). ``column`` is
            optional and defaults to the board's ``default_column`` or first
            declared column. ``position`` is optional; if omitted, it's set
            to ``max(existing_in_column) + 1`` (0 if empty).

    Returns:
        The created task entity, or an error dict if the board is missing
        or the requested column isn't defined on the board.
    """
    # Validate board exists
    try:
        board = app.get_entity("board", board_id)
    except FileNotFoundError:
        return {"error": f"Board {board_id} not found"}

    columns = board.get("columns", []) or []
    valid_column_keys = [c.get("key") for c in columns if c.get("key")]

    # Resolve column — caller-provided, or board default, or first column
    column = (
        data.get("column")
        or board.get("default_column")
        or (valid_column_keys[0] if valid_column_keys else None)
    )
    if column is None:
        return {"error": f"Board {board_id} has no columns defined"}
    data["column"] = column

    # Validate column exists on the board. Preventing regex-valid but
    # undefined columns avoids silently orphaning tasks into buckets the
    # UI never renders.
    if column not in valid_column_keys:
        return {
            "error": (
                f"Column '{column}' is not defined on board {board_id}. "
                f"Valid columns: {valid_column_keys}"
            )
        }

    # Auto-set position if caller didn't specify one. We query the board's
    # tasks via the reverse index and take max(existing_in_column) + 1 so
    # tasks land at the end of the column in creation order.
    if "position" not in data:
        existing = app.query_by_relationship("task", "belongs_to", board_id)
        positions = [
            t.get("position")
            for t in existing
            if t.get("column") == column and isinstance(t.get("position"), int)
        ]
        data["position"] = (max(positions) + 1) if positions else 0

    # Auto-wire the belongs_to relationship
    data["relationships"] = [{"rel": "belongs_to", "target": board_id}]

    task = app.create_entity("task", data)
    return task

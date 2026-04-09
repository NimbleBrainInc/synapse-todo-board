"""Create a task on a specific board with the relationship auto-wired."""

from typing import Any

from upjack.app import UpjackApp


def create_board_task(
    app: UpjackApp,
    board_id: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    """Create a task and automatically link it to the given board.

    Args:
        app: UpjackApp instance.
        board_id: Board to create the task on.
        data: Task fields (title, column, priority, etc.).

    Returns:
        The created task entity, or an error dict.
    """
    # Validate board exists
    try:
        board = app.get_entity("board", board_id)
    except FileNotFoundError:
        return {"error": f"Board {board_id} not found"}

    # Default column to board's default or first column
    if "column" not in data:
        data["column"] = board.get("default_column") or board.get("columns", [{}])[0].get("key", "todo")

    # Auto-wire the belongs_to relationship
    data["relationships"] = [{"rel": "belongs_to", "target": board_id}]

    task = app.create_entity("task", data)
    return task

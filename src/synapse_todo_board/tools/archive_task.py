"""Archive a single task by flipping its status to 'archived'."""

from typing import Any

from synapse_todo_board.store import BoardStore


def archive_task(app: BoardStore, task_id: str) -> dict[str, Any]:
    """Flip a task's status to 'archived' so it's filtered out of active views.

    The task schema's `status` lives on the Upjack base entity (not the
    task-specific schema), so the auto-generated `update_task` tool can't
    write it — its inputSchema only exposes task-specific fields. This
    custom tool writes the status directly via `app.update_entity`, the
    same path `batch_archive` uses.

    Args:
        app: BoardStore instance.
        task_id: Task to archive.

    Returns:
        The updated task entity, or an error dict if the task is missing.
    """
    try:
        app.get_entity("task", task_id)
    except FileNotFoundError:
        return {"error": f"Task {task_id} not found"}

    return app.update_entity("task", task_id, {"status": "archived"})

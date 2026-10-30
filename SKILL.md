# Todo Board — Tool Usage Guide

## Board Context

The UI pushes visible state with the active board (`selectedBoard.id`, `selectedBoard.name`, `selectedBoard.columns`). Always use this context — never ask the user which board they mean when one is selected.

## Tool Selection

### Creating tasks

Use `create_board_task(board_id, title, ...)` with flat arguments. The board-specific tool
links the task with a `belongs_to` relationship so it appears in the UI. A raw `create_task`
tool is deliberately not exposed.

### Finding tasks

Use `find_board_task(board_id, query)` when the user references a task by name on the current board. Only fall back to `search_tasks` if `find_board_task` returns no matches.

### Moving tasks between columns

Use `move_task(task_id, target_column)` — never raw `update_task` for column changes. `move_task` validates the column exists, checks WIP limits, and auto-sets `completed_at` when moving to done/complete/closed columns.

### Reordering within a column

Use `reorder_column(board_id, column_key, task_ids)` with task IDs in the desired order. Each task gets `position` set to its array index.
The server validates every target before changing positions; a task on another board or column
rejects the request without changing an earlier task.

### Board overview

Use `board_summary(board_id)` for aggregate stats: per-column counts, WIP status, overdue and stalled tasks. Good for daily standups or when the user asks "how's the board looking?"

### Bulk cleanup

Use `batch_archive(board_id, older_than_days)` to archive completed tasks older than N days (default 7). Keeps done columns clean.

## Data and refresh

Tools and the UI share one workspace. Successful writes notify the connected client so open
Synapse views refresh; read-only calls do not emit change notifications. List/query tools use
an `entities` envelope. Pass `limit: null` when the complete list is needed.

Use `add_field` for a requested schema extension with a valid default. Definitions are saved
in workspace overrides, without editing app source. `delete_board` and `delete_task` preserve
records by default; `hard: true` permanently removes the selected record. Do not substitute a
hard delete for archive or ordinary deletion.

This skill does not install hooks or schedules. Follow task-triage guidance when the person
requests triage; automatic review needs an explicitly configured host workflow. Source-schema
migration is an operator command documented in MIGRATION.md, not an agent tool.

## Common Patterns

**"Move X to done"** → `find_board_task` to get the ID, then `move_task` to the done column.

**"Add a task to do Y"** → `create_board_task` with the selected board ID, column defaults to the board's `default_column`.

**"What's overdue?"** → `board_summary` shows overdue tasks with their due dates.

**"Clean up the done column"** → `batch_archive` with the board ID.

## Column Keys

Column keys are lowercase with underscores (e.g., `todo`, `in_progress`, `review`, `done`). Use the keys from `selectedBoard.columns` in the visible state — never guess column names.

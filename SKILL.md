# Todo Board — Tool Usage Guide

## Board Context

The UI pushes visible state with the active board (`selectedBoard.id`, `selectedBoard.name`, `selectedBoard.columns`). Always use this context — never ask the user which board they mean when one is selected.

## Tool Selection

### Creating tasks

Use `create_board_task(board_id, data)` — never `create_task`. The board-specific tool auto-links the task via a `belongs_to` relationship so it appears in the UI. Bare `create_task` creates an orphan that's invisible on any board.

### Finding tasks

Use `find_board_task(board_id, query)` when the user references a task by name on the current board. Only fall back to `search_tasks` if `find_board_task` returns no matches.

### Moving tasks between columns

Use `move_task(task_id, target_column)` — never raw `update_task` for column changes. `move_task` validates the column exists, checks WIP limits, and auto-sets `completed_at` when moving to done/complete/closed columns.

### Reordering within a column

Use `reorder_column(board_id, column_key, task_ids)` with task IDs in the desired order. Each task gets `position` set to its array index.

### Board overview

Use `board_summary(board_id)` for aggregate stats: per-column counts, WIP status, overdue and stalled tasks. Good for daily standups or when the user asks "how's the board looking?"

### Bulk cleanup

Use `batch_archive(board_id, older_than_days)` to archive completed tasks older than N days (default 7). Keeps done columns clean.

## Common Patterns

**"Move X to done"** → `find_board_task` to get the ID, then `move_task` to the done column.

**"Add a task to do Y"** → `create_board_task` with the selected board ID, column defaults to the board's `default_column`.

**"What's overdue?"** → `board_summary` shows overdue tasks with their due dates.

**"Clean up the done column"** → `batch_archive` with the board ID.

## Column Keys

Column keys are lowercase with underscores (e.g., `todo`, `in_progress`, `review`, `done`). Use the keys from `selectedBoard.columns` in the visible state — never guess column names.

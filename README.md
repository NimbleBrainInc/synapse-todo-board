# Todo Board

[![mpak](https://img.shields.io/badge/mpak-registry-blue)](https://mpak.dev/packages/@nimblebraininc/synapse-todo-board?utm_source=github&utm_medium=readme&utm_campaign=synapse-todo-board)
[![NimbleBrain](https://img.shields.io/badge/NimbleBrain-nimblebrain.ai-purple)](https://nimblebrain.ai?utm_source=github&utm_medium=readme&utm_campaign=synapse-todo-board)
[![Discord](https://img.shields.io/badge/Discord-community-5865F2)](https://nimblebrain.ai/discord?utm_source=github&utm_medium=readme&utm_campaign=synapse-todo-board)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Kanban-style task manager with table and drag-and-drop board views, built on FastMCP.

**[View on mpak registry](https://mpak.dev/packages/@nimblebraininc/synapse-todo-board?utm_source=github&utm_medium=readme&utm_campaign=synapse-todo-board)** | **Built by [NimbleBrain](https://nimblebrain.ai?utm_source=github&utm_medium=readme&utm_campaign=synapse-todo-board)**

## Entities

| Entity | Prefix | Description |
|--------|--------|-------------|
| Board  | `bd`   | Named workspace that groups tasks and defines status columns for its Kanban view |
| Task   | `tk`   | Unit of work that lives on a board and moves through its columns |

## Custom Tools

CRUD tools (create, get, update, list, search, delete) are generated from the entity schemas by `entity_tools.py` and read and write through `BoardStore`. These domain-specific tools handle operations requiring multi-entity reads or business logic.

| Tool | Description | Inputs |
|------|-------------|--------|
| `move_task` | Move a task to a different column, enforcing WIP limits and triggering completion side effects | `task_id` (string, required), `target_column` (string, required), `position` (integer, optional) |
| `reorder_column` | Batch-update positions of all tasks within a column after drag-and-drop reorder | `board_id` (string, required), `column_key` (string, required), `task_ids` (array of strings, required) |
| `board_summary` | Aggregate view of a board: column counts, WIP status, overdue tasks, stalled tasks | `board_id` (string, required) |
| `batch_archive` | Archive all completed tasks on a board older than N days | `board_id` (string, required), `older_than_days` (integer, optional — default 7) |

## Skill: Task Triage

Automatically classifies, prioritizes, and organizes tasks so the user spends time doing work, not managing it.

**Triggers:**

- **New task created** (hook) — analyzes title/description, suggests priority and due date
- **Task column changed** (hook) — reacts to moves (e.g., sets `completed_at` when moved to a done-like column)
- **Daily review** (schedule: weekdays at 9am) — flags overdue tasks, stalled tasks, and WIP limit breaches

## Skills over MCP

The server serves its skills through the SEP-2640 skills extension (`io.modelcontextprotocol/skills`). `skills/list` lists each folder under `skills/`, and `skills/get` and `resources/read` serve it at `skill://<folder>/SKILL.md`. Both methods answer on 2026-07-28, the era NimbleBrain connects on, and on the older 2025-11-25 handshake era as well.

| Skill | URI |
|-------|-----|
| `task-triage` | `skill://task-triage/SKILL.md` |
| `todo-board-usage` | `skill://todo-board-usage/SKILL.md` |

The tool guide that was the root `SKILL.md` is now the `todo-board-usage` skill. `skill://todo-board/usage` still reads the same file, and `upjack://skills/task-triage` still answers.

## UI Overview

The Synapse UI provides two views, toggled via a tab bar, operating on one board at a time with a board selector in the header.

### Board View (Kanban)

Horizontal scrollable lanes, one per board column. Task cards show title, priority badge, assignee, and due date. Drag-and-drop between columns updates task `column` and `position`. Column headers display task count and WIP limit indicators. A "+" button at the bottom of each column creates a new task.

### Table View

Sortable, filterable data table with columns for title, priority, status column, assignee, due date, effort, and created date. Supports inline cell editing, column header sorting, a filter bar (priority, column, assignee, overdue), and multi-row bulk actions (change column, set priority, archive).

## File Structure

```
mcp-servers/todo-board/
├── manifest.json
├── SPEC.md
├── README.md
├── pyproject.toml
├── server.py
├── context.md
├── schemas/
│   ├── board.schema.json
│   └── task.schema.json
├── skills/
│   ├── task-triage/
│   │   └── SKILL.md
│   └── todo-board-usage/
│       └── SKILL.md
├── tools/
│   ├── move_task.py
│   ├── reorder_column.py
│   ├── board_summary.py
│   └── batch_archive.py
├── seed/
│   ├── sample-boards.json
│   └── sample-tasks.json
└── ui/
    ├── package.json
    ├── tsconfig.json
    ├── index.html
    └── src/
        ├── index.tsx
        ├── App.tsx
        ├── views/
        │   ├── BoardView.tsx
        │   └── TableView.tsx
        ├── components/
        │   ├── TaskCard.tsx
        │   ├── Column.tsx
        │   ├── TaskDetail.tsx
        │   ├── BoardSelector.tsx
        │   └── FilterBar.tsx
        └── hooks/
            ├── useSynapse.ts
            ├── useTasks.ts
            └── useBoards.ts
```

## Run Instructions

Install dependencies:

```bash
uv sync
```

Run the server in stdio mode (for mpak / Claude Desktop):

```bash
uv run python server.py
```

Run the server in HTTP mode (for cloud deployment):

```bash
uvicorn server:app
```

Build the Synapse UI:

```bash
cd ui && npm install && npm run build
```

## Seed Data

The `seed/` directory contains sample data (2 boards, 8 tasks) loaded automatically via `run_on_install`. Boards include "Sprint 14" (4-column workflow) and "Personal" (3-column workflow), with tasks spread across columns at various priorities and due dates.

## Custom field storage

`add_field` stores declarations in `apps/todo-board/schemas/<kind>.fields.json`
under the workspace root. Each file contains `{"version": 1, "fields": {...}}`;
fields carry their type, default, required flag and optional description. Bundled
`schemas/*.schema.json` stay unchanged. Missing values take the field default in
memory, and existing record values and metadata are retained. The generated CRUD
tool argument schemas include new fields after the server restarts.

Malformed declarations or a name that collides with a bundled or base field stop
schema loading; neither side silently overrides the other. To recover, remove or
rename the entry in `apps/todo-board/schemas/<kind>.fields.json` and restart. Record
values stay as they are. Field additions hold an exclusive lock on
`<kind>.fields.lock` in the same workspace directory, so two server processes
sharing one workspace cannot both rewrite the declarations. A competing writer gets an
error and may retry after the first call finishes. The operating system releases
the lock when its process exits, so a crashed writer leaves nothing to remove.

Customizations already present in bundled schema files remain readable in place.
This does not migrate them: retain the customized installation and a recoverable
copy before replacing it, then explicitly reconcile its field definitions with
the replacement package and workspace declarations. Do not replace a customized
package until that migration is complete.

# Todo Board — Architecture Spec

> Kanban-style task manager with table and drag-and-drop board views.

## Overview

Todo Board is an AI-native task management app built on Upjack. Users organize work across boards with customizable status columns. The app ships with two Synapse UI views: a **table view** for bulk filtering, sorting, and editing, and a **Kanban board view** with drag-and-drop between status lanes.

The agent assists by triaging new tasks (suggesting priority and due dates), flagging overdue work, and running daily reviews. Boards define their own column sets so users can model any workflow — a simple "To Do / In Progress / Done" or a more granular pipeline.

The key differentiator from the basic `examples/todo` is the board entity, column-aware status management, and rich Synapse UI with dual views.

## Technology

- **Framework**: Upjack (declarative AI-native app framework)
- **Bundle format**: MCPB v0.4
- **Server runtime**: Python 3.13 — `upjack[mcp]` (FastMCP 3) via `create_server()`
- **UI**: Synapse SDK (React + `@nimblebrain/synapse`)
- **Location**: `mcp-servers/todo-board/`

## Domain Model

### Entities

#### Board (`bd`)

A named workspace that groups tasks and defines the set of status columns available for its Kanban view.

**Properties:**

| Property | Type | Constraints | Description |
|----------|------|-------------|-------------|
| `name` | string | maxLength: 128, **required** | Board name (e.g., "Sprint 12", "Personal") |
| `description` | string | — | What this board is for |
| `columns` | array | items: object, minItems: 1, **required** | Ordered list of status columns |
| `columns[].key` | string | pattern: `^[a-z][a-z0-9_]*$` | Machine-readable column identifier |
| `columns[].label` | string | maxLength: 64 | Display label (e.g., "In Progress") |
| `columns[].color` | string | pattern: `^#[0-9a-fA-F]{6}$` | Column accent color (hex) |
| `columns[].wip_limit` | integer | minimum: 0 | Max tasks allowed in this column (0 = unlimited) |
| `default_column` | string | — | Key of the column new tasks land in (defaults to first column) |

**Lifecycle:** `active → archived`

---

#### Task (`tk`)

A unit of work that lives on a board and moves through its columns.

**Properties:**

| Property | Type | Constraints | Description |
|----------|------|-------------|-------------|
| `title` | string | maxLength: 256, **required** | Short, actionable summary (start with a verb) |
| `description` | string | — | Detailed notes, acceptance criteria, context |
| `priority` | string | enum: `critical`, `high`, `medium`, `low`, `none` | Priority level; default `none` |
| `column` | string | pattern: `^[a-z][a-z0-9_]*$`, **required** | Current column key on the board |
| `position` | integer | minimum: 0 | Sort order within the column (lower = higher) |
| `due_date` | string | format: date | Target completion date |
| `completed_at` | string | format: date-time | When the task was marked done |
| `assignee` | string | maxLength: 128 | Who owns this task |
| `effort` | string | enum: `trivial`, `small`, `medium`, `large`, `epic` | Estimated effort |
| `board_name` | string | — | Denormalized board name for quick display |

**Relationships:**
- `belongs_to` → board (every task lives on exactly one board)

**Lifecycle:** `active → archived` (status tracks entity lifecycle; `column` tracks workflow position)

---

### Entity Relationship Diagram

```
[Board] 1──∞ [Task]
```

### Relationship Summary

| Source | Rel | Target | Cardinality | Description |
|--------|-----|--------|-------------|-------------|
| task | belongs_to | board | N:1 | Task lives on a board and moves through its columns |

## Skills

### Task Triage

**Purpose:** Automatically classify, prioritize, and organize tasks so the user spends time doing work, not managing it.

**Triggers:**
- `entity.created` on task (→ hook): triage new tasks
- `entity.updated` on task when `$.column` changed (→ hook): react to column moves (e.g., auto-set `completed_at` when moved to a "done" column)
- `0 9 * * 1-5` schedule: daily review of all active tasks

**Process:**

1. **Auto-prioritize new tasks**: Analyze the title and description. Assign a priority if the user left it as `none`.
   - Mention of deadlines, blockers, or urgency → `high` or `critical`
   - Routine or exploratory work → `medium` or `low`
   - If unsure, leave as `none` and ask the user

2. **Suggest due dates**: If `due_date` is empty, infer a reasonable one based on effort and priority.
   - `critical` + `trivial`/`small` → today or tomorrow
   - `high` + `medium` → within 3 days
   - Otherwise → within 1 week
   - Never silently set a due date — suggest it and let the user confirm

3. **Column-move side effects**: When a task moves to a column whose key contains `done`, `complete`, or `closed`:
   - Set `completed_at` to now
   - Archive the task (status → `archived`) if the board has an archive policy

4. **Daily review** (schedule):
   - Flag tasks where `due_date` < today and `completed_at` is null
   - Identify tasks stuck in the same column for >3 days
   - Suggest re-prioritization if the column's WIP limit is exceeded

**Decision Criteria:**

| Signal | Action |
|--------|--------|
| New task, priority = none | Analyze and suggest priority |
| New task, no due_date | Suggest due date based on effort/priority |
| Task moved to done-like column | Set completed_at, consider archiving |
| Task overdue (due_date < today) | Flag in daily review |
| Column exceeds wip_limit | Warn user, suggest moving or deferring tasks |
| Task unchanged for >3 days | Flag as potentially stalled |

**Rules:**
- Never delete tasks — archive them
- Never change priority without telling the user why
- Keep task titles actionable (verb-first)
- Respect WIP limits — warn, don't silently block

## Custom Tools

CRUD tools (create, get, update, list, search, delete per entity) are auto-generated by Upjack. These domain-specific tools handle operations that require multi-entity reads, business logic, or computed results.

### `move_task`

**Purpose:** Move a task to a different column (and optionally reposition within it), enforcing WIP limits and triggering completion side effects. A single CRUD update can't validate WIP limits or auto-set `completed_at`.

**When to use:** User drags a card on the board, or asks the agent to move a task. The UI calls this instead of raw task update.

**Input:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task_id` | string | yes | ID of the task to move |
| `target_column` | string | yes | Column key to move the task to |
| `position` | integer | no | Position within the target column (default: append to end) |

**Logic:**
1. Load the task by ID
2. Load the board via the task's `belongs_to` relationship
3. Validate `target_column` exists in `board.columns`
4. Count tasks currently in `target_column`; if `wip_limit > 0` and count >= `wip_limit`, return warning (don't block — the agent decides)
5. Update task: set `column` to `target_column`, set `position`
6. If `target_column` key contains `done`, `complete`, or `closed`: set `completed_at` to now
7. If moving *out* of a done-like column: clear `completed_at`
8. Return the updated task + board context

**Output:**
```json
{
  "task": { "id": "tk_...", "title": "...", "column": "done", "position": 0 },
  "board": { "id": "bd_...", "name": "Sprint 14" },
  "previous_column": "in_progress",
  "completion_set": true,
  "wip_warning": null,
  "next_step": "Task completed. Consider archiving if no follow-up needed."
}
```

**Entities touched:** reads board, reads + writes task
**Side effects:** updates task `column`, `position`, optionally `completed_at`
**Error cases:**
- Task not found → `{"error": "Task tk_... not found"}`
- Invalid column key → `{"error": "Column 'xyz' does not exist on board bd_..."}`
- WIP exceeded → returns success with `wip_warning`: `"Column 'in_progress' has 5/5 tasks (WIP limit reached)"`

---

### `reorder_column`

**Purpose:** Batch-update positions of all tasks within a column after a drag-and-drop reorder. Doing N individual updates is wasteful and risks inconsistent ordering.

**When to use:** User reorders a card within the same column (vertical drag), or agent re-prioritizes a column.

**Input:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `board_id` | string | yes | ID of the board |
| `column_key` | string | yes | Column to reorder |
| `task_ids` | array[string] | yes | Task IDs in desired order (index = new position) |

**Logic:**
1. Load the board, validate `column_key` exists
2. For each task_id in `task_ids`, set `position` to its array index
3. Return the updated ordering

**Output:**
```json
{
  "column": "in_progress",
  "board_id": "bd_...",
  "reordered": 3,
  "order": [
    { "id": "tk_...", "title": "Fix login bug", "position": 0 },
    { "id": "tk_...", "title": "Write tests", "position": 1 },
    { "id": "tk_...", "title": "Update docs", "position": 2 }
  ]
}
```

**Entities touched:** reads board, reads + writes tasks (batch)
**Side effects:** updates `position` on each task
**Error cases:**
- Board not found → `{"error": "Board bd_... not found"}`
- Task not in column → `{"error": "Task tk_... is not in column 'in_progress'"}`

---

### `board_summary`

**Purpose:** Aggregate view of a board's state — column counts, WIP status, overdue tasks, stalled tasks. The daily review skill and the UI header both need this computed view, and it requires reading all tasks for a board.

**When to use:** Agent daily review, user asks "how's the board looking?", or UI renders board header stats.

**Input:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `board_id` | string | yes | ID of the board to summarize |

**Logic:**
1. Load the board
2. Query all active tasks with `belongs_to` → `board_id`
3. Group tasks by `column`; for each column, compute count, WIP status, overdue count
4. Identify stalled tasks (same column for >3 days based on `updated_at`)
5. Compute overall stats: total tasks, total overdue, total stalled

**Output:**
```json
{
  "board": { "id": "bd_...", "name": "Sprint 14" },
  "columns": [
    { "key": "backlog", "label": "Backlog", "count": 2, "wip_limit": 0, "wip_ok": true, "overdue": 0 },
    { "key": "in_progress", "label": "In Progress", "count": 3, "wip_limit": 3, "wip_ok": true, "overdue": 1 },
    { "key": "review", "label": "Review", "count": 1, "wip_limit": 2, "wip_ok": true, "overdue": 0 },
    { "key": "done", "label": "Done", "count": 4, "wip_limit": 0, "wip_ok": true, "overdue": 0 }
  ],
  "totals": { "tasks": 10, "overdue": 1, "stalled": 2 },
  "stalled_tasks": [
    { "id": "tk_...", "title": "Update API docs", "column": "in_progress", "days_stalled": 5 }
  ],
  "next_step": "1 overdue task in 'In Progress' and 2 stalled tasks. Consider re-prioritizing or unblocking."
}
```

**Entities touched:** reads board, reads tasks (query)
**Side effects:** none (read-only)
**Error cases:**
- Board not found → `{"error": "Board bd_... not found"}`

---

### `batch_archive`

**Purpose:** Archive all completed tasks on a board that have been in a done-like column for more than N days. Individual archiving is tedious; this keeps boards clean.

**When to use:** User asks to "clean up the board", or as part of a weekly maintenance routine.

**Input:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `board_id` | string | yes | ID of the board to clean |
| `older_than_days` | integer | no | Archive tasks completed more than N days ago (default: 7) |

**Logic:**
1. Load the board
2. Query tasks with `belongs_to` → `board_id` where `completed_at` is set and older than `older_than_days`
3. Set `status` → `archived` on each matching task
4. Return count and list of archived tasks

**Output:**
```json
{
  "board_id": "bd_...",
  "archived": 3,
  "tasks": [
    { "id": "tk_...", "title": "Fix header styling", "completed_at": "2026-03-20T14:30:00Z" },
    { "id": "tk_...", "title": "Deploy v2.1", "completed_at": "2026-03-18T09:15:00Z" }
  ],
  "next_step": "Archived 3 tasks completed more than 7 days ago."
}
```

**Entities touched:** reads board, reads + writes tasks (batch)
**Side effects:** sets `status: archived` on matching tasks
**Error cases:**
- Board not found → `{"error": "Board bd_... not found"}`
- No tasks to archive → `{"archived": 0, "tasks": [], "next_step": "No completed tasks older than 7 days."}`

### Tool Summary

| Tool | Category | Description |
|------|----------|-------------|
| `move_task` | Workflow | Move task between columns with WIP checks and completion side effects |
| `reorder_column` | Bulk operation | Batch-update task positions within a column |
| `board_summary` | Aggregation | Compute column counts, WIP status, overdue/stalled metrics |
| `batch_archive` | Bulk operation | Archive old completed tasks to keep boards clean |

## Reactive Behaviors

### Hooks

| Event | Entity | Condition | Skill | Description |
|-------|--------|-----------|-------|-------------|
| entity.created | task | — | bundled:task-triage | Triage new tasks (priority, due date) |
| entity.updated | task | $.column changed | bundled:task-triage | React to column moves (completion, archival) |

### Schedules

| Name | Cron | Skill | Description |
|------|------|-------|-------------|
| daily-review | 0 9 * * 1-5 | bundled:task-triage | Weekday morning review: overdue, stalled, WIP |

### Views

| Name | Entity | Filter | Sort | Description |
|------|--------|--------|------|-------------|
| all-tasks | task | $.status == 'active' | -priority, position | All active tasks by priority |
| overdue | task | $.status == 'active' AND $.due_date < today | due_date | Overdue tasks, oldest first |
| my-tasks | task | $.status == 'active' AND $.assignee != null | -priority | Assigned tasks by priority |
| board-tasks | task | $.status == 'active' AND $.relationships[rel=belongs_to].target == {board_id} | position | Tasks for a specific board, ordered by position |

## UI Requirements

The Synapse UI provides two views that the user can toggle between. Both views operate on a single board at a time, with a board selector in the header.

### Primary View: Kanban Board

A Trello-style drag-and-drop board where each column maps to a board column definition.

- **Layout**: Horizontal scrollable lanes, one per column from `board.columns`
- **Cards**: Each task renders as a card showing title, priority badge, assignee avatar/initials, and due date
- **Drag and drop**: Cards can be dragged between columns. On drop, update the task's `column` and `position` fields via Upjack CRUD tools
- **Column headers**: Show column label, task count, and WIP limit indicator (yellow when at limit, red when exceeded)
- **New task**: "+" button at the bottom of each column creates a task in that column
- **Card click**: Expands an inline detail panel (or modal) for editing all task fields

### Secondary View: Table

A sortable, filterable data table for power users who need to scan and bulk-edit.

- **Columns**: Title, Priority, Column (status), Assignee, Due Date, Effort, Created
- **Sorting**: Click column headers to sort
- **Filtering**: Filter bar for priority, column, assignee, and overdue status
- **Inline editing**: Click a cell to edit priority, assignee, or column directly
- **Bulk actions**: Select multiple rows → change column, set priority, archive

### Shared UI Behavior

- **Board selector**: Dropdown in the top bar to switch boards. Shows board name + task count
- **View toggle**: Tab bar or icon toggle to switch between Board and Table views
- **Theme**: Respect host light/dark theme via Synapse theme negotiation
- **Refresh**: Re-fetch data on entity change notifications from Synapse subscriptions
- **Empty state**: Helpful prompt to create a first board or add tasks

### Agent Interaction

The user interacts with the agent through the NimbleBrain chat interface (not through the Synapse UI directly). The UI is a read/write view of the data. The agent can be asked to:
- "Create a board for sprint planning with columns: backlog, in progress, review, done"
- "Move all overdue tasks to the top of their columns"
- "What's blocking progress this week?"

## Seed Data

Realistic sample data demonstrating a working board with tasks across columns.

| Entity | Count | Variety |
|--------|-------|---------|
| board | 2 | "Sprint 14" (4 columns: backlog, in_progress, review, done) and "Personal" (3 columns: todo, doing, done) |
| task | 8 | 2 in backlog, 2 in in_progress, 1 in review, 1 in done, 2 on Personal board. Mix of priorities, some with due dates, some overdue, some with assignees |

## File Structure

```
mcp-servers/todo-board/
├── manifest.json
├── SPEC.md                          ← this file
├── README.md
├── pyproject.toml
├── schemas/
│   ├── board.schema.json
│   └── task.schema.json
├── skills/
│   └── task-triage/
│       └── SKILL.md
├── context.md
├── tools/
│   ├── move_task.py                 ← move task between columns with WIP checks
│   ├── reorder_column.py            ← batch reposition tasks in a column
│   ├── board_summary.py             ← aggregate board metrics
│   └── batch_archive.py             ← archive old completed tasks
├── seed/
│   ├── sample-boards.json
│   └── sample-tasks.json
├── ui/
│   ├── package.json
│   ├── tsconfig.json
│   ├── src/
│   │   ├── App.tsx                  ← root: board selector + view toggle
│   │   ├── views/
│   │   │   ├── BoardView.tsx        ← Kanban drag-and-drop
│   │   │   └── TableView.tsx        ← sortable/filterable table
│   │   ├── components/
│   │   │   ├── TaskCard.tsx          ← card for board view
│   │   │   ├── Column.tsx            ← single Kanban column
│   │   │   ├── TaskDetail.tsx        ← edit modal/panel
│   │   │   ├── BoardSelector.tsx     ← board dropdown
│   │   │   └── FilterBar.tsx         ← table filter controls
│   │   ├── hooks/
│   │   │   ├── useSynapse.ts         ← Synapse SDK wrapper
│   │   │   ├── useTasks.ts           ← task CRUD + subscriptions
│   │   │   └── useBoards.ts          ← board CRUD + subscriptions
│   │   └── index.tsx                 ← entry point
│   └── index.html
└── server.py                        ← FastMCP server entry point
```

## Components (for /implement)

### Component 1: Project Scaffold
**Files:** `pyproject.toml`
**Description:** Initialize the project with Python 3.13 and uv. Dependencies: `upjack[mcp]>=0.1.0`. Build system: hatchling.
**Depends on:** nothing

### Component 2: Entity Schemas
**Files:** `schemas/board.schema.json`, `schemas/task.schema.json`
**Description:** JSON Schema draft 2020-12 for each entity. `allOf` composition with `https://upjack.dev/schemas/v1/upjack-entity.schema.json`. Properties as defined in Domain Model above.
**Depends on:** nothing

### Component 3: Manifest
**Files:** `manifest.json`
**Description:** MCPB v0.4 manifest with `_meta["ai.nimblebrain/upjack"]` extension. Server type `python`, entry point `server`, mcp_config command `python` with args `["server.py"]`. Wire entities (board: `bd`, task: `tk`), skill (task-triage), hooks, schedules, views, context, and seed config.
**Depends on:** Component 2

### Component 4: Skill — Task Triage
**Files:** `skills/task-triage/SKILL.md`
**Description:** Natural-language skill document covering auto-prioritization, due date suggestion, column-move effects, and daily review process. Content as defined in Skills section.
**Depends on:** nothing

### Component 5: Context
**Files:** `context.md`
**Description:** Domain knowledge: entity relationships (tasks belong to boards), column-based workflow, task lifecycle, prioritization model, and querying patterns.
**Depends on:** nothing

### Component 6: Seed Data
**Files:** `seed/sample-boards.json`, `seed/sample-tasks.json`
**Description:** 2 boards + 8 tasks. Boards define their columns. Tasks span columns with varied priorities and due dates. No `id`, `created_at`, `updated_at`. `version: 1`, `tags: ["sample"]`.
**Depends on:** Component 2

### Component 7: Custom Tools
**Files:** `tools/move_task.py`, `tools/reorder_column.py`, `tools/board_summary.py`, `tools/batch_archive.py`
**Description:** Domain-specific tool handlers as defined in the Custom Tools section. Each tool is a function decorated with `@mcp.tool()` that uses the Upjack app instance for entity access and returns a context dict.
**Depends on:** Component 2 (entity schemas define what can be queried)

### Component 8: Server Entry Point
**Files:** `server.py`
**Description:** Python MCP server using `create_server()` from `upjack.server`. Reads manifest, creates FastMCP instance, imports and registers custom tools from `tools/`, exposes `app = mcp.http_app()` for uvicorn and `if __name__ == "__main__": mcp.run()` for stdio.
**Depends on:** Components 3, 7 (manifest + custom tool handlers)

### Component 9: Synapse UI — Scaffold
**Files:** `ui/package.json`, `ui/tsconfig.json`, `ui/index.html`, `ui/src/index.tsx`, `ui/src/App.tsx`
**Description:** React app scaffold with Synapse SDK integration. Board selector + view toggle (Board/Table). Dependencies: `react`, `react-dom`, `@nimblebrain/synapse`.
**Depends on:** nothing

### Component 9: Synapse UI — Board View
**Files:** `ui/src/views/BoardView.tsx`, `ui/src/components/Column.tsx`, `ui/src/components/TaskCard.tsx`
**Description:** Kanban board with horizontal columns. Cards show title, priority, assignee, due date. Drag-and-drop between columns updates task `column` and `position` via Synapse tool calls.
**Depends on:** Component 9

### Component 11: Synapse UI — Table View
**Files:** `ui/src/views/TableView.tsx`, `ui/src/components/FilterBar.tsx`
**Description:** Data table with sortable columns, filter bar (priority, column, assignee, overdue), inline cell editing, and multi-row bulk actions.
**Depends on:** Component 8

### Component 12: Synapse UI — Shared Components
**Files:** `ui/src/components/TaskDetail.tsx`, `ui/src/components/BoardSelector.tsx`, `ui/src/hooks/useSynapse.ts`, `ui/src/hooks/useTasks.ts`, `ui/src/hooks/useBoards.ts`
**Description:** Task detail panel/modal for full editing. Board selector dropdown. Synapse hooks for CRUD operations and real-time data subscriptions.
**Depends on:** Component 9

### Component 13: README
**Files:** `README.md`
**Description:** Entity table, custom tool reference, skill descriptions, UI views overview, file structure, run instructions.
**Depends on:** Components 2–12

## Constraints

- `manifest_version` must be `"0.4"`
- `upjack_version` must be `"0.1"`
- Entity prefixes: `bd` (board), `tk` (task) — unique within the app
- Schemas: JSON Schema draft 2020-12, `allOf` with base entity ref
- Never redeclare base entity fields (`id`, `type`, `version`, `created_at`, `updated_at`, `created_by`, `status`, `tags`, `source`, `relationships`)
- Never set `additionalProperties: false` in schemas
- Skills: natural language only, no code
- Seed data: no `id`, `created_at`, `updated_at` fields
- Server: `create_server()` for auto-CRUD + `@mcp.tool()` for custom tools
- Custom tools return `dict` with optional `error` key and `next_step` guidance
- Custom tool inputs should be simple (1-2 IDs + options), not deep nested objects
- All file paths in manifest must point to files that exist
- Board `columns` array defines the source of truth for valid column keys — task `column` values must match

## Verification

```bash
cd mcp-servers/todo-board

# Check manifest is valid JSON
cat manifest.json | python -m json.tool

# Check schemas are valid JSON
for f in schemas/*.schema.json; do cat "$f" | python -m json.tool; done

# Check seed data is valid JSON
for f in seed/*.json; do cat "$f" | python -m json.tool; done

# Install dependencies
uv sync

# Run the server (smoke test, stdio mode)
uv run python server.py

# Build UI
cd ui && npm install && npm run build
```

## Acceptance Criteria

- [ ] All entity schemas validate against JSON Schema draft 2020-12
- [ ] All entity schemas compose with base entity via `allOf`
- [ ] Manifest references all entities, skills, and seed paths correctly
- [ ] Task triage skill has When to Use, Process, and Rules sections
- [ ] context.md documents board/task relationship and column workflow
- [ ] Seed data has 2 boards and 8 tasks with realistic variety
- [ ] Server starts and registers CRUD tools for both entities
- [ ] Custom tools (`move_task`, `reorder_column`, `board_summary`, `batch_archive`) register and appear in tool listing
- [ ] `move_task` enforces WIP limits (warning, not blocking) and sets `completed_at` on done-like columns
- [ ] `reorder_column` batch-updates positions for all tasks in a column
- [ ] `board_summary` returns per-column counts, WIP status, overdue/stalled metrics
- [ ] `batch_archive` archives completed tasks older than N days
- [ ] Custom tools return `{"error": "..."}` on failure (not exceptions)
- [ ] Synapse UI renders board view with draggable cards across columns
- [ ] Synapse UI renders table view with sorting, filtering, and inline edit
- [ ] View toggle switches between board and table without data loss
- [ ] Board selector switches context and reloads tasks for selected board
- [ ] Drag-and-drop updates task column and position via Synapse tool calls
- [ ] Theme follows host light/dark mode
- [ ] README documents all entities, skill, UI views, and run instructions

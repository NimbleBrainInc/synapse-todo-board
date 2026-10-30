# Todo Board

Kanban and table views for boards and tasks, with shared tools for the UI and agent.
A FastMCP server and app-owned JSON store back React views built with Synapse.

## Run

Python 3.13+, uv, Node and npm are required. Install the locked dependencies and build the UI:

```sh
uv sync --frozen
cd ui
npm ci --ignore-scripts
npm run build
cd ..
```

For an MCP client that launches a command:

```sh
MPAK_WORKSPACE=./workspace uv run python -m synapse_todo_board.server
```

For a client that connects over HTTP:

```sh
MPAK_WORKSPACE=./workspace uv run uvicorn synapse_todo_board.server:app --host 127.0.0.1 --port 8001
```

The MCP endpoint is `http://127.0.0.1:8001/mcp`. Keep the binding local for a local
installation. A managed deployment must supply its own network and access controls.
The module entry point remains stdio for packaged clients.

## Use the board

Choose a board in the app, then add tasks or ask the agent to create, find, move or archive them.
The selected board appears in the agent's visible context. Task creation uses
`create_board_task(board_id, title, ...)`; moving uses `move_task(task_id, target_column)`.
The [tool usage guide](SKILL.md) covers common requests and the
[task-triage skill](skills/task-triage/SKILL.md) describes priority and review guidance.
Those are agent guidance. This server does not install a scheduler or run triage automatically.

Every saved board/task/schema change emits `notifications/resources/list_changed` to the
calling MCP session. Synapse refreshes open views after that notification. Read-only calls do
not emit changes, and the UI requests all boards and all active tasks for the selected board.

## Tools and resources

| Surface | Purpose |
| --- | --- |
| Board create/get/update/list/search/delete | Manage named boards and their columns |
| Task get/update/list/search/delete | Read and edit tasks; creation stays board-scoped |
| `create_board_task`, `find_board_task` | Create or find tasks on a specific board |
| `move_task`, `reorder_column` | Validate column/board membership and update positions |
| `board_summary`, `archive_task`, `batch_archive` | Review and clean up board work |
| Relationship query, related and composite tools | Follow the existing `belongs_to` links |
| `add_field`, `seed_data`, `rebuild_index` | Extend schemas, load samples or rebuild the derived index |
| `set_custom_instructions` | Save per-workspace agent guidance, capped at 8 KiB |

List/search/query results use an `entities` envelope. `list_boards`, `list_tasks` and
relationship queries default to 50 records; `limit: null` requests all. `delete_*` soft-deletes
by default. Explicit `hard: true` permanently removes only the selected record.

The server retains six resource URIs: `ui://todo-board/main`, `ui://todo-board/settings`,
`app://instructions`, `skill://todo-board/usage`, `upjack://context` and
`upjack://skills/task-triage`. The two legacy URI names remain for client compatibility;
Upjack is not a runtime dependency. Both UI resources use the same built HTML, with a static
view marker selecting settings. AppFrame and host tokens size and theme both views; the
settings screen reads resources and calls tools through the SDK's own-server bridge.

## Data and upgrades

`MPAK_WORKSPACE` selects the workspace root; `UPJACK_ROOT` remains a legacy fallback.
Without either variable, the server uses `./workspace`.

- Records: `apps/todo-board/data/boards/` and `apps/todo-board/data/tasks/`.
- Added schema fields: `apps/todo-board/schemas/`.
- Custom instructions: `custom-instructions.md`.
- Relationship index: `apps/todo-board/data/_index/relations.json`, derived from records.

Existing JSON records retain IDs, timestamps, relationships and unknown custom fields.
Individual writes use a temporary file and atomic rename. A process-local lock serializes
operations within one server; run one writer per workspace. This is not a cross-process database.

If the old Upjack version added fields to its source schemas, follow the
[migration guide](MIGRATION.md) before changing releases. Keep the original source and a workspace
backup. A generic installer supplies paths, backups and lifecycle management; this app owns
schema interpretation and migration.

## Develop and verify

See [AGENTS.md](AGENTS.md) for the source map and invariants. The
[domain specification](SPEC.md#domain-model) explains boards, tasks and relationships.

```sh
uv run pytest -p no:cacheprovider tests/ -q
uv run ruff check src/
uv run ty check src/
cd ui && npm run build
```

With the UI built and locked Python dependencies available, run the disposable transport checks:

```sh
uv run python tests/http_workflow.py
uv run python tests/stdio_workflow.py
uv run python tests/notification_workflow.py
```

They start only their own loopback server, use fresh temporary data, stop it, and retain JSON
results. The HTTP workflow also restarts its server to verify saved records and instructions.

Build the UI before creating a distributable wheel with `uv build --wheel`. The wheel includes
schemas, skills, context, sample data and built UI under the Python package's assets directory.
Editable environments use those assets directly from the checkout, so Python setup can precede
the UI build. Check a built wheel without installing it or using the checkout's assets:

```sh
uv run python tests/wheel_workflow.py dist/synapse_todo_board-0.3.1-py3-none-any.whl
```

[MIT license](LICENSE) · [NimbleBrain](https://nimblebrain.ai) ·
[Package](https://mpak.dev/packages/@nimblebraininc/synapse-todo-board)

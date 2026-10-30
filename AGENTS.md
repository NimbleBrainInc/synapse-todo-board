# Todo Board

Start with [README.md](README.md) for setup, transports, data paths and checks.
[SKILL.md](SKILL.md) and [task triage](skills/task-triage/SKILL.md) describe agent use.
[MIGRATION.md](MIGRATION.md) covers an existing Upjack workspace.

## Source map

- `src/synapse_todo_board/server.py`: FastMCP registration, HTTP/stdio entries and notifications.
- `crud.py` and `store.py` implement CRUD contracts, validation and JSON persistence.
- `assets.py` locates bundled wheel assets or the editable checkout's resources.
- `tools/`: board-specific task creation, moves, reorder, archive and summary operations.
- `migration.py`: operator-only schema plan/apply command. It is not an MCP tool.
- `schemas/`: bundled entity definitions; workspace overrides stay outside source.
- `ui/src/`: React views and Synapse hooks; `Settings.tsx` owns the instructions editor.
  `ui/dist/index.html` serves both views with a static settings marker.
- `tests/`: tool, storage and migration boundaries; HTTP checks retain disposable results.

## Keep these contracts

Task creation stays board-scoped. Validate all reorder targets before the first write.
Retain record IDs, creation metadata, relationships and unknown fields during upgrades.
Read-only tools do not announce writes. Saved changes announce the supported MCP resource-list
notification; UI reads must not cause notification loops.

Keep `python -m synapse_todo_board.server` on stdio and export `app` for ASGI HTTP.
Diagnostics go to stderr; stdout belongs to the stdio protocol. Use the locked dependencies
and run the relevant commands in the README. Include compatibility and regression evidence
with changes to tool schemas or saved data. Test fixtures contain synthetic data only.

## Contribute

Use a topic branch and pull request. Explain the change, its purpose and verification in the
PR body, naming the tested commit and unavailable checks. Independent review covers the current
pushed head; later changes need a delta review. Required checks pass without an admin bypass.
Maintainers merge upstream and publish releases. Verify the accepted source before claiming
that a change landed.

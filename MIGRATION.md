# Move an existing workspace off Upjack

The FastMCP server reads the existing board/task JSON layout. It does not rewrite records
at startup. IDs, creation metadata, relationships and unknown custom fields are retained.

Schema additions are different: the old `add_field` changed files in the app's source checkout.
The new server keeps field definitions in the workspace. Preserve the old source until those
definitions have been imported.

1. Stop every writer using this workspace. Save a verified copy of the workspace and old source.
2. From the new release, review a read-only plan:

   ```sh
   uv run python -m synapse_todo_board.migration --legacy-source <old-source> --workspace <workspace>
   ```

3. Review the returned `updates` and `planHash`. The command accepts only added fields with a
   supported type and valid default. Changes to existing fields, conflicting workspace fields,
   unsupported schema constraints and symlinked schema paths are rejected.
4. Apply that exact plan, keeping the same source and workspace:

   ```sh
   uv run python -m synapse_todo_board.migration --legacy-source <old-source> --workspace <workspace> --apply --expected-plan-hash <planHash>
   ```

5. Start the new server with `MPAK_WORKSPACE` pointing to that workspace. Read a known board,
   its tasks and a custom field. Make one intended edit, restart, and check the saved result.

The helper validates both entity schemas and receiving overrides before writing. It changes
only workspace schema overrides, never source schemas or records. It checks the plan hash
again before applying; a changed source/override requires a new review. Individual files are
written atomically, but a disk failure between files is not a transaction. An installer or
operator owns backups, stopping writers and rollback.

Custom field defaults are hydrated when reading older records; existing files are not bulk
rewritten. New edits are validated against the selected schema. Keep a pre-upgrade backup for
rollback. Definitions added after the upgrade are not automatically converted back into an
older Upjack source tree.

The runtime no longer runs Upjack hooks, views or schedules. Triage remains available as agent
guidance. Configure automation explicitly in its owning host. A legacy manifest declaration
does not start a scheduler.

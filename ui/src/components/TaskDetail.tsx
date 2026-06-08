import { useCallback, useState } from "react";
import type { BoardColumn } from "../hooks/useBoards";
import type { Task } from "../hooks/useTasks";
import { useSynapse } from "@nimblebrain/synapse/react";
import { Button, Drawer, Stack, TextLink } from "@nimblebrain/synapse/ui";
import { useStyleTokens } from "../tokens";
import { errorStyle, inputStyle, labelStyle } from "../formStyles";

interface TaskDetailProps {
  task?: Task | null;
  columns: BoardColumn[];
  boardId: string;
  defaultColumn?: string;
  onClose: () => void;
  onSaved?: () => void;
}

const PRIORITIES = ["critical", "high", "medium", "low", "none"] as const;
const EFFORTS = ["trivial", "small", "medium", "large", "epic"] as const;

/**
 * Slide-over panel for editing or creating a single task, built on the shared
 * `Drawer` (native `<dialog>` — Escape, backdrop dismissal, and focus handling
 * come from the library).
 * Edit mode: task prop is provided. Save calls update_task (and move_task if column changed).
 * Create mode: task prop is null/undefined. Save calls create_board_task, which wires the board relationship.
 */
export function TaskDetail({ task, columns, boardId, defaultColumn, onClose, onSaved }: TaskDetailProps) {
  const synapse = useSynapse();
  const t = useStyleTokens();

  const isCreate = !task;
  const initialColumn = task?.column ?? defaultColumn ?? columns[0]?.key ?? "";

  const [title, setTitle] = useState(task?.title ?? "");
  const [description, setDescription] = useState(task?.description ?? "");
  const [priority, setPriority] = useState<Task["priority"]>(task?.priority ?? "none");
  const [column, setColumn] = useState(initialColumn);
  const [assignee, setAssignee] = useState(task?.assignee ?? "");
  const [dueDate, setDueDate] = useState(task?.due_date ?? "");
  const [effort, setEffort] = useState(task?.effort ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const input = inputStyle(t);
  const label = labelStyle(t);

  const handleSave = useCallback(async () => {
    setSaving(true);
    setError(null);
    try {
      if (isCreate) {
        // Create mode — custom tool that validates column + wires belongs_to
        const result = await synapse.callTool("create_board_task", {
          board_id: boardId,
          title,
          description: description || undefined,
          priority,
          // Empty string → omit so server picks the board's default column
          column: column || undefined,
          assignee: assignee || undefined,
          due_date: dueDate || undefined,
          effort: effort || undefined,
        });

        if (result.isError) {
          setError(String(result.data));
          return;
        }
      } else {
        // Edit mode — if column changed, use move_task for WIP enforcement
        if (column !== task.column) {
          await synapse.callTool("move_task", {
            task_id: task.id,
            target_column: column,
          });
        }

        const result = await synapse.callTool("update_task", {
          task_id: task.id,
          title,
          description: description || undefined,
          priority,
          assignee: assignee || undefined,
          due_date: dueDate || undefined,
          effort: effort || undefined,
        });

        if (result.isError) {
          setError(String(result.data));
          return;
        }
      }

      onSaved?.();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to ${isCreate ? "create" : "save"} task`);
    } finally {
      setSaving(false);
    }
  }, [synapse, isCreate, task, title, description, priority, column, assignee, dueDate, effort, boardId, onClose, onSaved]);

  const handleArchive = useCallback(async () => {
    if (!task) return;
    setSaving(true);
    setError(null);
    try {
      const result = await synapse.callTool("archive_task", {
        task_id: task.id,
      });
      if (result.isError) {
        setError(String(result.data));
        return;
      }
      onSaved?.();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to archive task");
    } finally {
      setSaving(false);
    }
  }, [synapse, task, onClose, onSaved]);

  return (
    <Drawer open onClose={onClose} width={420}>
      <Drawer.Header onClose={onClose}>{isCreate ? "New Task" : "Edit Task"}</Drawer.Header>

      <Drawer.Body>
        <Stack gap="1rem">
          {/* Title */}
          <div>
            <label style={label}>Title</label>
            <input type="text" value={title} onChange={(e) => setTitle(e.target.value)} style={input} />
          </div>

          {/* Description */}
          <div>
            <label style={label}>Description</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={4}
              style={{ ...input, resize: "vertical" }}
            />
          </div>

          {/* Priority + Effort row */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
            <div>
              <label style={label}>Priority</label>
              <select
                value={priority}
                onChange={(e) => setPriority(e.target.value as Task["priority"])}
                style={input}
              >
                {PRIORITIES.map((p) => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
            </div>
            <div>
              <label style={label}>Effort</label>
              <select value={effort} onChange={(e) => setEffort(e.target.value)} style={input}>
                <option value="">--</option>
                {EFFORTS.map((e) => (
                  <option key={e} value={e}>{e}</option>
                ))}
              </select>
            </div>
          </div>

          {/* Column */}
          <div>
            <label style={label}>Column</label>
            <select value={column} onChange={(e) => setColumn(e.target.value)} style={input}>
              {columns.map((col) => (
                <option key={col.key} value={col.key}>{col.label}</option>
              ))}
            </select>
          </div>

          {/* Assignee */}
          <div>
            <label style={label}>Assignee</label>
            <input
              type="text"
              value={assignee}
              onChange={(e) => setAssignee(e.target.value)}
              placeholder="Name or email"
              style={input}
            />
          </div>

          {/* Due date */}
          <div>
            <label style={label}>Due Date</label>
            <input type="date" value={dueDate} onChange={(e) => setDueDate(e.target.value)} style={input} />
          </div>

          {error && <div style={errorStyle(t)}>{error}</div>}
        </Stack>
      </Drawer.Body>

      <Drawer.Footer style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
        {!isCreate && (
          <TextLink tone="danger" onClick={handleArchive} disabled={saving}>
            Archive
          </TextLink>
        )}
        <div style={{ flex: 1 }} />
        <Button variant="secondary" size="sm" onClick={onClose}>
          Cancel
        </Button>
        <Button size="sm" onClick={handleSave} disabled={saving || !title.trim()}>
          {saving ? "Saving..." : "Save"}
        </Button>
      </Drawer.Footer>
    </Drawer>
  );
}

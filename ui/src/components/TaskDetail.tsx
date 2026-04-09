import { useCallback, useEffect, useState } from "react";
import type { BoardColumn } from "../hooks/useBoards";
import type { Task } from "../hooks/useTasks";
import { useSynapse } from "@nimblebrain/synapse/react";

interface TaskDetailProps {
  task?: Task | null;
  columns: BoardColumn[];
  boardId: string;
  defaultColumn?: string;
  onClose: () => void;
  onSaved?: () => void;
  isDark: boolean;
  accentColor?: string;
}

const PRIORITIES = ["critical", "high", "medium", "low", "none"] as const;
const EFFORTS = ["trivial", "small", "medium", "large", "epic"] as const;

/**
 * Modal/slide-over panel for editing or creating a single task.
 * Edit mode: task prop is provided. Save calls update_task (and move_task if column changed).
 * Create mode: task prop is null/undefined. Save calls create_task with board relationship.
 * Escape key or close button dismisses.
 */
export function TaskDetail({ task, columns, boardId, defaultColumn, onClose, onSaved, isDark, accentColor = "#2563eb" }: TaskDetailProps) {
  const synapse = useSynapse();

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

  // Escape key to close
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  const handleSave = useCallback(async () => {
    setSaving(true);
    setError(null);
    try {
      if (isCreate) {
        // Create mode
        const result = await synapse.callTool("create_task", {
          data: {
            title,
            description: description || undefined,
            priority,
            column,
            assignee: assignee || undefined,
            due_date: dueDate || undefined,
            effort: effort || undefined,
            relationships: [{ rel: "belongs_to", target: boardId }],
          },
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
          entity_id: task.id,
          data: {
            title,
            description: description || undefined,
            priority,
            assignee: assignee || undefined,
            due_date: dueDate || undefined,
            effort: effort || undefined,
          },
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
      const result = await synapse.callTool("update_task", {
        task_id: task.id,
        data: { status: "archived" },
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

  const bg = isDark ? "#1e1e36" : "#ffffff";
  const overlayBg = isDark ? "rgba(0,0,0,0.6)" : "rgba(0,0,0,0.3)";
  const borderColor = isDark ? "#3d3d5c" : "#ddd";
  const inputStyle: React.CSSProperties = {
    width: "100%",
    padding: "0.5rem",
    borderRadius: "4px",
    border: `1px solid ${borderColor}`,
    background: isDark ? "#16162a" : "#f8f9fa",
    color: isDark ? "#e0e0e0" : "#1a1a2e",
    fontSize: "0.875rem",
    boxSizing: "border-box",
  };
  const labelStyle: React.CSSProperties = {
    display: "block",
    fontSize: "0.75rem",
    fontWeight: 600,
    marginBottom: "0.25rem",
    color: isDark ? "#aaa" : "#555",
    textTransform: "uppercase",
    letterSpacing: "0.04em",
  };

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: overlayBg,
        display: "flex",
        justifyContent: "flex-end",
        zIndex: 1000,
      }}
    >
      {/* Slide-over panel */}
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "420px",
          maxWidth: "100vw",
          height: "100vh",
          background: bg,
          borderLeft: `1px solid ${borderColor}`,
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        }}
      >
        {/* Header */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "1rem 1.25rem",
            borderBottom: `1px solid ${borderColor}`,
          }}
        >
          <h3 style={{ margin: 0, fontSize: "1rem", fontWeight: 600 }}>
            {isCreate ? "New Task" : "Edit Task"}
          </h3>
          <button
            onClick={onClose}
            style={{
              background: "none",
              border: "none",
              fontSize: "1.25rem",
              cursor: "pointer",
              color: isDark ? "#888" : "#666",
              padding: "0.25rem",
              lineHeight: 1,
            }}
            aria-label="Close"
          >
            x
          </button>
        </div>

        {/* Form body */}
        <div style={{ flex: 1, overflowY: "auto", padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
          {/* Title */}
          <div>
            <label style={labelStyle}>Title</label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              style={inputStyle}
            />
          </div>

          {/* Description */}
          <div>
            <label style={labelStyle}>Description</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={4}
              style={{ ...inputStyle, resize: "vertical" }}
            />
          </div>

          {/* Priority + Effort row */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
            <div>
              <label style={labelStyle}>Priority</label>
              <select
                value={priority}
                onChange={(e) => setPriority(e.target.value as Task["priority"])}
                style={inputStyle}
              >
                {PRIORITIES.map((p) => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
            </div>
            <div>
              <label style={labelStyle}>Effort</label>
              <select
                value={effort}
                onChange={(e) => setEffort(e.target.value)}
                style={inputStyle}
              >
                <option value="">--</option>
                {EFFORTS.map((e) => (
                  <option key={e} value={e}>{e}</option>
                ))}
              </select>
            </div>
          </div>

          {/* Column */}
          <div>
            <label style={labelStyle}>Column</label>
            <select
              value={column}
              onChange={(e) => setColumn(e.target.value)}
              style={inputStyle}
            >
              {columns.map((col) => (
                <option key={col.key} value={col.key}>{col.label}</option>
              ))}
            </select>
          </div>

          {/* Assignee */}
          <div>
            <label style={labelStyle}>Assignee</label>
            <input
              type="text"
              value={assignee}
              onChange={(e) => setAssignee(e.target.value)}
              placeholder="Name or email"
              style={inputStyle}
            />
          </div>

          {/* Due date */}
          <div>
            <label style={labelStyle}>Due Date</label>
            <input
              type="date"
              value={dueDate}
              onChange={(e) => setDueDate(e.target.value)}
              style={inputStyle}
            />
          </div>

          {/* Error */}
          {error && (
            <div style={{
              padding: "0.5rem 0.75rem",
              borderRadius: "4px",
              background: isDark ? "#3b1a1a" : "#fee",
              color: isDark ? "#f88" : "#c00",
              fontSize: "0.8rem",
            }}>
              {error}
            </div>
          )}
        </div>

        {/* Footer actions */}
        <div
          style={{
            display: "flex",
            gap: "0.5rem",
            padding: "1rem 1.25rem",
            borderTop: `1px solid ${borderColor}`,
          }}
        >
          {!isCreate && (
            <button
              onClick={handleArchive}
              disabled={saving}
              style={{
                padding: "0.5rem 1rem",
                borderRadius: "6px",
                border: `1px solid ${isDark ? "#5c3d3d" : "#e0b0b0"}`,
                background: isDark ? "#2e1a1a" : "#fff5f5",
                color: isDark ? "#f88" : "#c00",
                fontSize: "0.8rem",
                cursor: saving ? "not-allowed" : "pointer",
                opacity: saving ? 0.6 : 1,
              }}
            >
              Archive
            </button>
          )}
          <div style={{ flex: 1 }} />
          <button
            onClick={onClose}
            style={{
              padding: "0.5rem 1rem",
              borderRadius: "6px",
              border: `1px solid ${borderColor}`,
              background: "transparent",
              color: isDark ? "#ccc" : "#333",
              fontSize: "0.8rem",
              cursor: "pointer",
            }}
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving || !title.trim()}
            style={{
              padding: "0.5rem 1rem",
              borderRadius: "6px",
              border: "none",
              background: saving ? (isDark ? "#333" : "#ccc") : accentColor,
              color: "#fff",
              fontSize: "0.8rem",
              fontWeight: 600,
              cursor: saving || !title.trim() ? "not-allowed" : "pointer",
              opacity: saving || !title.trim() ? 0.6 : 1,
            }}
          >
            {saving ? "Saving..." : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}

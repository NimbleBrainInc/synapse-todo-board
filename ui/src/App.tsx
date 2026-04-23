import { useCallback, useEffect, useState } from "react";
import { useTheme, useSynapse, useVisibleState } from "@nimblebrain/synapse/react";
import { useBoards } from "./hooks/useBoards";
import { useTasks } from "./hooks/useTasks";
import type { Task } from "./hooks/useTasks";
import type { BoardColumn } from "./hooks/useBoards";
import { BoardSelector } from "./components/BoardSelector";
import { TaskDetail } from "./components/TaskDetail";
import BoardView from "./views/BoardView";
import TableView from "./views/TableView";

// ---------------------------------------------------------------------------
// Responsive styles (injected once)
// ---------------------------------------------------------------------------

const RESPONSIVE_STYLES = `
@media (max-width: 640px) {
  .tb-header {
    flex-wrap: wrap !important;
  }
  .tb-header-actions {
    order: 3;
    width: 100%;
    display: flex;
    gap: 0.5rem;
  }
  .tb-view-toggle {
    order: 2;
    margin-left: auto !important;
  }
  .tb-board-container {
    flex-direction: column !important;
  }
  .tb-board-container > div {
    flex: none !important;
    width: 100% !important;
    min-width: 0 !important;
  }
  .tb-table-wrap {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }
  .tb-table-wrap table {
    table-layout: auto !important;
    min-width: 0 !important;
  }
  .tb-col-hide-mobile {
    display: none !important;
  }
  .tb-filter-bar {
    flex-direction: column !important;
    align-items: stretch !important;
  }
  .tb-filter-bar > div,
  .tb-filter-bar > label {
    width: 100%;
  }
  .tb-filter-bar select {
    width: 100% !important;
    min-width: 0 !important;
  }
  .tb-bulk-bar {
    flex-wrap: wrap !important;
  }
  .tb-dialog-panel {
    width: 100vw !important;
    max-width: 100vw !important;
    border-radius: 0 !important;
  }
}
`;

let stylesInjected = false;
function injectStyles() {
  if (stylesInjected) return;
  stylesInjected = true;
  const el = document.createElement("style");
  el.textContent = RESPONSIVE_STYLES;
  document.head.appendChild(el);
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type ViewMode = "board" | "table";

const DEFAULT_COLUMNS: BoardColumn[] = [
  { key: "todo", label: "To Do" },
  { key: "in_progress", label: "In Progress" },
  { key: "done", label: "Done" },
];

const PRIORITIES = ["critical", "high", "medium", "low", "none"] as const;
const EFFORTS = ["trivial", "small", "medium", "large", "epic"] as const;

// ---------------------------------------------------------------------------
// Create Board Dialog
// ---------------------------------------------------------------------------

function CreateBoardDialog({
  isDark,
  accentColor,
  onClose,
  onCreate,
}: {
  isDark: boolean;
  accentColor: string;
  onClose: () => void;
  onCreate: (name: string, description: string, columns: BoardColumn[]) => Promise<void>;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [columns, setColumns] = useState<BoardColumn[]>(DEFAULT_COLUMNS.map((c) => ({ ...c })));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  const handleColumnChange = (index: number, field: "key" | "label", value: string) => {
    setColumns((prev) => {
      const next = [...prev];
      next[index] = { ...next[index], [field]: value };
      // Auto-derive key from label if user hasn't manually edited the key
      if (field === "label") {
        next[index].key = value.toLowerCase().replace(/\s+/g, "_").replace(/[^a-z0-9_]/g, "");
      }
      return next;
    });
  };

  const addColumn = () => {
    setColumns((prev) => [...prev, { key: "", label: "" }]);
  };

  const removeColumn = (index: number) => {
    if (columns.length <= 1) return;
    setColumns((prev) => prev.filter((_, i) => i !== index));
  };

  const handleSubmit = async () => {
    if (!name.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await onCreate(
        name.trim(),
        description.trim(),
        columns.filter((c) => c.key && c.label),
      );
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create board");
    } finally {
      setSaving(false);
    }
  };

  const overlayBg = isDark ? "rgba(0,0,0,0.6)" : "rgba(0,0,0,0.3)";
  const panelBg = isDark ? "#1e1e36" : "#ffffff";
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
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "480px",
          maxWidth: "90vw",
          background: panelBg,
          borderRadius: "12px",
          border: `1px solid ${borderColor}`,
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
          <h3 style={{ margin: 0, fontSize: "1rem", fontWeight: 600 }}>Create Board</h3>
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

        {/* Body */}
        <div style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
          <div>
            <label style={labelStyle}>Board Name *</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="My Project Board"
              style={inputStyle}
              autoFocus
            />
          </div>

          <div>
            <label style={labelStyle}>Description</label>
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Optional description"
              style={inputStyle}
            />
          </div>

          <div>
            <label style={labelStyle}>Columns</label>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              {columns.map((col, i) => (
                <div key={i} style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
                  <input
                    type="text"
                    value={col.label}
                    onChange={(e) => handleColumnChange(i, "label", e.target.value)}
                    placeholder="Column name"
                    style={{ ...inputStyle, flex: 1 }}
                  />
                  <button
                    onClick={() => removeColumn(i)}
                    disabled={columns.length <= 1}
                    style={{
                      background: "none",
                      border: "none",
                      color: columns.length <= 1 ? (isDark ? "#444" : "#ccc") : (isDark ? "#f88" : "#c00"),
                      cursor: columns.length <= 1 ? "not-allowed" : "pointer",
                      fontSize: "1rem",
                      padding: "0.25rem",
                    }}
                    aria-label="Remove column"
                  >
                    x
                  </button>
                </div>
              ))}
              <button
                onClick={addColumn}
                style={{
                  background: "none",
                  border: `1px dashed ${borderColor}`,
                  borderRadius: "4px",
                  padding: "0.4rem",
                  color: isDark ? "#888" : "#666",
                  cursor: "pointer",
                  fontSize: "0.8rem",
                }}
              >
                + Add Column
              </button>
            </div>
          </div>

          {error && (
            <div
              style={{
                padding: "0.5rem 0.75rem",
                borderRadius: "4px",
                background: isDark ? "#3b1a1a" : "#fee",
                color: isDark ? "#f88" : "#c00",
                fontSize: "0.8rem",
              }}
            >
              {error}
            </div>
          )}
        </div>

        {/* Footer */}
        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            gap: "0.5rem",
            padding: "1rem 1.25rem",
            borderTop: `1px solid ${borderColor}`,
          }}
        >
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
            onClick={handleSubmit}
            disabled={saving || !name.trim()}
            style={{
              padding: "0.5rem 1rem",
              borderRadius: "6px",
              border: "none",
              background: saving || !name.trim() ? (isDark ? "#333" : "#ccc") : accentColor,
              color: "#fff",
              fontSize: "0.8rem",
              fontWeight: 600,
              cursor: saving || !name.trim() ? "not-allowed" : "pointer",
              opacity: saving || !name.trim() ? 0.6 : 1,
            }}
          >
            {saving ? "Creating..." : "Create Board"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Create Task Dialog
// ---------------------------------------------------------------------------

function CreateTaskDialog({
  isDark,
  accentColor,
  columns,
  defaultColumn,
  onClose,
  onCreate,
}: {
  isDark: boolean;
  accentColor: string;
  columns: BoardColumn[];
  defaultColumn: string;
  onClose: () => void;
  onCreate: (data: {
    title: string;
    column: string;
    priority: string;
    assignee: string;
    due_date: string;
    effort: string;
  }) => Promise<void>;
}) {
  const [title, setTitle] = useState("");
  const [column, setColumn] = useState(defaultColumn);
  const [priority, setPriority] = useState<string>("medium");
  const [assignee, setAssignee] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [effort, setEffort] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  // Update column if defaultColumn changes (e.g. clicking + on a different column)
  useEffect(() => {
    setColumn(defaultColumn);
  }, [defaultColumn]);

  const handleSubmit = async () => {
    if (!title.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await onCreate({
        title: title.trim(),
        column,
        priority,
        assignee: assignee.trim(),
        due_date: dueDate,
        effort,
      });
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create task");
    } finally {
      setSaving(false);
    }
  };

  const overlayBg = isDark ? "rgba(0,0,0,0.6)" : "rgba(0,0,0,0.3)";
  const panelBg = isDark ? "#1e1e36" : "#ffffff";
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
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "440px",
          maxWidth: "90vw",
          background: panelBg,
          borderRadius: "12px",
          border: `1px solid ${borderColor}`,
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
          <h3 style={{ margin: 0, fontSize: "1rem", fontWeight: 600 }}>New Task</h3>
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

        {/* Body */}
        <div style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
          <div>
            <label style={labelStyle}>Title *</label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="What needs to be done?"
              style={inputStyle}
              autoFocus
            />
          </div>

          {/* Column + Priority row */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
            <div>
              <label style={labelStyle}>Column</label>
              <select value={column} onChange={(e) => setColumn(e.target.value)} style={inputStyle}>
                {columns.map((c) => (
                  <option key={c.key} value={c.key}>
                    {c.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label style={labelStyle}>Priority</label>
              <select value={priority} onChange={(e) => setPriority(e.target.value)} style={inputStyle}>
                {PRIORITIES.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Assignee + Due date row */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
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
            <div>
              <label style={labelStyle}>Due Date</label>
              <input
                type="date"
                value={dueDate}
                onChange={(e) => setDueDate(e.target.value)}
                style={inputStyle}
              />
            </div>
          </div>

          {/* Effort */}
          <div>
            <label style={labelStyle}>Effort</label>
            <select value={effort} onChange={(e) => setEffort(e.target.value)} style={inputStyle}>
              <option value="">--</option>
              {EFFORTS.map((e) => (
                <option key={e} value={e}>
                  {e}
                </option>
              ))}
            </select>
          </div>

          {error && (
            <div
              style={{
                padding: "0.5rem 0.75rem",
                borderRadius: "4px",
                background: isDark ? "#3b1a1a" : "#fee",
                color: isDark ? "#f88" : "#c00",
                fontSize: "0.8rem",
              }}
            >
              {error}
            </div>
          )}
        </div>

        {/* Footer */}
        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            gap: "0.5rem",
            padding: "1rem 1.25rem",
            borderTop: `1px solid ${borderColor}`,
          }}
        >
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
            onClick={handleSubmit}
            disabled={saving || !title.trim()}
            style={{
              padding: "0.5rem 1rem",
              borderRadius: "6px",
              border: "none",
              background: saving || !title.trim() ? (isDark ? "#333" : "#ccc") : accentColor,
              color: "#fff",
              fontSize: "0.8rem",
              fontWeight: 600,
              cursor: saving || !title.trim() ? "not-allowed" : "pointer",
              opacity: saving || !title.trim() ? 0.6 : 1,
            }}
          >
            {saving ? "Creating..." : "Create Task"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// App
// ---------------------------------------------------------------------------

export default function App() {
  const theme = useTheme();
  const synapse = useSynapse();
  const { boards, loading: boardsLoading, refresh: refreshBoards } = useBoards();

  const [activeView, setActiveView] = useState<ViewMode>("board");
  const [selectedBoardId, setSelectedBoardId] = useState<string | null>(null);
  const [showCreateBoard, setShowCreateBoard] = useState(false);
  const [showCreateTask, setShowCreateTask] = useState(false);
  const [createTaskColumn, setCreateTaskColumn] = useState<string>("");
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);

  const { tasks, refresh: refreshTasks } = useTasks(selectedBoardId);

  // Derive the current board object from the boards list
  const selectedBoard = boards.find((b) => b.id === selectedBoardId) ?? null;

  // Apply theme mode to document
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme.mode);
  }, [theme.mode]);

  const isDark = theme.mode === "dark";
  const accentColor = theme.tokens["--color-text-accent"] || "#2563eb";

  // Inject responsive CSS on first render
  useEffect(() => { injectStyles(); }, []);

  // Auto-select the first board when boards load and nothing is selected
  useEffect(() => {
    if (!selectedBoardId && boards.length > 0) {
      setSelectedBoardId(boards[0].id);
    }
  }, [selectedBoardId, boards]);

  // Push current UI state to the agent so it knows what the user is looking at
  const pushState = useVisibleState();
  useEffect(() => {
    const tasksByColumn: Record<string, number> = {};
    for (const t of tasks) {
      tasksByColumn[t.column] = (tasksByColumn[t.column] ?? 0) + 1;
    }
    pushState(
      {
        selectedBoard: selectedBoard
          ? { id: selectedBoard.id, name: selectedBoard.name, columns: selectedBoard.columns.map((c) => c.key) }
          : null,
        view: activeView,
        taskCount: tasks.length,
        tasksByColumn,
      },
      selectedBoard
        ? `Viewing "${selectedBoard.name}" board (${activeView} view, ${tasks.length} tasks)`
        : "No board selected",
    );
  }, [selectedBoard, activeView, tasks, pushState]);

  // -- Board selector handler (intercepts "__create__" sentinel) --

  const handleBoardChange = useCallback((boardId: string | null) => {
    if (boardId === "__create__") {
      setShowCreateBoard(true);
      return;
    }
    setSelectedBoardId(boardId);
  }, []);

  // -- Create board --

  const handleCreateBoard = useCallback(
    async (name: string, description: string, columns: BoardColumn[]) => {
      const result = await synapse.callTool("create_board", {
        name,
        description: description || undefined,
        columns: columns.map((c) => ({ key: c.key, label: c.label })),
      });
      if (result.isError) {
        throw new Error(String(result.data));
      }
      await refreshBoards();
      // Select the newly created board
      const data = result.data as { id?: string } | undefined;
      if (data?.id) {
        setSelectedBoardId(data.id);
      }
    },
    [synapse, refreshBoards],
  );

  // -- Create task --

  const handleAddTask = useCallback(
    (columnKey: string) => {
      setCreateTaskColumn(columnKey);
      setShowCreateTask(true);
    },
    [],
  );

  const handleCreateTask = useCallback(
    async (data: {
      title: string;
      column: string;
      priority: string;
      assignee: string;
      due_date: string;
      effort: string;
    }) => {
      if (!selectedBoardId) return;
      const args: Record<string, unknown> = {
        board_id: selectedBoardId,
        title: data.title,
        column: data.column,
        priority: data.priority,
      };
      if (data.assignee) args.assignee = data.assignee;
      if (data.due_date) args.due_date = data.due_date;
      if (data.effort) args.effort = data.effort;

      const result = await synapse.callTool("create_board_task", args);
      if (result.isError) {
        throw new Error(String(result.data));
      }
      await refreshTasks();
    },
    [synapse, selectedBoardId, refreshTasks],
  );

  // -- Task click (open detail) --

  const handleTaskClick = useCallback((task: Task) => {
    setSelectedTask(task);
  }, []);

  // -- Header "New Task" button (uses default column) --

  const handleNewTaskHeader = useCallback(() => {
    const defaultCol = selectedBoard?.default_column ?? selectedBoard?.columns[0]?.key ?? "";
    setCreateTaskColumn(defaultCol);
    setShowCreateTask(true);
  }, [selectedBoard]);

  // -- Delete board --

  const handleDeleteBoard = useCallback(async () => {
    if (!selectedBoardId) return;
    const board = boards.find((b) => b.id === selectedBoardId);
    if (!confirm(`Delete board "${board?.name}"? All tasks on this board will be orphaned.`)) return;
    try {
      await synapse.callTool("delete_board", { board_id: selectedBoardId });
      setSelectedBoardId(null);
      await refreshBoards();
    } catch (err) {
      console.error("Failed to delete board:", err);
    }
  }, [synapse, selectedBoardId, boards, refreshBoards]);

  // -- Render --

  const buttonBase: React.CSSProperties = {
    padding: "0.4rem 1rem",
    fontSize: "0.8rem",
    border: `1px solid ${isDark ? "#3d3d5c" : "#ccc"}`,
    cursor: "pointer",
    color: isDark ? "#e0e0e0" : "#1a1a2e",
  };

  return (
    <div
      style={{
        fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
        minHeight: "100vh",
        background: isDark ? "#1a1a2e" : "#f8f9fa",
        color: isDark ? "#e0e0e0" : "#1a1a2e",
      }}
    >
      {/* ---- Header ---- */}
      <header
        className="tb-header"
        style={{
          display: "flex",
          alignItems: "center",
          gap: "0.75rem",
          padding: "0.75rem 1rem",
          borderBottom: `1px solid ${isDark ? "#2d2d44" : "#e0e0e0"}`,
          background: isDark ? "#16162a" : "#ffffff",
        }}
      >
        {/* Board selector */}
        <BoardSelector
          boards={boards}
          selectedBoardId={selectedBoardId}
          onBoardChange={handleBoardChange}
          isDark={isDark}
        />

        {/* New Task + Delete Board buttons */}
        {selectedBoard && (
          <div className="tb-header-actions" style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <button
              onClick={handleNewTaskHeader}
              style={{
                ...buttonBase,
                borderRadius: "6px",
                background: accentColor,
                border: "none",
                color: "#fff",
                fontWeight: 600,
              }}
            >
              + New Task
            </button>
            <button
              onClick={handleDeleteBoard}
              title="Delete this board"
              style={{
                ...buttonBase,
                borderRadius: "6px",
                background: "transparent",
                color: isDark ? "#888" : "#999",
                fontSize: "0.75rem",
                padding: "0.4rem 0.6rem",
              }}
            >
              Delete Board
            </button>
          </div>
        )}

        {/* View toggle (pushed to the right) */}
        <div className="tb-view-toggle" style={{ display: "flex", marginLeft: "auto", gap: 0 }}>
          {(["board", "table"] as const).map((view) => (
            <button
              key={view}
              onClick={() => setActiveView(view)}
              style={{
                ...buttonBase,
                fontWeight: activeView === view ? 600 : 400,
                borderRadius: view === "board" ? "6px 0 0 6px" : "0 6px 6px 0",
                background: activeView === view
                  ? (isDark ? "#2d2d44" : "#e8e8f0")
                  : (isDark ? "#1a1a2e" : "#fff"),
                textTransform: "capitalize",
                marginLeft: view === "table" ? "-1px" : 0,
              }}
            >
              {view === "board" ? "Board" : "Table"}
            </button>
          ))}
        </div>
      </header>

      {/* ---- Main content ---- */}
      <main>
        {boardsLoading && boards.length === 0 ? (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              padding: "6rem 2rem",
              textAlign: "center",
              color: isDark ? "#888" : "#666",
            }}
          >
            <div style={{ fontSize: "2rem", marginBottom: "0.75rem", opacity: 0.5 }}>...</div>
            <p style={{ margin: 0, fontSize: "0.875rem" }}>Loading boards</p>
          </div>
        ) : boards.length === 0 ? (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              padding: "6rem 2rem",
              textAlign: "center",
            }}
          >
            <div style={{ fontSize: "2.5rem", marginBottom: "1rem", opacity: 0.4 }}>
              {isDark ? "+" : "+"}
            </div>
            <h2 style={{ margin: "0 0 0.5rem", fontWeight: 600, fontSize: "1.25rem" }}>
              Create your first board
            </h2>
            <p style={{ color: isDark ? "#888" : "#666", margin: "0 0 1.5rem", maxWidth: "360px", lineHeight: 1.5 }}>
              Boards organize your tasks into columns. Start with a simple To Do / In Progress / Done workflow.
            </p>
            <button
              onClick={() => setShowCreateBoard(true)}
              style={{
                padding: "0.7rem 2rem",
                borderRadius: "8px",
                border: "none",
                background: accentColor,
                color: "#fff",
                fontSize: "0.9rem",
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              + New Board
            </button>
          </div>
        ) : !selectedBoard ? (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              padding: "6rem 2rem",
              textAlign: "center",
            }}
          >
            <h2 style={{ margin: "0 0 0.5rem", fontWeight: 500 }}>Select a board</h2>
            <p style={{ color: isDark ? "#888" : "#666", margin: 0 }}>
              Pick a board from the dropdown to get started.
            </p>
          </div>
        ) : activeView === "board" ? (
          <BoardView
            board={selectedBoard}
            tasks={tasks}
            accentColor={accentColor}
            onTaskClick={handleTaskClick}
            onAddTask={handleAddTask}
            onRefresh={refreshTasks}
          />
        ) : (
          <TableView
            tasks={tasks}
            board={selectedBoard}
            callTool={synapse.callTool.bind(synapse)}
            onRefresh={refreshTasks}
            isDark={isDark}
            accentColor={accentColor}
          />
        )}
      </main>

      {/* ---- Modals / Overlays ---- */}

      {showCreateBoard && (
        <CreateBoardDialog
          isDark={isDark}
          accentColor={accentColor}
          onClose={() => setShowCreateBoard(false)}
          onCreate={handleCreateBoard}
        />
      )}

      {showCreateTask && selectedBoard && (
        <CreateTaskDialog
          isDark={isDark}
          accentColor={accentColor}
          columns={selectedBoard.columns}
          defaultColumn={createTaskColumn || selectedBoard.default_column || selectedBoard.columns[0]?.key || ""}
          onClose={() => setShowCreateTask(false)}
          onCreate={handleCreateTask}
        />
      )}

      {selectedTask && selectedBoard && (
        <TaskDetail
          task={selectedTask}
          columns={selectedBoard.columns}
          boardId={selectedBoard.id}
          onClose={() => setSelectedTask(null)}
          onSaved={refreshTasks}
          isDark={isDark}
          accentColor={accentColor}
        />
      )}
    </div>
  );
}

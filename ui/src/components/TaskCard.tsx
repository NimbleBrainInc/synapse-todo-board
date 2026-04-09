import type { CSSProperties, DragEvent } from "react";

// -- Types --

export interface Task {
  id: string;
  title: string;
  priority: "critical" | "high" | "medium" | "low" | "none";
  column: string;
  position: number;
  due_date?: string;
  assignee?: string;
  effort?: "trivial" | "small" | "medium" | "large" | "epic";
  board_name?: string;
  description?: string;
  completed_at?: string;
  status: string;
  created_at: string;
  updated_at: string;
  relationships?: Array<{ rel: string; target: string }>;
}

export interface TaskCardProps {
  task: Task;
  isDark: boolean;
  onTaskClick?: (task: Task) => void;
}

// -- Priority config --

const PRIORITY_COLORS: Record<string, { bg: string; text: string }> = {
  critical: { bg: "#dc2626", text: "#ffffff" },
  high: { bg: "#ea580c", text: "#ffffff" },
  medium: { bg: "#ca8a04", text: "#ffffff" },
  low: { bg: "#2563eb", text: "#ffffff" },
  none: { bg: "#6b7280", text: "#ffffff" },
};

// -- Helpers --

function getInitials(name: string): string {
  return name
    .split(/[\s_-]+/)
    .map((w) => w[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

function isOverdue(dateStr: string): boolean {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const due = new Date(dateStr + "T00:00:00");
  return due < today;
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr + "T00:00:00");
  const month = d.toLocaleString("en-US", { month: "short" });
  return `${month} ${d.getDate()}`;
}

// -- Component --

export default function TaskCard({ task, isDark, onTaskClick }: TaskCardProps) {
  const priority = task.priority ?? "none";
  const priorityColor = PRIORITY_COLORS[priority] ?? PRIORITY_COLORS.none;
  const overdue = task.due_date ? isOverdue(task.due_date) : false;

  function handleDragStart(e: DragEvent<HTMLDivElement>) {
    e.dataTransfer.setData("text/plain", JSON.stringify({ id: task.id, column: task.column }));
    e.dataTransfer.effectAllowed = "move";
  }

  const cardStyle: CSSProperties = {
    padding: "0.625rem 0.75rem",
    borderRadius: "6px",
    background: isDark ? "#1e1e36" : "#ffffff",
    border: `1px solid ${isDark ? "#2d2d44" : "#e2e2e8"}`,
    cursor: "grab",
    userSelect: "none",
    transition: "box-shadow 0.15s, border-color 0.15s",
  };

  const titleStyle: CSSProperties = {
    fontSize: "0.8125rem",
    fontWeight: 500,
    lineHeight: 1.35,
    margin: 0,
    color: isDark ? "#e0e0e0" : "#1a1a2e",
    wordBreak: "break-word",
  };

  const badgeStyle: CSSProperties = {
    display: "inline-block",
    fontSize: "0.625rem",
    fontWeight: 600,
    lineHeight: 1,
    padding: "2px 6px",
    borderRadius: "3px",
    textTransform: "uppercase",
    letterSpacing: "0.03em",
    background: priorityColor.bg,
    color: priorityColor.text,
  };

  const metaRowStyle: CSSProperties = {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: "0.5rem",
    marginTop: "0.375rem",
  };

  const dueDateStyle: CSSProperties = {
    fontSize: "0.6875rem",
    color: overdue ? "#dc2626" : isDark ? "#888" : "#666",
    fontWeight: overdue ? 600 : 400,
  };

  const initialsStyle: CSSProperties = {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    width: "22px",
    height: "22px",
    borderRadius: "50%",
    background: isDark ? "#3d3d5c" : "#e0e0e8",
    color: isDark ? "#c0c0d0" : "#4a4a6a",
    fontSize: "0.5625rem",
    fontWeight: 600,
    flexShrink: 0,
  };

  return (
    <div
      draggable
      onDragStart={handleDragStart}
      onClick={() => onTaskClick?.(task)}
      style={cardStyle}
      onMouseEnter={(e) => {
        (e.currentTarget as HTMLDivElement).style.borderColor = isDark
          ? "#5555aa"
          : "#a0a0d0";
        (e.currentTarget as HTMLDivElement).style.boxShadow = isDark
          ? "0 2px 8px rgba(0,0,0,0.3)"
          : "0 2px 8px rgba(0,0,0,0.08)";
      }}
      onMouseLeave={(e) => {
        (e.currentTarget as HTMLDivElement).style.borderColor = isDark
          ? "#2d2d44"
          : "#e2e2e8";
        (e.currentTarget as HTMLDivElement).style.boxShadow = "none";
      }}
    >
      {/* Title */}
      <p style={titleStyle}>{task.title}</p>

      {/* Meta row: priority badge + due date + assignee */}
      <div style={metaRowStyle}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.375rem", flexWrap: "wrap" }}>
          {priority !== "none" && <span style={badgeStyle}>{priority}</span>}
          {task.due_date && <span style={dueDateStyle}>{formatDate(task.due_date)}</span>}
        </div>

        {task.assignee && (
          <div style={initialsStyle} title={task.assignee}>
            {getInitials(task.assignee)}
          </div>
        )}
      </div>
    </div>
  );
}

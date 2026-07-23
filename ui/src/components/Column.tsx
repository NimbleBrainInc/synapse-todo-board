import type { CSSProperties, DragEvent } from "react";
import { useState } from "react";
import TaskCard from "./TaskCard.js";
import type { Task } from "./TaskCard.js";
import { useStyleTokens } from "../tokens";

// -- Types --

export interface ColumnDef {
  key: string;
  label: string;
  color?: string;
  wip_limit?: number;
}

export interface ColumnProps {
  column: ColumnDef;
  tasks: Task[];
  onDrop: (taskId: string, sourceColumn: string, targetColumn: string) => void;
  onTaskClick?: (task: Task) => void;
  onAddTask?: (columnKey: string) => void;
}

// -- WIP helpers --

type WipStatus = "ok" | "at_limit" | "exceeded" | "unlimited";

function getWipStatus(count: number, limit: number | undefined): WipStatus {
  if (!limit || limit === 0) return "unlimited";
  if (count > limit) return "exceeded";
  if (count === limit) return "at_limit";
  return "ok";
}

// -- Component --

export default function Column({
  column,
  tasks,
  onDrop,
  onTaskClick,
  onAddTask,
}: ColumnProps) {
  const t = useStyleTokens();
  const [dragOver, setDragOver] = useState(false);

  const sorted = [...tasks].sort((a, b) => (a.position ?? 0) - (b.position ?? 0));
  const wipStatus = getWipStatus(tasks.length, column.wip_limit);

  const WIP_COLORS: Record<WipStatus, string> = {
    ok: t.success,
    at_limit: t.warning,
    exceeded: t.danger,
    unlimited: "transparent",
  };

  // -- Drag handlers --

  function handleDragOver(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    setDragOver(true);
  }

  function handleDragLeave(e: DragEvent<HTMLDivElement>) {
    // Only reset if leaving the column container itself
    if (!e.currentTarget.contains(e.relatedTarget as Node)) {
      setDragOver(false);
    }
  }

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragOver(false);
    try {
      const raw = e.dataTransfer.getData("text/plain");
      const { id: taskId, column: sourceColumn } = JSON.parse(raw);
      if (taskId && sourceColumn !== column.key) {
        onDrop(taskId, sourceColumn, column.key);
      }
    } catch {
      // Ignore invalid drop data
    }
  }

  // -- Styles --

  const columnStyle: CSSProperties = {
    display: "flex",
    flexDirection: "column",
    minWidth: "200px",
    flex: "1 1 272px",
    borderRadius: "8px",
    background: t.bgSubtle,
    border: dragOver ? `2px dashed ${t.accent}` : "2px solid transparent",
    transition: "border-color 0.15s",
  };

  const headerStyle: CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: "0.5rem",
    padding: "0.625rem 0.75rem",
  };

  const labelStyle: CSSProperties = {
    fontSize: "0.8125rem",
    fontWeight: 600,
    color: t.fgMuted,
    textTransform: "uppercase",
    letterSpacing: "0.04em",
  };

  const countStyle: CSSProperties = {
    fontSize: "0.6875rem",
    fontWeight: 500,
    color: t.fgFaint,
    marginLeft: "auto",
  };

  const wipDotStyle: CSSProperties = {
    width: "8px",
    height: "8px",
    borderRadius: "50%",
    background: WIP_COLORS[wipStatus],
    flexShrink: 0,
    display: wipStatus === "unlimited" ? "none" : "block",
  };

  const listStyle: CSSProperties = {
    display: "flex",
    flexDirection: "column",
    gap: "0.375rem",
    padding: "0 0.5rem 0.5rem",
    flex: 1,
    minHeight: "60px",
    overflowY: "auto",
  };

  const addBtnStyle: CSSProperties = {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    gap: "0.25rem",
    padding: "0.375rem",
    margin: "0 0.5rem 0.5rem",
    border: `1px dashed ${t.border}`,
    borderRadius: "6px",
    background: "transparent",
    color: t.fgMuted,
    fontSize: "0.75rem",
    cursor: "pointer",
    transition: "background 0.15s, color 0.15s",
  };

  return (
    <div
      style={columnStyle}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Header */}
      <div style={headerStyle}>
        {column.color && (
          <span
            style={{
              width: "10px",
              height: "10px",
              borderRadius: "3px",
              background: column.color,
              flexShrink: 0,
            }}
          />
        )}
        <span style={labelStyle}>{column.label}</span>
        <span style={wipDotStyle} title={wipStatus === "ok" ? "Under WIP limit" : wipStatus === "at_limit" ? "At WIP limit" : "WIP limit exceeded"} />
        <span style={countStyle}>
          {tasks.length}
          {column.wip_limit ? ` / ${column.wip_limit}` : ""}
        </span>
      </div>

      {/* Task list */}
      <div style={listStyle}>
        {sorted.map((task) => (
          <TaskCard key={task.id} task={task} onTaskClick={onTaskClick} />
        ))}
      </div>

      {/* Add task button */}
      <button
        style={addBtnStyle}
        onClick={() => onAddTask?.(column.key)}
        onMouseEnter={(e) => {
          (e.currentTarget as HTMLButtonElement).style.background = t.bgHover;
          (e.currentTarget as HTMLButtonElement).style.color = t.fg;
        }}
        onMouseLeave={(e) => {
          (e.currentTarget as HTMLButtonElement).style.background = "transparent";
          (e.currentTarget as HTMLButtonElement).style.color = t.fgMuted;
        }}
      >
        + Add task
      </button>
    </div>
  );
}

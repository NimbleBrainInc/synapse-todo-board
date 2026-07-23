import type { CSSProperties, DragEvent } from "react";
import { Avatar, Badge, Card, Inline, Text } from "@nimblebrain/synapse/ui";
import { PRIORITY_TONE, useStyleTokens } from "../tokens";

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
  onTaskClick?: (task: Task) => void;
}

// -- Helpers --

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

export default function TaskCard({ task, onTaskClick }: TaskCardProps) {
  const t = useStyleTokens();
  const priority = task.priority ?? "none";
  const overdue = task.due_date ? isOverdue(task.due_date) : false;

  function handleDragStart(e: DragEvent<HTMLDivElement>) {
    e.dataTransfer.setData("text/plain", JSON.stringify({ id: task.id, column: task.column }));
    e.dataTransfer.effectAllowed = "move";
  }

  const dueDateStyle: CSSProperties = {
    fontSize: "0.6875rem",
    color: overdue ? t.danger : t.fgMuted,
    fontWeight: overdue ? 600 : 400,
  };

  return (
    <Card
      interactive
      padding="0.625rem 0.75rem"
      draggable
      onDragStart={handleDragStart}
      onClick={() => onTaskClick?.(task)}
      style={{ cursor: "grab", userSelect: "none" }}
    >
      <Text weight="medium" style={{ fontSize: "0.8125rem", lineHeight: 1.35, wordBreak: "break-word" }}>
        {task.title}
      </Text>

      <Inline gap="0.5rem" justify="between" style={{ marginTop: "0.375rem" }}>
        <Inline gap="0.375rem" wrap>
          {priority !== "none" && (
            <Badge tone={PRIORITY_TONE[priority] ?? "neutral"}>{priority}</Badge>
          )}
          {task.due_date && <span style={dueDateStyle}>{formatDate(task.due_date)}</span>}
        </Inline>

        {task.assignee && <Avatar name={task.assignee} size={22} title={task.assignee} />}
      </Inline>
    </Card>
  );
}

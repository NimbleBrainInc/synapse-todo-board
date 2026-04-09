import type { Board } from "../hooks/useBoards";

interface BoardSelectorProps {
  boards: Board[];
  selectedBoardId: string | null;
  onBoardChange: (boardId: string | null) => void;
  isDark: boolean;
}

/**
 * Dropdown showing all boards with name + task count.
 * Shows current board name as the selected value.
 */
export function BoardSelector({ boards, selectedBoardId, onBoardChange, isDark }: BoardSelectorProps) {
  return (
    <select
      value={selectedBoardId ?? ""}
      onChange={(e) => onBoardChange(e.target.value || null)}
      style={{
        padding: "0.4rem 0.75rem",
        borderRadius: "6px",
        border: `1px solid ${isDark ? "#3d3d5c" : "#ccc"}`,
        background: isDark ? "#1a1a2e" : "#fff",
        color: isDark ? "#e0e0e0" : "#1a1a2e",
        fontSize: "0.875rem",
        minWidth: "180px",
        cursor: "pointer",
      }}
    >
      <option value="">Select a board...</option>
      {boards.map((board) => (
        <option key={board.id} value={board.id}>
          {board.name}
          {board.task_count != null ? ` (${board.task_count})` : ""}
        </option>
      ))}
      <option disabled style={{ borderTop: `1px solid ${isDark ? "#3d3d5c" : "#ccc"}` }}>
        ──────────
      </option>
      <option value="__create__">+ Create Board</option>
    </select>
  );
}

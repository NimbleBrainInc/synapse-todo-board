import type { Board } from "../hooks/useBoards";
import { useStyleTokens } from "../tokens";

interface BoardSelectorProps {
  boards: Board[];
  selectedBoardId: string | null;
  onBoardChange: (boardId: string | null) => void;
}

/**
 * Dropdown showing all boards with name + task count.
 * Shows current board name as the selected value.
 */
export function BoardSelector({ boards, selectedBoardId, onBoardChange }: BoardSelectorProps) {
  const t = useStyleTokens();
  return (
    <select
      value={selectedBoardId ?? ""}
      onChange={(e) => onBoardChange(e.target.value || null)}
      style={{
        padding: "0.4rem 0.75rem",
        borderRadius: "6px",
        border: `1px solid ${t.border}`,
        background: t.bgSubtle,
        color: t.fg,
        fontFamily: t.fontFamily,
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
      <option disabled>──────────</option>
      <option value="__create__">+ Create Board</option>
    </select>
  );
}

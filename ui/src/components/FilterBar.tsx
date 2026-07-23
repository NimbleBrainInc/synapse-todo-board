import { useMemo } from "react";
import { Badge, TextLink } from "@nimblebrain/synapse/ui";
import { useStyleTokens } from "../tokens";

// -- Types --

export interface Filters {
  priority: string | null;
  column: string | null;
  assignee: string | null;
  overdueOnly: boolean;
}

export interface ColumnDef {
  key: string;
  label: string;
}

export interface FilterBarProps {
  filters: Filters;
  onChange: (filters: Filters) => void;
  columns: ColumnDef[];
  assignees: string[];
}

const PRIORITIES = ["critical", "high", "medium", "low", "none"];

export const EMPTY_FILTERS: Filters = {
  priority: null,
  column: null,
  assignee: null,
  overdueOnly: false,
};

export default function FilterBar({ filters, onChange, columns, assignees }: FilterBarProps) {
  const t = useStyleTokens();
  const activeCount = useMemo(() => {
    let count = 0;
    if (filters.priority) count++;
    if (filters.column) count++;
    if (filters.assignee) count++;
    if (filters.overdueOnly) count++;
    return count;
  }, [filters]);

  const selectStyle: React.CSSProperties = {
    padding: "0.35rem 0.6rem",
    borderRadius: "6px",
    border: `1px solid ${t.border}`,
    background: t.bgRaised,
    color: t.fg,
    fontFamily: t.fontFamily,
    fontSize: "0.8rem",
    minWidth: "120px",
    cursor: "pointer",
  };

  const labelStyle: React.CSSProperties = {
    fontSize: "0.75rem",
    fontWeight: 500,
    color: t.fgMuted,
    marginBottom: "2px",
  };

  return (
    <div
      className="tb-filter-bar"
      style={{
        display: "flex",
        alignItems: "flex-end",
        gap: "0.75rem",
        padding: "0.6rem 1rem",
        borderBottom: `1px solid ${t.border}`,
        background: t.bgSubtle,
        flexWrap: "wrap",
      }}
    >
      {/* Priority filter */}
      <div style={{ display: "flex", flexDirection: "column" }}>
        <span style={labelStyle}>Priority</span>
        <select
          value={filters.priority ?? ""}
          onChange={(e) => onChange({ ...filters, priority: e.target.value || null })}
          style={selectStyle}
        >
          <option value="">All</option>
          {PRIORITIES.map((p) => (
            <option key={p} value={p}>
              {p.charAt(0).toUpperCase() + p.slice(1)}
            </option>
          ))}
        </select>
      </div>

      {/* Column filter */}
      <div style={{ display: "flex", flexDirection: "column" }}>
        <span style={labelStyle}>Column</span>
        <select
          value={filters.column ?? ""}
          onChange={(e) => onChange({ ...filters, column: e.target.value || null })}
          style={selectStyle}
        >
          <option value="">All</option>
          {columns.map((c) => (
            <option key={c.key} value={c.key}>
              {c.label}
            </option>
          ))}
        </select>
      </div>

      {/* Assignee filter */}
      <div style={{ display: "flex", flexDirection: "column" }}>
        <span style={labelStyle}>Assignee</span>
        <select
          value={filters.assignee ?? ""}
          onChange={(e) => onChange({ ...filters, assignee: e.target.value || null })}
          style={selectStyle}
        >
          <option value="">All</option>
          {assignees.map((a) => (
            <option key={a} value={a}>
              {a}
            </option>
          ))}
        </select>
      </div>

      {/* Overdue only toggle */}
      <label
        style={{
          display: "flex",
          alignItems: "center",
          gap: "0.4rem",
          fontSize: "0.8rem",
          cursor: "pointer",
          color: t.fg,
          paddingBottom: "0.35rem",
        }}
      >
        <input
          type="checkbox"
          checked={filters.overdueOnly}
          onChange={(e) => onChange({ ...filters, overdueOnly: e.target.checked })}
          style={{ cursor: "pointer" }}
        />
        Overdue only
      </label>

      {/* Active filter count + clear */}
      {activeCount > 0 && (
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", paddingBottom: "0.35rem" }}>
          <Badge tone="accent">{activeCount} active</Badge>
          <TextLink tone="danger" onClick={() => onChange(EMPTY_FILTERS)}>
            Clear filters
          </TextLink>
        </div>
      )}
    </div>
  );
}

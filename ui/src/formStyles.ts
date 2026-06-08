import type { CSSProperties } from "react";
import type { ResolvedTokens } from "./tokens";

/**
 * Shared, token-driven styles for the native form controls the library doesn't
 * yet cover (text/date inputs, textareas, selects). Centralized so the task and
 * board dialogs read the same — when the library grows an `Input`/`Select`,
 * these call sites swap in one place.
 */
export function inputStyle(t: ResolvedTokens): CSSProperties {
  return {
    width: "100%",
    padding: "0.5rem",
    borderRadius: "6px",
    border: `1px solid ${t.border}`,
    background: t.bgSubtle,
    color: t.fg,
    fontFamily: t.fontFamily,
    fontSize: "0.875rem",
    boxSizing: "border-box",
  };
}

export function labelStyle(t: ResolvedTokens): CSSProperties {
  return {
    display: "block",
    fontSize: "0.75rem",
    fontWeight: 600,
    marginBottom: "0.25rem",
    color: t.fgMuted,
    textTransform: "uppercase",
    letterSpacing: "0.04em",
  };
}

export function errorStyle(t: ResolvedTokens): CSSProperties {
  return {
    padding: "0.5rem 0.75rem",
    borderRadius: "6px",
    background: t.dangerSoft,
    color: t.danger,
    fontSize: "0.8rem",
  };
}

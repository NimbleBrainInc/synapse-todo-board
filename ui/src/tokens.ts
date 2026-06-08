import { tokens as ui } from "@nimblebrain/synapse/ui";

/**
 * Todo-board token shape, backed by the shared `@nimblebrain/synapse/ui` token
 * contract instead of per-component `isDark ? "#x" : "#y"` hex tables. Every
 * value is a `var(--token, neutral-fallback)` from the library, so the host's
 * injected brand theme drives the whole app and light/dark resolve in CSS with
 * no React re-render.
 *
 * `useStyleTokens()` is a hook only by convention (so call sites read like the
 * rest of the app); it returns a static mapping because the host swaps the CSS
 * variables, not React state.
 */
export interface ResolvedTokens {
  bg: string;
  bgRaised: string;
  bgSubtle: string;
  bgHover: string;
  fg: string;
  fgMuted: string;
  fgFaint: string;
  border: string;
  borderStrong: string;
  accent: string;
  accentSoft: string;
  accentText: string;
  fontFamily: string;
  fontMono: string;
  danger: string;
  dangerSoft: string;
  success: string;
  warning: string;
}

const RESOLVED: ResolvedTokens = {
  bg: ui.bg,
  bgRaised: ui.bgRaised,
  bgSubtle: ui.bgSubtle,
  bgHover: ui.bgSubtle,
  fg: ui.fg,
  fgMuted: ui.fgMuted,
  fgFaint: ui.fgFaint,
  border: ui.border,
  borderStrong: ui.borderStrong,
  accent: ui.accent,
  accentSoft: ui.infoLight,
  accentText: ui.accentFg,
  fontFamily: ui.fontSans,
  fontMono: ui.fontMono,
  danger: ui.danger,
  dangerSoft: `color-mix(in oklab, ${ui.danger} 14%, transparent)`,
  success: ui.success,
  warning: ui.warning,
};

export function useStyleTokens(): ResolvedTokens {
  return RESOLVED;
}

/**
 * Maps a task priority onto a library `Badge` tone, so priority chips draw from
 * the shared semantic palette (host-themeable) instead of fixed hex.
 */
export const PRIORITY_TONE: Record<string, "danger" | "warning" | "warm" | "accent" | "neutral"> = {
  critical: "danger",
  high: "warning",
  medium: "warm",
  low: "accent",
  none: "neutral",
};

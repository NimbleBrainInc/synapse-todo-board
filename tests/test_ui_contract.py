"""UI → MCP contract tests.

Catches the class of drift where the UI and the MCP server disagree on the
tool surface. Two dimensions are checked:

1. *Tool name* — every static `callTool("name", ...)` site must resolve to
   a tool the live MCP server actually lists. This catches the
   `create_task`-style regression where the UI calls a tool hidden by the
   entity allowlist.

2. *Argument shape* — every key passed in the inline args object must be a
   property the tool's `inputSchema` defines. This catches the
   `create_board({data: {...}})` / `delete_board({entity_id: ...})`
   regressions where the name is valid but the shape isn't, which fail at
   runtime with a generic `invalid_input` error.

Both checks are textual — no TS AST. Dynamic call sites like
`callTool(someVar, args)` are deliberately skipped; they're opaque to
static analysis and would need runtime instrumentation to verify.

The same pattern is meant to be liftable into any synapse-app: drop this
file in, point `_UI_SRC` at the app's `ui/src/`, reuse the `mcp` fixture.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from tests.conftest import _run

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_UI_SRC = _PROJECT_ROOT / "ui" / "src"


# ---------------------------------------------------------------------------
# Textual extraction — callTool call sites and their arg literals
# ---------------------------------------------------------------------------

# Matches the preamble of a callTool invocation up to (and including) the
# comma between the two arguments. Captures the tool name literal.
_CALL_TOOL_RE = re.compile(r"""callTool\s*\(\s*["']([^"']+)["']\s*,\s*""")


def _skip_string(text: str, i: int) -> int:
    """Advance past a string literal starting at `text[i]`. Handles `"`, `'`, and backticks."""
    quote = text[i]
    i += 1
    while i < len(text):
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == quote:
            return i + 1
        i += 1
    return i  # unterminated — treat as consumed


def _capture_arg_object(text: str, start: int) -> str | None:
    """If the character at `start` opens an object literal, return its content.

    Content = the source between the outer `{` and `}`. Returns None when the
    second arg is a variable (`callTool("x", args)`) or any non-object
    expression — those are out of scope for static checking.
    """
    if start >= len(text) or text[start] != "{":
        return None
    depth = 1
    i = start + 1
    while i < len(text) and depth > 0:
        c = text[i]
        if c in '"\'`':
            i = _skip_string(text, i)
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1 : i]
        i += 1
    return None


def _top_level_keys(obj_content: str) -> set[str]:
    """Extract top-level property-name keys from an object literal's body.

    Handles:
      - explicit `key: value` pairs
      - shorthand `{ title, priority }` properties
      - nested objects / arrays / calls (skipped; only depth-0 keys count)
      - string values that contain `{`, `:`, or `,`

    Doesn't attempt to handle computed keys (`[foo]:`) or string-literal
    keys (`"foo":`). Neither is in use in this UI; the cost isn't worth it.
    """
    keys: set[str] = set()
    depth = 0
    in_key_position = True
    i = 0
    n = len(obj_content)
    while i < n:
        c = obj_content[i]
        if c in '"\'`':
            i = _skip_string(obj_content, i)
            continue
        if c in "{[(":
            depth += 1
            i += 1
            continue
        if c in "}])":
            depth -= 1
            i += 1
            continue
        if depth != 0:
            i += 1
            continue
        if c == ",":
            in_key_position = True
            i += 1
            continue
        if c == ":":
            in_key_position = False
            i += 1
            continue
        if in_key_position and (c.isalpha() or c in "_$"):
            j = i
            while j < n and (obj_content[j].isalnum() or obj_content[j] in "_$"):
                j += 1
            keys.add(obj_content[i:j])
            # Don't flip in_key_position here — shorthand ends at `,` or `}`,
            # explicit pair ends at `:`. Both transitions are handled above.
            i = j
            continue
        i += 1
    return keys


def _extract_call_sites() -> list[tuple[str, str | None, Path]]:
    """Scan every `.ts`/`.tsx` under _UI_SRC. Yield (tool_name, arg_body | None, path)."""
    sites: list[tuple[str, str | None, Path]] = []
    for src in _UI_SRC.rglob("*"):
        if src.suffix not in {".ts", ".tsx"}:
            continue
        text = src.read_text()
        rel = src.relative_to(_PROJECT_ROOT)
        for m in _CALL_TOOL_RE.finditer(text):
            name = m.group(1)
            arg_body = _capture_arg_object(text, m.end())
            sites.append((name, arg_body, rel))
    return sites


# ---------------------------------------------------------------------------
# Live tool fixture — fetch full tool defs (name + inputSchema) once per test
# ---------------------------------------------------------------------------


async def _list_tools_full(mcp) -> dict[str, dict[str, Any]]:
    """Return {name: {inputSchema: {...}}} for every listed tool."""
    from fastmcp import Client

    async with Client(mcp) as client:
        tools = await client.list_tools()
        return {t.name: {"inputSchema": t.inputSchema or {}} for t in tools}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_every_ui_call_tool_is_listed(mcp):
    """Every static `callTool("name", ...)` in the UI must resolve to a listed tool.

    "Listed" = present in `tools/list`. This is the same view the NimbleBrain
    platform bridge uses to decide whether to forward or 404 a `/v1/tools/call`
    request, so matching against it exactly mirrors production behavior.
    """
    sites = _extract_call_sites()
    assert sites, f"No callTool(...) sites found under {_UI_SRC} — check the regex or UI layout"

    listed = set(_run(_list_tools_full(mcp)).keys())
    unknown: dict[str, list[Path]] = {}
    for name, _args, path in sites:
        if name not in listed:
            unknown.setdefault(name, []).append(path)

    if unknown:
        lines = ["UI calls tools that are not listed by the MCP server:"]
        for name, paths in sorted(unknown.items()):
            locs = ", ".join(str(p) for p in paths)
            lines.append(f"  - {name!r} called from {locs}")
        # Cap the "available tools" hint so CI logs don't drown on large apps.
        preview_limit = 40
        preview = sorted(listed)[:preview_limit]
        suffix = f" (+{len(listed) - preview_limit} more)" if len(listed) > preview_limit else ""
        lines.append(f"Listed tools ({len(listed)}): {preview}{suffix}")
        raise AssertionError("\n".join(lines))


def test_every_ui_call_tool_arg_shape_matches_schema(mcp):
    """Every top-level key in the UI's inline args must be an inputSchema property.

    Catches shape drift that slips past `test_every_ui_call_tool_is_listed`:
    the tool name resolves, but the keys don't match what the schema expects.
    Historical cases this would have caught at CI time:

      - `callTool("create_board", { data: {...} })` — `data` is not a property
      - `callTool("update_task", { entity_id: ..., data: {...} })` — neither is
      - `callTool("delete_board", { entity_id: ... })` — id param is `board_id`

    Call sites whose second arg is a variable (`callTool("x", args)`) are
    skipped. Adding coverage for those requires runtime instrumentation or
    a proper TypeScript AST pass — see follow-up: generated types.
    """
    tools = _run(_list_tools_full(mcp))
    violations: list[str] = []

    for name, arg_body, path in _extract_call_sites():
        if name not in tools:
            continue  # covered by the other test
        if arg_body is None:
            continue  # dynamic arg — not statically checkable
        schema = tools[name]["inputSchema"]
        allowed = set((schema.get("properties") or {}).keys())
        used = _top_level_keys(arg_body)
        unknown = used - allowed
        if unknown:
            violations.append(
                f"  - {name!r} at {path}: unknown keys {sorted(unknown)}; "
                f"allowed: {sorted(allowed)}"
            )

    if violations:
        raise AssertionError(
            "UI callTool sites pass keys not declared in the tool's inputSchema:\n"
            + "\n".join(violations)
        )


# ---------------------------------------------------------------------------
# Parser self-tests — guard against regressions in the extractor itself
# ---------------------------------------------------------------------------


def test_top_level_keys_basic_literal():
    assert _top_level_keys('title: "foo", priority: "high"') == {"title", "priority"}


def test_top_level_keys_shorthand():
    assert _top_level_keys("title, priority, description") == {
        "title",
        "priority",
        "description",
    }


def test_top_level_keys_nested_is_flat():
    body = 'board_id: "x", data: { title: "y", tags: ["a", "b"] }, flag: true'
    assert _top_level_keys(body) == {"board_id", "data", "flag"}


def test_top_level_keys_string_with_braces_and_colons():
    body = 'title: "a: b, c {d}", count: 1'
    assert _top_level_keys(body) == {"title", "count"}


def test_capture_arg_object_balances_nested_braces():
    text = 'callTool("x", { a: { b: 1 }, c: 2 })'
    m = _CALL_TOOL_RE.search(text)
    assert m is not None
    body = _capture_arg_object(text, m.end())
    assert body is not None
    assert _top_level_keys(body) == {"a", "c"}


def test_capture_arg_object_returns_none_for_variable():
    text = "callTool('x', someArgs)"
    m = _CALL_TOOL_RE.search(text)
    assert m is not None
    assert _capture_arg_object(text, m.end()) is None

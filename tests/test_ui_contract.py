"""UI → MCP contract tests.

Catches the class of drift where the UI calls a tool name the server doesn't
expose. The motivating regression: `synapse.callTool("create_task", ...)`
shipped in the UI, but the `task` entity's manifest allowlist hides
`create_task` from `tools/list`. The NimbleBrain platform bridge rejects
unlisted tool names with 404 `tool_not_found`, so the UI failed at the
customer but passed every server-side test.

This test closes the loop by grep-extracting every `callTool(` site from the
UI source and asserting each resolves to a tool the live MCP server actually
lists. It intentionally uses a textual parse rather than a TS AST — the goal
is the same thing the customer's browser does: "does this literal tool name
exist?"

The same pattern can be lifted into any synapse-app: drop this file in,
point `_UI_SRC` at the app's `ui/src/`, reuse the `mcp` fixture.
"""

from __future__ import annotations

import re
from pathlib import Path

from tests.conftest import _list_tool_names, _run

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_UI_SRC = _PROJECT_ROOT / "ui" / "src"

# Matches `callTool("name"` or `callTool('name'` across line breaks. Captures
# the tool name literal. Dynamic names (`callTool(someVar, ...)`) are
# deliberately ignored — they're opaque to static analysis.
_CALL_TOOL_RE = re.compile(r"""callTool\s*\(\s*["']([^"']+)["']""")


def _extract_tool_calls() -> dict[str, list[Path]]:
    """Return {tool_name: [files that call it]} for every static callTool site."""
    calls: dict[str, list[Path]] = {}
    for src in _UI_SRC.rglob("*.ts*"):
        text = src.read_text()
        for name in _CALL_TOOL_RE.findall(text):
            calls.setdefault(name, []).append(src.relative_to(_PROJECT_ROOT))
    return calls


def test_every_ui_call_tool_is_listed(mcp):
    """Every static `callTool("name", ...)` in the UI must resolve to a listed tool.

    "Listed" = present in `tools/list`. This is the same view the NimbleBrain
    platform bridge uses to decide whether to forward or 404 a `/v1/tools/call`
    request, so matching against it exactly mirrors production behavior.
    """
    ui_calls = _extract_tool_calls()
    assert ui_calls, (
        f"No callTool(...) sites found under {_UI_SRC} — check the regex or UI layout"
    )

    listed = _run(_list_tool_names(mcp))
    unknown = {name: files for name, files in ui_calls.items() if name not in listed}

    if unknown:
        lines = ["UI calls tools that are not listed by the MCP server:"]
        for name, files in sorted(unknown.items()):
            locs = ", ".join(str(f) for f in files)
            lines.append(f"  - {name!r} called from {locs}")
        lines.append(f"Listed tools ({len(listed)}): {sorted(listed)}")
        raise AssertionError("\n".join(lines))

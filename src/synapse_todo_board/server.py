"""Todo Board MCP server built with Upjack + FastMCP.

Tier 2: Auto-generated entity CRUD from manifest (boards, tasks, labels).
Tier 3: Custom domain tools for task workflow (move, reorder, archive, summary).
"""

import os
from pathlib import Path

from upjack.app import UpjackApp
from upjack.server import create_server

from synapse_todo_board.tools import register_tools

_PROJECT_ROOT = Path(__file__).parent.parent.parent
manifest_path = _PROJECT_ROOT / "manifest.json"
workspace_root = os.environ.get("MPAK_WORKSPACE", "./workspace")
mcp = create_server(manifest_path, root=workspace_root)

# Skill resource — teaches the LLM how to use this server's tools
_SKILL_PATH = _PROJECT_ROOT / "SKILL.md"
_SKILL_CONTENT = _SKILL_PATH.read_text() if _SKILL_PATH.exists() else ""


@mcp.resource("skill://todo-board/usage")
def todo_board_skill() -> str:
    """Tool selection and usage guidance for the Todo Board."""
    return _SKILL_CONTENT

# Append board-scoping instructions — the agent MUST see this before any tool call
mcp._mcp_server.instructions = (
    (mcp.instructions or "")
    + "\n\nCRITICAL — Board Context: The UI visible state contains the active board "
    "(selectedBoard.id). Use it for ALL task operations:\n"
    "- Creating tasks: use create_board_task(board_id=<selectedBoard.id>, data={...}) — "
    "NEVER use create_task directly, it won't link to the board and the task will be invisible.\n"
    "- Finding tasks: use find_board_task(board_id=<selectedBoard.id>, query=...)\n"
    "- NEVER call search_tasks or list_boards — the board context is already in the visible state."
)

# Load app instance for custom tools
_app = UpjackApp.from_manifest(manifest_path, root=workspace_root)

# Register custom domain tools
register_tools(mcp, _app)

# UI resource — served to the platform as an iframe
_UI_HTML = _PROJECT_ROOT / "ui" / "dist" / "index.html"


@mcp.resource("ui://todo-board/main")
def todo_board_ui() -> str:
    """The Todo Board app UI — rendered in the platform sidebar."""
    if _UI_HTML.exists():
        return _UI_HTML.read_text()
    return "<html><body><p>UI not built. Run <code>cd ui && npm run build</code>.</p></body></html>"


# ASGI entrypoint (uvicorn / nimbletools-core)
app = mcp.http_app()

if __name__ == "__main__":
    mcp.run()

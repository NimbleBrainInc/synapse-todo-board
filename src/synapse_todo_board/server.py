"""Todo Board MCP server with FastMCP tools and an app-owned JSON store."""

import os
import logging

from fastmcp import FastMCP
from fastmcp.server.middleware import Middleware, MiddlewareContext

from synapse_todo_board.assets import asset_root
from synapse_todo_board.crud import register_store_tools
from synapse_todo_board.store import BoardStore, ChangeMarker, current_change, mark_changed

from synapse_todo_board.instructions import (
    read_custom_instructions,
    write_custom_instructions,
)
from synapse_todo_board.tools import register_tools

_PROJECT_ROOT = asset_root()
workspace_root = os.environ.get("MPAK_WORKSPACE", os.environ.get("UPJACK_ROOT", "./workspace"))
_app = BoardStore(workspace_root, _PROJECT_ROOT)
mcp = FastMCP(
    "Todo Board",
    instructions="Boards and tasks stored locally. Read skill://todo-board/usage for guidance.",
)


class BoardWriteNotifications(Middleware):
    async def on_call_tool(self, context: MiddlewareContext, call_next):
        marker = ChangeMarker()
        token = current_change.set(marker)
        try:
            return await call_next(context)
        finally:
            current_change.reset(token)
            if marker.changed and context.fastmcp_context is not None:
                try:
                    await context.fastmcp_context.session.send_resource_list_changed()
                except Exception:
                    logging.getLogger(__name__).warning(
                        "Board change notification could not be sent", exc_info=True
                    )


mcp.add_middleware(BoardWriteNotifications())
register_store_tools(mcp, _app)


@mcp.resource("upjack://context")
def todo_board_context() -> str:
    """Domain guidance; the resource URI is kept for existing clients."""
    return (_PROJECT_ROOT / "context.md").read_text()


@mcp.resource("upjack://skills/task-triage")
def todo_board_triage() -> str:
    """Task triage guidance; the resource URI is kept for existing clients."""
    return (_PROJECT_ROOT / "skills/task-triage/SKILL.md").read_text()


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
    "- Creating tasks: use create_board_task(board_id=<selectedBoard.id>, title=..., ...) — "
    "NEVER use create_task directly, it won't link to the board and the task will be invisible.\n"
    "- Finding tasks: use find_board_task(board_id=<selectedBoard.id>, query=...)\n"
    "- NEVER call search_tasks or list_boards — the board context is already in the visible state."
)

# Register custom domain tools
register_tools(mcp, _app)

# UI resource — served to the platform as an iframe
_UI_HTML = _PROJECT_ROOT / "ui" / "dist" / "index.html"


@mcp.resource("ui://todo-board/main", mime_type="text/html;profile=mcp-app")
def todo_board_ui() -> str:
    """The Todo Board app UI — rendered in the platform sidebar."""
    if _UI_HTML.exists():
        return _UI_HTML.read_text()
    return "<html><body><p>UI not built. Run <code>cd ui && npm run build</code>.</p></body></html>"


# --- Custom Instructions (NimbleBrain platform contract) ---


@mcp.resource("app://instructions", mime_type="text/markdown")
def todo_board_custom_instructions() -> str:
    """Per-bundle custom instructions for the NimbleBrain platform.

    NimbleBrain reads `app://instructions` from every active bundle on each
    prompt assembly. A non-empty body lands inside `<app-custom-instructions>`
    containment in the system prompt; empty omits the block. Storage,
    validation, and the editor UI all live in this bundle.
    """
    return read_custom_instructions(workspace_root)


@mcp.tool()
async def set_custom_instructions(text: str) -> dict[str, str]:
    """Save custom instructions for this Todo Board.

    Use sparingly — only when the user explicitly asks to save a convention
    (e.g. "always triage with the priority matrix" or "default new tasks to
    medium priority"). Empty text clears the instruction. Capped at 8 KiB.

    The saved text is surfaced to the agent on every conversation turn via
    NimbleBrain's `app://instructions` contract, so the agent picks up the
    convention without you having to repeat it.
    """
    try:
        before = read_custom_instructions(workspace_root)
        result = write_custom_instructions(workspace_root, text)
        if before != text:
            mark_changed()
        return result
    except ValueError as err:
        # 8 KiB cap → return a structured tool error rather than letting the
        # exception cross the wire as a transport-level failure. The agent
        # sees `isError: true` and can react cleanly.
        return {"status": "error", "error": str(err)}


@mcp.resource("ui://todo-board/settings", mime_type="text/html;profile=mcp-app")
def todo_board_settings_ui() -> str:
    """The settings view uses the same built Synapse app and own-server bridge."""
    if not _UI_HTML.exists():
        return todo_board_ui()
    document = _UI_HTML.read_text()
    if "<head>" not in document:
        raise ValueError("Rebuild the Todo Board UI before opening settings")
    marker = '<meta name="todo-board-view" content="settings">'
    return document.replace("<head>", "<head>" + marker, 1).replace(
        "<title>Todo Board</title>", "<title>Todo Board Settings</title>", 1
    )


# ASGI entrypoint (uvicorn / nimbletools-core)
app = mcp.http_app()


if __name__ == "__main__":
    mcp.run()

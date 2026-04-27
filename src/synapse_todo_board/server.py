"""Todo Board MCP server built with Upjack + FastMCP.

Tier 2: Auto-generated entity CRUD from manifest (boards, tasks, labels).
Tier 3: Custom domain tools for task workflow (move, reorder, archive, summary).
"""

import os
from pathlib import Path

from upjack.app import UpjackApp
from upjack.server import create_server

from synapse_todo_board.instructions import (
    read_custom_instructions,
    write_custom_instructions,
)
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
        return write_custom_instructions(workspace_root, text)
    except ValueError as err:
        # 8 KiB cap → return a structured tool error rather than letting the
        # exception cross the wire as a transport-level failure. The agent
        # sees `isError: true` and can react cleanly.
        return {"status": "error", "error": str(err)}


_SETTINGS_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Todo Board Settings</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: system-ui, -apple-system, sans-serif; padding: 0; color: #1a1a1a; background: transparent; font-size: 14px; line-height: 1.5; }
  h2 { font-size: 16px; font-weight: 600; margin-bottom: 4px; }
  p.lede { font-size: 13px; color: #555; margin-bottom: 12px; }
  .section { padding: 16px; border: 1px solid #e5e5e5; border-radius: 8px; background: #fff; }
  textarea { width: 100%; min-height: 180px; padding: 10px; border: 1px solid #ddd; border-radius: 6px; font-family: ui-monospace, SFMono-Regular, monospace; font-size: 13px; line-height: 1.5; resize: vertical; }
  .row { display: flex; gap: 8px; align-items: center; margin-top: 10px; }
  .count { font-size: 12px; color: #777; margin-left: auto; }
  .count.over { color: #b91c1c; font-weight: 500; }
  button { padding: 8px 14px; border: none; border-radius: 6px; font-size: 13px; font-weight: 500; cursor: pointer; background: #2563eb; color: #fff; }
  button:hover { background: #1d4ed8; }
  button:disabled { opacity: 0.5; cursor: not-allowed; }
  .btn-secondary { background: #f3f4f6; color: #374151; }
  .btn-secondary:hover { background: #e5e7eb; }
  .status { font-size: 12px; padding: 6px 10px; border-radius: 4px; }
  .status.ok { background: #f0fdf4; color: #166534; }
  .status.err { background: #fef2f2; color: #991b1b; }
  .loading { color: #999; font-style: italic; padding: 16px; }
</style>
</head>
<body>
<div id="root" class="loading">Loading…</div>
<script>
(function() {
  const MAX = 8 * 1024;
  let _reqId = 0;
  const _pending = {};

  function callTool(name, args) {
    return new Promise((resolve, reject) => {
      const id = ++_reqId;
      _pending[id] = { resolve, reject };
      window.parent.postMessage(
        { jsonrpc: "2.0", id, method: "tools/call", params: { name, arguments: args || {} } },
        "*",
      );
    });
  }
  function readResource(uri) {
    return new Promise((resolve, reject) => {
      const id = ++_reqId;
      _pending[id] = { resolve, reject };
      window.parent.postMessage(
        { jsonrpc: "2.0", id, method: "resources/read", params: { uri } },
        "*",
      );
    });
  }
  window.addEventListener("message", (e) => {
    const msg = e.data;
    if (!msg || !msg.jsonrpc) return;
    if (msg.id && _pending[msg.id]) {
      const { resolve, reject } = _pending[msg.id];
      delete _pending[msg.id];
      if (msg.error) reject(new Error(msg.error.message || "request failed"));
      else resolve(msg.result);
    }
  });

  // Character count for the UI; the backend enforces an 8 KiB UTF-8 byte
  // cap. For ASCII Markdown the two are equal; for emoji-heavy text the
  // server-side check may reject before the UI count reaches the limit and
  // the error surfaces in the status row.

  let lastSaved = "";

  async function init() {
    const root = document.getElementById("root");
    try {
      const result = await readResource("app://instructions");
      const body = (result && result.contents && result.contents[0] && result.contents[0].text) || "";
      lastSaved = body;
      root.classList.remove("loading");
      root.innerHTML = `
        <div class="section">
          <h2>Custom Instructions</h2>
          <p class="lede">
            Saved guidance the agent picks up on every turn — workflow conventions,
            triage rules, default priorities, anything you'd otherwise repeat in
            chat. Empty clears.
          </p>
          <textarea id="ta" placeholder="e.g. Default new tasks to 'medium' priority. Triage on Mondays only.">${
            body.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
          }</textarea>
          <div class="row">
            <button id="save">Save</button>
            <button id="reset" class="btn-secondary">Reset</button>
            <span id="count" class="count">0 / ${MAX.toLocaleString()} characters</span>
          </div>
          <div class="row">
            <span id="status"></span>
          </div>
        </div>
      `;
      const ta = document.getElementById("ta");
      const count = document.getElementById("count");
      const status = document.getElementById("status");
      const saveBtn = document.getElementById("save");
      const resetBtn = document.getElementById("reset");

      function refreshCount() {
        const chars = ta.value.length;
        count.textContent = `${chars.toLocaleString()} / ${MAX.toLocaleString()} characters`;
        count.classList.toggle("over", chars > MAX);
        saveBtn.disabled = chars > MAX || ta.value === lastSaved;
        resetBtn.disabled = ta.value === lastSaved;
      }
      ta.addEventListener("input", refreshCount);
      refreshCount();

      saveBtn.addEventListener("click", async () => {
        status.className = "status";
        status.textContent = "Saving…";
        saveBtn.disabled = true;
        try {
          await callTool("set_custom_instructions", { text: ta.value });
          lastSaved = ta.value;
          status.className = "status ok";
          status.textContent = "Saved";
          refreshCount();
          setTimeout(() => { status.textContent = ""; status.className = "status"; }, 1500);
        } catch (err) {
          status.className = "status err";
          status.textContent = String(err.message || err);
          refreshCount();
        }
      });
      resetBtn.addEventListener("click", () => {
        ta.value = lastSaved;
        refreshCount();
        status.textContent = "";
        status.className = "status";
      });
    } catch (err) {
      root.classList.remove("loading");
      root.innerHTML = `<div class="section"><h2>Custom Instructions</h2>
        <p class="lede" style="color:#b91c1c">Failed to load: ${String(err.message || err)}</p></div>`;
    }
  }
  init();
})();
</script>
</body>
</html>
"""


@mcp.resource("ui://todo-board/settings")
def todo_board_settings_ui() -> str:
    """Custom-instructions editor — rendered at /settings/apps/synapse-todo-board.

    Inline HTML for now (no separate ui/settings.html build). Communicates
    with the bundle via the platform's iframe postMessage bridge — same
    pattern Collateral's inline settings page uses.
    """
    return _SETTINGS_HTML


# ASGI entrypoint (uvicorn / nimbletools-core)
app = mcp.http_app()


if __name__ == "__main__":
    mcp.run()

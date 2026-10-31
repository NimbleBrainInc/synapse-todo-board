"""Write notifications: a write tool tells the client, everything else stays quiet.

Synapse views refresh on `notifications/resources/list_changed`. These
tests drive the server through an in-memory `fastmcp.Client` and record
every server notification it receives.
"""

from __future__ import annotations

import asyncio
import json

from fastmcp import Client, Context, FastMCP
from mcp.server.session import ServerSession
from mcp.types import ServerNotification

from synapse_todo_board.notifications import WRITE_TOOLS, NotifyOnWrite

from .conftest import _list_tool_names, _run

LIST_CHANGED = "notifications/resources/list_changed"

READ_TOOLS = {
    "get_board",
    "list_boards",
    "search_boards",
    "get_task",
    "list_tasks",
    "search_tasks",
    "query_boards_by_relationship",
    "get_related_board",
    "get_board_composite",
    "query_tasks_by_relationship",
    "get_related_task",
    "get_task_composite",
    "find_board_task",
    "board_summary",
}

# Writes no board data. The platform reads `app://instructions` on each
# prompt, and no view refetches on a notification for it.
NOT_BOARD_TOOLS = {"set_custom_instructions"}


async def _calls(
    server, calls: list[tuple[str, dict]], *, raises: tuple[str, ...] = ()
) -> list[str]:
    """Run tool calls in one session; return the notification methods seen.

    Every call must succeed unless its tool is named in `raises`.
    """
    seen: list[str] = []

    async def on_message(message):
        if isinstance(message, ServerNotification):
            seen.append(message.root.method)

    async with Client(server, message_handler=on_message) as client:
        for name, arguments in calls:
            result = await client.call_tool(name, arguments, raise_on_error=False)
            assert result.is_error == (name in raises), (name, result.content)
        await asyncio.sleep(0.05)
    return seen


# ---------------------------------------------------------------------------
# The middleware on its own
# ---------------------------------------------------------------------------


def _toy_server() -> FastMCP:
    server = FastMCP("toy")
    server.add_middleware(NotifyOnWrite(write_tools={"write", "fail", "refuse"}))

    @server.tool()
    def write() -> dict:
        return {"status": "saved"}

    @server.tool()
    def read() -> dict:
        return {"value": ""}

    @server.tool()
    def fail() -> dict:
        raise ValueError("boom")

    @server.tool()
    def refuse() -> dict:
        return {"error": "not found"}

    return server


def test_write_tool_sends_one_list_changed() -> None:
    assert _run(_calls(_toy_server(), [("write", {})])) == [LIST_CHANGED]


def test_read_tool_sends_nothing() -> None:
    assert _run(_calls(_toy_server(), [("read", {})])) == []


def test_raised_error_sends_nothing() -> None:
    assert _run(_calls(_toy_server(), [("fail", {})], raises=("fail",))) == []


def test_error_result_still_notifies() -> None:
    assert _run(_calls(_toy_server(), [("refuse", {})])) == [LIST_CHANGED]


def _request_id_server() -> FastMCP:
    server = FastMCP("toy")
    server.add_middleware(NotifyOnWrite(write_tools={"write"}))

    @server.tool()
    def write(ctx: Context) -> dict:
        return {"request_id": str(ctx.request_id)}

    return server


async def _call_write() -> dict:
    async with Client(_request_id_server()) as client:
        result = await client.call_tool("write", {})
        return json.loads(result.content[0].text)


def test_notification_is_tied_to_the_call(monkeypatch) -> None:
    sent: list[dict] = []

    async def record(self, notification, related_request_id=None):
        sent.append({"related_request_id": related_request_id})

    monkeypatch.setattr(ServerSession, "send_notification", record)
    result = _run(_call_write())
    assert [str(s["related_request_id"]) for s in sent] == [result["request_id"]]


def test_send_failure_keeps_the_tool_result(monkeypatch) -> None:
    async def explode(self, notification, related_request_id=None):
        raise RuntimeError("stream closed")

    monkeypatch.setattr(ServerSession, "send_notification", explode)
    result = _run(_call_write())
    assert set(result) == {"request_id"}


# ---------------------------------------------------------------------------
# The Todo Board server
# ---------------------------------------------------------------------------


def test_every_tool_is_classed(mcp) -> None:
    """A new tool must join WRITE_TOOLS, READ_TOOLS or NOT_BOARD_TOOLS, or this fails."""
    tools = _run(_list_tool_names(mcp))
    assert tools == WRITE_TOOLS | READ_TOOLS | NOT_BOARD_TOOLS
    assert not WRITE_TOOLS & (READ_TOOLS | NOT_BOARD_TOOLS)


def _board_with_task(mcp) -> tuple[str, str]:
    async def create() -> tuple[str, str]:
        async with Client(mcp) as client:
            board = await client.call_tool(
                "create_board", {"name": "B", "columns": [{"key": "todo", "label": "To Do"}]}
            )
            board_id = json.loads(board.content[0].text)["id"]
            task = await client.call_tool("create_board_task", {"board_id": board_id, "title": "T"})
            return board_id, json.loads(task.content[0].text)["id"]

    return _run(create())


def test_create_board_task_notifies_once(mcp) -> None:
    board_id, _ = _board_with_task(mcp)
    seen = _run(_calls(mcp, [("create_board_task", {"board_id": board_id, "title": "T"})]))
    assert seen == [LIST_CHANGED]


def test_reads_stay_quiet(mcp) -> None:
    board_id, _ = _board_with_task(mcp)
    seen = _run(
        _calls(
            mcp,
            [
                ("list_boards", {}),
                ("get_board", {"board_id": board_id}),
                ("board_summary", {"board_id": board_id}),
            ],
        )
    )
    assert seen == []


def test_write_that_reports_an_error_still_notifies(mcp) -> None:
    """`reorder_column` returns an error at the first unknown id; the board still refreshes."""
    board_id, task_id = _board_with_task(mcp)
    seen = _run(
        _calls(
            mcp,
            [
                (
                    "reorder_column",
                    {
                        "board_id": board_id,
                        "column_key": "todo",
                        "task_ids": [task_id, "tk_missing"],
                    },
                )
            ],
        )
    )
    assert seen == [LIST_CHANGED]

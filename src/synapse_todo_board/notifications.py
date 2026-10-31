"""Tell the connected client when a tool call changes board data.

Synapse views refresh on `notifications/resources/list_changed`. The
middleware sends it after each call to a tool in `WRITE_TOOLS` that does
not raise, so an open board picks up an agent's edit without a reload.
Reads send nothing, so a view's refetch cannot start a refresh loop.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

from fastmcp.server.middleware import Middleware, MiddlewareContext
from mcp.types import ResourceListChangedNotification, ServerNotification

logger = logging.getLogger(__name__)

# Every tool that can change boards, tasks or the schema. A new write tool
# must be added here, or an open board will not refresh.
WRITE_TOOLS = frozenset(
    {
        "create_board",
        "update_board",
        "delete_board",
        "update_task",
        "delete_task",
        "create_board_task",
        "move_task",
        "reorder_column",
        "archive_task",
        "batch_archive",
        "add_field",
        "seed_data",
        "rebuild_index",
    }
)


class NotifyOnWrite(Middleware):
    """Send `notifications/resources/list_changed` after a write tool call.

    A write that returns an error dict still notifies, since a tool may
    commit part of its work before it reports the error, and a spare
    refetch is cheap. A call that raises sends nothing.
    """

    def __init__(self, write_tools: Iterable[str] = WRITE_TOOLS) -> None:
        self._write_tools = frozenset(write_tools)

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        result = await call_next(context)
        ctx = context.fastmcp_context
        if context.message.name in self._write_tools and ctx is not None:
            try:
                # Tied to the call, so streamable HTTP sends it on the call's
                # own response stream, which a stateless server also has.
                await ctx.session.send_notification(
                    ServerNotification(ResourceListChangedNotification()),
                    related_request_id=ctx.request_id,
                )
            except Exception:
                logger.warning("Board change notification could not be sent", exc_info=True)
        return result

"""HTTP check that board/task writes notify the client while reads stay quiet."""

import asyncio
import json

from fastmcp import Client
from mcp.types import ServerNotification

from http_workflow import EVIDENCE, start, stop


async def exercise(url):
    notices = []
    changed = asyncio.Event()

    async def on_message(message):
        if isinstance(message, ServerNotification):
            notices.append(message.root.method)
            changed.set()

    async with Client(url, message_handler=on_message) as client:
        await client.list_tools()
        await client.call_tool("list_boards", {})
        await asyncio.sleep(0.2)
        assert not notices, f"read caused notification: {notices}"

        board = await client.call_tool(
            "create_board",
            {
                "name": "Notification check",
                "columns": [{"key": "todo", "label": "To Do"}],
            },
        )
        board_id = json.loads(board.content[0].text)["id"]
        await asyncio.wait_for(changed.wait(), timeout=3)
        assert notices == ["notifications/resources/list_changed"], notices

        changed.clear()
        await client.call_tool("list_boards", {})
        await client.call_tool(
            "query_tasks_by_relationship",
            {
                "rel": "belongs_to",
                "target_id": board_id,
            },
        )
        await asyncio.sleep(0.2)
        assert len(notices) == 1, f"read caused refresh loop: {notices}"

        await client.call_tool(
            "create_board_task",
            {
                "board_id": board_id,
                "title": "Agent edit",
            },
        )
        await asyncio.wait_for(changed.wait(), timeout=3)
        assert notices == ["notifications/resources/list_changed"] * 2, notices
        changed.clear()
        await client.call_tool("set_custom_instructions", {"text": "Keep task titles concise."})
        await asyncio.wait_for(changed.wait(), timeout=3)
        assert len(notices) == 3, notices
        await client.call_tool("set_custom_instructions", {"text": "Keep task titles concise."})
        await asyncio.sleep(0.2)
        assert len(notices) == 3, "unchanged instructions announced a write"

        changed.clear()
        await client.call_tool(
            "add_field",
            {
                "entity_type": "board",
                "field_name": "category",
                "field_type": "string",
                "default": "general",
            },
        )
        await asyncio.wait_for(changed.wait(), timeout=3)
        assert len(notices) == 4, notices
    return {
        "board": board_id,
        "notifications": notices,
        "read_notifications": 0,
        "unchanged_instruction_notifications": 0,
        "instruction_write_notifications": 1,
        "schema_write_notifications": 1,
    }


if __name__ == "__main__":
    child, url = start()
    try:
        result = asyncio.run(exercise(url))
    finally:
        stop(child)
    (EVIDENCE / "notification-receipt.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({**result, "evidence": str(EVIDENCE)}, indent=2))

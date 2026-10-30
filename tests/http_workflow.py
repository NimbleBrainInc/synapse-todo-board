"""Disposable HTTP workflow. Run with an environment containing the locked dependencies.

Uses fresh data, restarts its own child, and leaves a JSON receipt beside the logs.
The UI must already be built before this check.
"""

import asyncio
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

from fastmcp import Client
from fastmcp.exceptions import ToolError

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = Path(tempfile.mkdtemp(prefix="todo-http-"))
WORKSPACE = EVIDENCE / "workspace"
CALLED: set[str] = set()


def port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def call(client, tool, **args):
    result = await client.call_tool(tool, args)
    CALLED.add(tool)
    return json.loads(result.content[0].text)


async def exercise(url):
    async with Client(url) as client:
        names = sorted(tool.name for tool in await client.list_tools())
        assert len(names) == 28 and "create_task" not in names, names
        resources = {str(resource.uri): resource for resource in await client.list_resources()}
        assert len(resources) == 6
        for uri in ["ui://todo-board/main", "ui://todo-board/settings"]:
            assert resources[uri].mimeType == "text/html;profile=mcp-app", resources[uri]
            content = await client.read_resource(uri)
            assert "<script" in content[0].text and "UI not built" not in content[0].text
        columns = [{"key": "todo", "label": "To Do"}, {"key": "done", "label": "Done"}]
        one = await call(client, "create_board", name="One", columns=columns)
        two = await call(client, "create_board", name="Two", columns=columns)
        first = await call(client, "create_board_task", board_id=one["id"], title="First")
        second = await call(client, "create_board_task", board_id=one["id"], title="Second")
        other = await call(client, "create_board_task", board_id=two["id"], title="Other")
        assert (await call(client, "get_board", board_id=one["id"]))["id"] == one["id"]
        assert (await call(client, "update_board", board_id=one["id"], description="Checked"))[
            "description"
        ] == "Checked"
        assert one["id"] in {
            item["id"] for item in (await call(client, "list_boards", limit=None))["entities"]
        }
        assert [
            item["id"] for item in (await call(client, "search_boards", query="One"))["entities"]
        ] == [one["id"]]
        assert (
            await call(
                client, "query_boards_by_relationship", rel="belongs_to", target_id=one["id"]
            )
        )["entities"] == []
        reverse = await call(client, "get_related_board", board_id=one["id"], direction="reverse")
        assert {item["id"] for item in reverse["entities"]} == {first["id"], second["id"]}
        assert (await call(client, "get_task_composite", task_id=first["id"]))["_related"][
            "belongs_to"
        ][0]["id"] == one["id"]
        assert (await call(client, "board_summary", board_id=one["id"]))["totals"]["tasks"] == 2
        assert (await call(client, "find_board_task", board_id=one["id"], query="First"))[
            "matches"
        ][0]["id"] == first["id"]
        updated = await call(
            client, "update_task", task_id=first["id"], title="Updated", priority="high"
        )
        assert updated["priority"] == "high"
        assert (await call(client, "search_tasks", query="Updated"))["entities"][0]["id"] == first[
            "id"
        ]
        assert len((await call(client, "list_tasks", limit=None))["entities"]) == 3
        listing = await call(
            client, "query_tasks_by_relationship", rel="belongs_to", target_id=one["id"]
        )
        assert {row["id"] for row in listing["entities"]} == {first["id"], second["id"]}
        related = await call(client, "get_related_task", task_id=first["id"])
        assert related["entities"][0]["id"] == one["id"]
        assert (await call(client, "get_board_composite", board_id=one["id"]))["_related"]
        before = await call(client, "get_task", task_id=second["id"])
        invalid = await call(
            client,
            "reorder_column",
            board_id=one["id"],
            column_key="todo",
            task_ids=[second["id"], other["id"]],
        )
        assert "error" in invalid
        assert await call(client, "get_task", task_id=second["id"]) == before
        reordered = await call(
            client,
            "reorder_column",
            board_id=one["id"],
            column_key="todo",
            task_ids=[second["id"], first["id"]],
        )
        assert reordered["reordered"] == 2
        await call(client, "move_task", task_id=first["id"], target_column="done")
        completed = await call(client, "get_task", task_id=first["id"])
        assert completed["column"] == "done" and completed["completed_at"]
        await call(client, "archive_task", task_id=first["id"])
        listing = await call(
            client, "query_tasks_by_relationship", rel="belongs_to", target_id=one["id"]
        )
        assert [row["id"] for row in listing["entities"]] == [second["id"]]
        before_files = {str(p): p.read_bytes() for p in WORKSPACE.rglob("*.json")}
        try:
            await call(client, "update_task", task_id="../../outside", title="invalid")
        except ToolError:
            pass
        else:
            raise AssertionError("Traversal was accepted")
        assert before_files == {str(p): p.read_bytes() for p in WORKSPACE.rglob("*.json")}
        await call(client, "set_custom_instructions", text="Keep the board concise.")
        assert (
            await call(
                client,
                "add_field",
                entity_type="board",
                field_name="category",
                field_type="string",
                default="general",
            )
        )["success"]
        assert (await call(client, "get_board", board_id=one["id"]))["category"] == "general"
        assert (await call(client, "rebuild_index"))["success"]
        assert (await call(client, "batch_archive", board_id=one["id"], older_than_days=7))[
            "archived"
        ] == 0
        assert (await call(client, "delete_task", task_id=other["id"]))["status"] == "deleted"
        assert (await call(client, "delete_board", board_id=two["id"]))["status"] == "deleted"
        seeded = await call(client, "seed_data")
        assert seeded["loaded"] and not seeded["errors"], seeded
        assert CALLED == set(names), sorted(set(names) - CALLED)
        return {
            "tools": names,
            "tools_called": sorted(CALLED),
            "resources": sorted(resources),
            "board": one["id"],
            "second": second["id"],
            "archived": first["id"],
        }


async def verify_restart(url, result):
    async with Client(url) as client:
        assert (await call(client, "get_task", task_id=result["archived"]))["status"] == "archived"
        listing = await call(
            client, "query_tasks_by_relationship", rel="belongs_to", target_id=result["board"]
        )
        assert [row["id"] for row in listing["entities"]] == [result["second"]]
        assert (await client.read_resource("app://instructions"))[
            0
        ].text == "Keep the board concise."


def start():
    chosen = port()
    log = (EVIDENCE / f"server-{chosen}.log").open("w")
    env = {
        key: os.environ[key]
        for key in ["PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "TMPDIR", "PYTHONPATH"]
        if key in os.environ
    }
    env.update(
        MPAK_WORKSPACE=str(WORKSPACE), UPJACK_ROOT=str(WORKSPACE), PYTHONDONTWRITEBYTECODE="1"
    )
    child = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "synapse_todo_board.server:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(chosen),
        ],
        cwd=ROOT,
        env=env,
        stdout=log,
        stderr=log,
    )
    log.close()
    for _ in range(150):
        if child.poll() is not None:
            raise RuntimeError(f"Server exited; see {EVIDENCE}")
        try:
            with socket.create_connection(("127.0.0.1", chosen), timeout=0.1):
                return child, f"http://127.0.0.1:{chosen}/mcp"
        except OSError:
            time.sleep(0.1)
    child.terminate()
    child.wait(timeout=5)
    raise RuntimeError("Server did not listen")


def stop(child):
    child.terminate()
    child.wait(timeout=10)


if __name__ == "__main__":
    child, url = start()
    try:
        result = asyncio.run(exercise(url))
    finally:
        stop(child)
    before = {str(p): p.read_bytes() for p in WORKSPACE.rglob("*") if p.is_file()}
    child, url = start()
    try:
        asyncio.run(verify_restart(url, result))
    finally:
        stop(child)
    assert before == {str(p): p.read_bytes() for p in WORKSPACE.rglob("*") if p.is_file()}
    result.update(passed=True, restart_preserved_bytes=True, evidence=str(EVIDENCE))
    (EVIDENCE / "receipt.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))

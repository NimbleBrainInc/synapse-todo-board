"""Check an already-built wheel without installing it or using checkout assets.

Run with the project's Python environment: python tests/wheel_workflow.py <wheel>.
The subprocess uses synthetic data, and every Todo module must come from the wheel.
"""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import sysconfig
import tempfile
import zipfile

PROBE = r"""
import asyncio, hashlib, json, os
from pathlib import Path
import sys
from fastmcp import Client
from synapse_todo_board import assets, server

root = Path(os.environ["TODO_WHEEL_ROOT"]).resolve()
for name, module in tuple(sys.modules.items()):
    if name.startswith("synapse_todo_board") and getattr(module, "__file__", None):
        assert Path(module.__file__).resolve().is_relative_to(root), name
assert assets.asset_root().resolve() == root / "synapse_todo_board/assets"

async def exercise():
    async with Client(server.mcp) as client:
        tools = await client.list_tools()
        resources = await client.list_resources()
        assert len(tools) == 28 and len(resources) == 6
        for uri in ["upjack://context", "upjack://skills/task-triage", "skill://todo-board/usage"]:
            assert (await client.read_resource(uri))[0].text
        ui = (await client.read_resource("ui://todo-board/main"))[0]
        expected = assets.asset_root() / "ui/dist/index.html"
        assert ui.text.encode() == expected.read_bytes()
        assert ui.mimeType == "text/html;profile=mcp-app"
        settings = (await client.read_resource("ui://todo-board/settings"))[0]
        assert '<meta name="todo-board-view" content="settings">' in settings.text
        board = json.loads((await client.call_tool("create_board", {
            "name": "Wheel example", "columns": [{"key": "todo", "label": "To Do"}]
        })).content[0].text)
        task = json.loads((await client.call_tool("create_board_task", {
            "board_id": board["id"], "title": "Wheel task"
        })).content[0].text)
        fetched = await client.call_tool("get_task", {"task_id": task["id"]})
        assert json.loads(fetched.content[0].text) == task
        assert task["relationships"][0]["target"] == board["id"]
        seeded = json.loads((await client.call_tool("seed_data", {})).content[0].text)
        assert seeded["loaded"] and not seeded["errors"], seeded
        return {"tools": len(tools), "resources": len(resources),
                "ui_sha256": hashlib.sha256(ui.text.encode()).hexdigest(),
                "workspace_write_read": True, "seed_assets": True,
                "checkout_assets_used": False}

print(json.dumps(asyncio.run(exercise())))
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="todo-wheel-check-") as temporary:
        root = Path(temporary)
        package = root / "package"
        with zipfile.ZipFile(args.wheel.resolve()) as archive:
            for name in archive.namelist():
                if not (package / name).resolve().is_relative_to(package.resolve()):
                    raise ValueError(f"Wheel entry escapes package directory: {name}")
            archive.extractall(package)
        env = dict(os.environ)
        env.update(
            # Skip editable-install .pth files so they cannot shadow the wheel.
            PYTHONPATH=os.pathsep.join(
                dict.fromkeys(
                    [
                        str(package),
                        sysconfig.get_path("purelib"),
                        sysconfig.get_path("platlib"),
                    ]
                )
            ),
            PYTHONDONTWRITEBYTECODE="1",
            MPAK_WORKSPACE=str(root / "workspace"),
            UPJACK_ROOT=str(root / "workspace"),
            TODO_WHEEL_ROOT=str(package),
        )
        result = subprocess.run(
            [sys.executable, "-S", "-c", PROBE],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
        )
        if result.returncode:
            sys.stderr.write(result.stdout + result.stderr)
            return result.returncode
        print(json.dumps(json.loads(result.stdout.strip().splitlines()[-1]), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

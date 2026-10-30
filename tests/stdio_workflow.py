"""Exercise the same public tools through the packaged stdio entry point."""

import asyncio
import json
import os
import sys

from fastmcp.client.transports import StdioTransport

from http_workflow import EVIDENCE, ROOT, WORKSPACE, exercise, verify_restart


def transport():
    env = {
        key: os.environ[key]
        for key in ("PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "TMPDIR", "PYTHONPATH")
        if key in os.environ
    }
    env.update(MPAK_WORKSPACE=str(WORKSPACE), PYTHONDONTWRITEBYTECODE="1")
    return StdioTransport(
        command=sys.executable,
        args=["-m", "synapse_todo_board.server"],
        cwd=str(ROOT),
        env=env,
        keep_alive=False,
        log_file=EVIDENCE / "stdio-server.log",
    )


if __name__ == "__main__":
    result = asyncio.run(exercise(transport()))
    before = {str(path): path.read_bytes() for path in WORKSPACE.rglob("*") if path.is_file()}
    asyncio.run(verify_restart(transport(), result))
    assert before == {
        str(path): path.read_bytes() for path in WORKSPACE.rglob("*") if path.is_file()
    }
    result.update(
        passed=True, transport="stdio", restart_preserved_bytes=True, evidence=str(EVIDENCE)
    )
    (EVIDENCE / "stdio-receipt.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))

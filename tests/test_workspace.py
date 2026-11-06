"""A workspace the Upjack-backed server wrote reads unchanged through this one.

`tests/fixtures/upjack-workspace/root` was written by the server on
upstream main c2c1c33 (upjack 0.5.1, fastmcp 3.1.1, mcp 1.26.0), driven
through its own tools: create_board, create_board_task twice, update_task
with a tag and an undeclared field, then delete_task on the second task.
`reads.json` beside it holds what that server answered for each read tool on
the result. These tests copy the workspace in, go through the published tools
of this server, not the store, and compare every answer with the recording.
The seed, add_field and hidden-tool checks cover what Upjack used to do at
the server layer.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from fastmcp import Client

from synapse_todo_board.store import BoardStore
from tests.conftest import _call_tool, _list_tool_names, _run

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).parent / "fixtures/upjack-workspace"
DATA = "apps/todo-board/data"
READS = json.loads((FIXTURE / "reads.json").read_text())


def _fixture_records(folder: str) -> list[dict]:
    paths = sorted((FIXTURE / "root" / DATA / folder).glob("*.json"))
    return [json.loads(path.read_text()) for path in paths]


BOARD = _fixture_records("boards")[0]
TASKS = {task["status"]: task for task in _fixture_records("tasks")}
KEPT, DROPPED = TASKS["active"], TASKS["deleted"]
INDEX = (FIXTURE / "root" / DATA / "_index/relations.json").read_bytes()
# What get_related_task (forward) and get_related_board (reverse) hold on this
# workspace. Upjack refused both against its own output schema, so the
# recording has its error text and the answer is checked against the records.
RELATED = {"task": [BOARD], "board": [KEPT, DROPPED]}


def _copy_upjack_workspace(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    shutil.copytree(FIXTURE / "root", root, dirs_exist_ok=True)
    return root


def test_fixture_holds_a_board_a_kept_task_and_a_soft_deleted_task():
    assert KEPT["relationships"] == [{"rel": "belongs_to", "target": BOARD["id"]}]
    assert DROPPED["relationships"] == KEPT["relationships"]
    assert KEPT["legacy_custom"] == {"keep": True}
    assert json.loads(INDEX) == {
        "reverse": {
            BOARD["id"]: [
                {"source": KEPT["id"], "rel": "belongs_to"},
                {"source": DROPPED["id"], "rel": "belongs_to"},
            ]
        }
    }


@pytest.mark.parametrize("recorded", READS, ids=[f"{r['tool']}-{i}" for i, r in enumerate(READS)])
def test_every_read_tool_answers_as_the_upjack_server_did(mcp, tmp_path, recorded):
    _copy_upjack_workspace(tmp_path)

    result = _run(_call_tool(mcp, recorded["tool"], recorded["arguments"]))

    if "error" in recorded["result"]:
        assert recorded["result"]["error"].startswith("Output validation error")
        related = RELATED[recorded["tool"].removeprefix("get_related_")]
        assert result == {"entities": related, "count": len(related)}
    else:
        assert result == recorded["result"]


def test_board_summary_counts_the_kept_task_only(mcp, tmp_path):
    _copy_upjack_workspace(tmp_path)

    summary = _run(_call_tool(mcp, "board_summary", {"board_id": BOARD["id"]}))

    assert summary["board"] == {"id": BOARD["id"], "name": BOARD["name"]}
    assert summary["totals"]["tasks"] == 1
    assert [(c["key"], c["count"]) for c in summary["columns"]] == [
        ("todo", 1),
        ("doing", 0),
        ("done", 0),
    ]


def test_update_through_the_tool_keeps_the_file_shape_and_the_upjack_index(mcp, tmp_path):
    root = _copy_upjack_workspace(tmp_path)

    updated = _run(_call_tool(mcp, "update_task", {"task_id": KEPT["id"], "title": "Renamed"}))

    assert updated["title"] == "Renamed"
    assert updated["updated_at"] > KEPT["updated_at"]
    for key in KEPT.keys() - {"title", "updated_at"}:
        assert updated[key] == KEPT[key]
    saved = json.loads((root / DATA / "tasks" / f"{KEPT['id']}.json").read_text())
    assert saved == updated
    # No edge changed, so the index Upjack wrote is left exactly as it was.
    assert (root / DATA / "_index/relations.json").read_bytes() == INDEX

    rebuilt = _run(_call_tool(mcp, "rebuild_index"))

    assert rebuilt == {"success": True, "entries": 2}
    assert json.loads((root / DATA / "_index/relations.json").read_text()) == json.loads(INDEX)


def test_seed_data_loads_the_sample_boards_with_their_stable_ids(mcp):
    result = _run(_call_tool(mcp, "seed_data"))

    assert result["errors"] == []
    boards = json.loads((PROJECT_ROOT / "seed/sample-boards.json").read_text())
    tasks = json.loads((PROJECT_ROOT / "seed/sample-tasks.json").read_text())
    assert len(result["loaded"]) == len(boards) + len(tasks)
    sprint = _run(_call_tool(mcp, "get_board", {"board_id": boards[0]["id"]}))
    assert sprint["created_by"] == "system"
    on_sprint = _run(
        _call_tool(
            mcp,
            "query_tasks_by_relationship",
            {"rel": "belongs_to", "target_id": boards[0]["id"]},
        )
    )
    expected = [t for t in tasks if t["relationships"][0]["target"] == boards[0]["id"]]
    assert on_sprint["count"] == len(expected)

    again = _run(_call_tool(mcp, "seed_data"))
    assert len(again["errors"]) == len(boards)  # the fixed ids already exist


def test_add_field_writes_workspace_fields_and_reloads_them(tmp_path):
    project = tmp_path / "project"
    shutil.copytree(PROJECT_ROOT / "schemas", project / "schemas")
    store = BoardStore(tmp_path / "workspace", project)
    board = store.create_entity("board", {"name": "B", "columns": [{"key": "todo", "label": "T"}]})

    result = store.add_field("task", "estimate", "integer", 0, "Points", required=True)

    assert result == {
        "success": True,
        "entity_type": "task",
        "field": {"name": "estimate", "type": "integer", "default": 0, "required": True},
    }
    saved = json.loads(
        (tmp_path / "workspace/apps/todo-board/schemas/task.fields.json").read_text()
    )
    assert saved["fields"]["estimate"] == {
        "type": "integer",
        "default": 0,
        "description": "Points",
        "required": True,
    }
    schema = store.app_schemas["task"]
    assert "estimate" in schema["required"]
    assert schema["allOf"] == [{"$ref": "https://upjack.dev/schemas/v1/upjack-entity.schema.json"}]
    task = store.create_entity(
        "task",
        {
            "title": "T",
            "column": "todo",
            "relationships": [{"rel": "belongs_to", "target": board["id"]}],
        },
    )
    assert task["estimate"] == 0
    assert store.add_field("task", "estimate", "string", "") == {
        "error": "Field 'estimate' already exists with type 'integer'"
    }
    assert "reserved" in store.add_field("task", "status", "string", "")["error"]
    assert "Invalid field_name" in store.add_field("task", "Bad-Name", "string", "")["error"]
    assert "not compatible" in store.add_field("task", "count", "integer", "x")["error"]


def test_add_field_tool_refuses_before_touching_the_schema(mcp):
    before = (PROJECT_ROOT / "schemas/task.schema.json").read_bytes()

    result = _run(
        _call_tool(
            mcp,
            "add_field",
            {"entity_type": "task", "field_name": "id", "field_type": "string", "default": ""},
        )
    )

    assert result == {"error": "Field 'id' is a reserved base entity field"}
    assert (PROJECT_ROOT / "schemas/task.schema.json").read_bytes() == before


def test_create_task_is_hidden_from_the_list_but_still_callable(mcp):
    assert "create_task" not in _run(_list_tool_names(mcp))

    async def call():
        async with Client(mcp) as client:
            result = await client.call_tool("create_task", {"title": "Loose", "column": "todo"})
            return json.loads(result.content[0].text)

    task = _run(call())
    assert task["id"].startswith("tk_")
    assert task["relationships"] == []


def test_context_and_skill_resources_keep_their_uris(mcp):
    async def read(uri: str) -> str:
        async with Client(mcp) as client:
            return (await client.read_resource(uri))[0].text

    assert _run(read("upjack://context")) == (PROJECT_ROOT / "context.md").read_text()
    assert (
        _run(read("upjack://skills/task-triage"))
        == (PROJECT_ROOT / "skills/task-triage/SKILL.md").read_text()
    )

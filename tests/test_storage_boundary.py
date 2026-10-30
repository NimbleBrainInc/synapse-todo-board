"""Persistence and nonmutation checks for the app-owned store."""

import json
import os
from pathlib import Path
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, BrokenBarrierError, Event

import pytest
from fastmcp.exceptions import ToolError

from tests.conftest import _call_tool, _run


def board(mcp, name="Board"):
    return _run(
        _call_tool(
            mcp, "create_board", {"name": name, "columns": [{"key": "todo", "label": "To Do"}]}
        )
    )


def task(mcp, board_id, title):
    return _run(_call_tool(mcp, "create_board_task", {"board_id": board_id, "title": title}))


def test_server_runs_when_upjack_is_unavailable(tmp_path):
    # This fails if any runtime path still imports the removed dependency.
    code = """
import asyncio, importlib.abc, sys
class RejectUpjack(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "upjack" or fullname.startswith("upjack."):
            raise ImportError("Upjack is unavailable")
sys.meta_path.insert(0, RejectUpjack())
from fastmcp import Client
from synapse_todo_board.server import mcp
async def check():
    async with Client(mcp) as client:
        assert "create_board_task" in {tool.name for tool in await client.list_tools()}
asyncio.run(check())
"""
    env = {**os.environ, "MPAK_WORKSPACE": str(tmp_path), "UPJACK_ROOT": str(tmp_path)}
    result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_reorder_invalid_later_task_does_not_change_earlier_task(mcp):
    b = board(mcp)
    first = task(mcp, b["id"], "first")
    second = task(mcp, b["id"], "second")
    before = _run(_call_tool(mcp, "get_task", {"task_id": second["id"]}))
    result = _run(
        _call_tool(
            mcp,
            "reorder_column",
            {
                "board_id": b["id"],
                "column_key": "todo",
                "task_ids": [second["id"], "tk_00000000000000000000000000"],
            },
        )
    )
    assert "error" in result
    assert _run(_call_tool(mcp, "get_task", {"task_id": second["id"]})) == before
    assert first["position"] == 0


def test_invalid_update_does_not_change_saved_entity(mcp, tmp_path):
    b = board(mcp)
    t = task(mcp, b["id"], "kept")
    path = tmp_path / "workspace/apps/todo-board/data/tasks" / f"{t['id']}.json"
    before = path.read_bytes()
    with pytest.raises(ToolError):
        _run(_call_tool(mcp, "update_task", {"task_id": t["id"], "priority": "invalid"}))
    assert path.read_bytes() == before


@pytest.mark.parametrize("kind,identifier", [("board", "board_id"), ("task", "task_id")])
def test_explicit_hard_delete_removes_only_selected_record(mcp, tmp_path, kind, identifier):
    b = board(mcp)
    entity = b if kind == "board" else task(mcp, b["id"], "kept")
    folder = "boards" if kind == "board" else "tasks"
    path = tmp_path / "workspace/apps/todo-board/data" / folder / f"{entity['id']}.json"
    kept = board(mcp, "Unrelated")
    kept_path = tmp_path / "workspace/apps/todo-board/data/boards" / f"{kept['id']}.json"
    before = kept_path.read_bytes()
    deleted = _run(_call_tool(mcp, f"delete_{kind}", {identifier: entity["id"], "hard": True}))

    assert deleted == entity
    assert not path.exists()
    assert kept_path.read_bytes() == before


def test_default_delete_preserves_record_and_custom_fields(mcp, tmp_path):
    from synapse_todo_board.server import _app

    b = board(mcp)
    path = tmp_path / "workspace/apps/todo-board/data/boards" / f"{b['id']}.json"
    _app.update_entity("board", b["id"], {"custom": "keep"})
    deleted = _app.delete_entity("board", b["id"])
    assert path.is_file()
    assert deleted["status"] == "deleted"
    assert json.loads(path.read_text())["custom"] == "keep"


def test_reverse_related_survives_a_hard_deleted_target(mcp, tmp_path):
    b = board(mcp)
    child = task(mcp, b["id"], "Still references its board")
    path = tmp_path / "workspace/apps/todo-board/data/tasks" / f"{child['id']}.json"
    before = path.read_bytes()
    _run(_call_tool(mcp, "delete_board", {"board_id": b["id"], "hard": True}))

    related = _run(
        _call_tool(
            mcp,
            "get_related_board",
            {
                "board_id": b["id"],
                "direction": "reverse",
            },
        )
    )
    assert related["entities"] == [child]
    assert path.read_bytes() == before


def test_rebuild_index_cannot_publish_a_snapshot_older_than_a_concurrent_create(mcp, monkeypatch):
    from synapse_todo_board.server import _app

    b = board(mcp)
    all_records = _app._all
    scanned, resume_scan, creator_probed, creation_finished = Event(), Event(), Event(), Event()
    lock_probe = []

    def pause_after_task_scan(kind):
        records = all_records(kind)
        if kind == "task":
            scanned.set()
            assert resume_scan.wait(timeout=5)
        return records

    def create_during_rebuild():
        acquired = _app.lock.acquire(blocking=False)
        lock_probe.append(acquired)
        creator_probed.set()
        try:
            record = _app.create_entity(
                "task",
                {
                    "title": "Created during rebuild",
                    "column": "todo",
                    "relationships": [{"rel": "belongs_to", "target": b["id"]}],
                },
            )
            creation_finished.set()
            return record
        finally:
            if acquired:
                _app.lock.release()

    monkeypatch.setattr(_app, "_all", pause_after_task_scan)
    with ThreadPoolExecutor(max_workers=2) as pool:
        rebuilding = pool.submit(_app.rebuild_index)
        assert scanned.wait(timeout=5)
        creating = pool.submit(create_during_rebuild)
        try:
            assert creator_probed.wait(timeout=5)
            # On the unlocked baseline, finish the create before publishing the
            # paused snapshot. With serialization, release the scan so the
            # blocked create can proceed and invalidate the derived index.
            if lock_probe[0]:
                assert creation_finished.wait(timeout=5)
        finally:
            resume_scan.set()
        assert rebuilding.result(timeout=10)["success"]
        created = creating.result(timeout=10)

    assert _app.get_entity("task", created["id"])["title"] == "Created during rebuild"
    index = _app.path("apps/todo-board/data/_index/relations.json")
    if index.exists():
        entries = json.loads(index.read_text())["reverse"].get(b["id"], [])
        assert {"source": created["id"], "rel": "belongs_to"} in entries


def test_entity_paths_cannot_escape_workspace(mcp, tmp_path):
    outside = tmp_path / "outside.json"
    outside.write_text('{"private":"keep"}')
    with pytest.raises(ToolError):
        _run(_call_tool(mcp, "get_task", {"task_id": "../../../../../../outside"}))
    with pytest.raises(ToolError):
        _run(
            _call_tool(
                mcp, "update_task", {"task_id": "../../../../../../outside", "title": "changed"}
            )
        )
    assert outside.read_text() == '{"private":"keep"}'


def test_symlink_entity_cannot_read_or_replace_outside_file(mcp, tmp_path):
    b = board(mcp)
    t = task(mcp, b["id"], "kept")
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps(t))
    entity = tmp_path / "workspace/apps/todo-board/data/tasks" / f"{t['id']}.json"
    entity.unlink()
    entity.symlink_to(outside)
    before = outside.read_bytes()
    for name, args in [
        ("get_task", {"task_id": t["id"]}),
        ("update_task", {"task_id": t["id"], "title": "changed"}),
    ]:
        with pytest.raises(ToolError):
            _run(_call_tool(mcp, name, args))
    assert outside.read_bytes() == before


def test_legacy_record_custom_fields_and_timestamps_survive_update(tmp_path):
    from synapse_todo_board.store import BoardStore

    store = BoardStore(tmp_path, Path(__file__).resolve().parents[1])
    path = tmp_path / "apps/todo-board/data/tasks/tk_00000000000000000000SEED01.json"
    path.parent.mkdir(parents=True)
    original = {
        "id": "tk_00000000000000000000SEED01",
        "type": "task",
        "version": 1,
        "created_at": "2026-01-02T03:04:05Z",
        "updated_at": "2026-01-02T03:04:05Z",
        "created_by": "user",
        "status": "active",
        "title": "Legacy",
        "column": "todo",
        "relationships": [{"rel": "belongs_to", "target": "bd_00000000000000000000SEED01"}],
        "private_extension": {"keep": True},
    }
    path.write_text(json.dumps(original))
    loaded = store.get_entity("task", original["id"])
    assert loaded["private_extension"] == {"keep": True}
    updated = store.update_entity("task", original["id"], {"title": "Updated"})
    for key in ["id", "type", "created_at", "created_by", "relationships", "private_extension"]:
        assert updated[key] == original[key]


def test_schema_defaults_apply_when_creating_after_add_field(tmp_path):
    import shutil
    from synapse_todo_board.store import BoardStore

    project = tmp_path / "project"
    shutil.copytree(Path(__file__).resolve().parents[1] / "schemas", project / "schemas")
    store = BoardStore(tmp_path / "workspace", project)
    original_schema = (project / "schemas/board.schema.json").read_bytes()
    assert store.add_field("board", "department", "string", "General")["success"]
    assert (project / "schemas/board.schema.json").read_bytes() == original_schema
    extension = tmp_path / "workspace/apps/todo-board/schemas/board.schema.json"
    assert set(json.loads(extension.read_text())["fields"]) == {"department"}
    bundled = json.loads((project / "schemas/board.schema.json").read_text())
    bundled["properties"]["new_base_field"] = {"type": "string", "default": "current"}
    (project / "schemas/board.schema.json").write_text(json.dumps(bundled))
    reopened = BoardStore(tmp_path / "workspace", project)
    created = reopened.create_entity(
        "board", {"name": "New", "columns": [{"key": "todo", "label": "To Do"}]}
    )
    assert created["department"] == "General"
    assert created["new_base_field"] == "current"


def test_invalid_schema_field_metadata_leaves_no_override(tmp_path):
    from synapse_todo_board.store import BoardStore

    project = Path(__file__).resolve().parents[1]
    store = BoardStore(tmp_path, project)
    for required, description in [("yes", "valid"), (True, 42)]:
        assert "error" in store.add_field(
            "board", "department", "string", "General", description, required
        )
        assert not (tmp_path / "apps/todo-board/schemas/board.schema.json").exists()
    BoardStore(tmp_path, project)


def test_open_board_reads_all_tasks_and_keeps_positions_unique_past_fifty(mcp):
    from synapse_todo_board.server import _app
    from synapse_todo_board.tools.create_board_task import create_board_task

    b = _app.create_entity(
        "board", {"name": "Large", "columns": [{"key": "todo", "label": "To Do"}]}
    )
    tasks = [create_board_task(_app, b["id"], {"title": f"Task {n}"}) for n in range(52)]
    assert [row["position"] for row in tasks] == list(range(52))

    visible = _run(
        _call_tool(
            mcp,
            "query_tasks_by_relationship",
            {
                "rel": "belongs_to",
                "target_id": b["id"],
                "limit": None,
            },
        )
    )
    assert visible["count"] == 52
    assert (
        len(
            _run(
                _call_tool(
                    mcp,
                    "query_tasks_by_relationship",
                    {
                        "rel": "belongs_to",
                        "target_id": b["id"],
                        "limit": 50,
                    },
                )
            )["entities"]
        )
        == 50
    )


def test_concurrent_board_task_creates_choose_distinct_positions(mcp, monkeypatch):
    from synapse_todo_board.server import _app
    from synapse_todo_board.tools.create_board_task import create_board_task

    b = _app.create_entity(
        "board", {"name": "Concurrent", "columns": [{"key": "todo", "label": "To Do"}]}
    )
    query = _app.query_by_relationship
    both_read = Barrier(2)

    def pause_after_read(*args, **kwargs):
        result = query(*args, **kwargs)
        try:
            both_read.wait(timeout=0.1)
        except BrokenBarrierError:
            pass
        return result

    monkeypatch.setattr(_app, "query_by_relationship", pause_after_read)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda title: create_board_task(_app, b["id"], {"title": title}), ["one", "two"]
            )
        )
    assert {task["position"] for task in results} == {0, 1}


def test_concurrent_reorders_do_not_mix_two_position_sequences(mcp, monkeypatch):
    from synapse_todo_board.server import _app
    from synapse_todo_board.tools.reorder_column import reorder_column

    b = board(mcp)
    first, second = task(mcp, b["id"], "First"), task(mcp, b["id"], "Second")
    update = _app.update_entity
    first_writes = Barrier(2)

    def pause_after_first_write(kind, entity_id, data):
        result = update(kind, entity_id, data)
        if data == {"position": 0}:
            try:
                first_writes.wait(timeout=0.1)
            except BrokenBarrierError:
                pass
        return result

    monkeypatch.setattr(_app, "update_entity", pause_after_first_write)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda ids: reorder_column(_app, b["id"], "todo", ids),
                [[first["id"], second["id"]], [second["id"], first["id"]]],
            )
        )
    assert all(result["reordered"] == 2 for result in results)
    assert {_app.get_entity("task", record["id"])["position"] for record in (first, second)} == {
        0,
        1,
    }


def test_concurrent_moves_append_at_distinct_positions(mcp, monkeypatch):
    from synapse_todo_board.server import _app
    from synapse_todo_board.tools.create_board_task import create_board_task
    from synapse_todo_board.tools.move_task import move_task

    b = _app.create_entity(
        "board",
        {
            "name": "Concurrent moves",
            "columns": [
                {"key": "todo", "label": "To Do"},
                {"key": "done", "label": "Done"},
            ],
        },
    )
    tasks = [create_board_task(_app, b["id"], {"title": title}) for title in ["one", "two"]]
    list_entities = _app.list_entities
    both_read = Barrier(2)

    def pause_after_read(*args, **kwargs):
        result = list_entities(*args, **kwargs)
        try:
            both_read.wait(timeout=0.1)
        except BrokenBarrierError:
            pass
        return result

    monkeypatch.setattr(_app, "list_entities", pause_after_read)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda item: move_task(_app, item["id"], "done"), tasks))
    assert {result["task"]["position"] for result in results} == {0, 1}

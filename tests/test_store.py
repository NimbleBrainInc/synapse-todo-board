"""Storage tests for `BoardStore`, called directly on a temporary workspace.

`tests/fixtures/legacy-workspace.json` holds one board and one task in the
shape Upjack writes them, including a custom field Upjack never declared.
"""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest
from jsonschema import ValidationError
from upjack.app import UpjackApp

from synapse_todo_board.store import BoardStore

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LEGACY = json.loads((Path(__file__).parent / "fixtures/legacy-workspace.json").read_text())
DATA = "apps/todo-board/data"


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "workspace"
    for kind, folder in [("board", "boards"), ("task", "tasks")]:
        path = root / DATA / folder / f"{LEGACY[kind]['id']}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(LEGACY[kind], indent=2) + "\n")
    return root


@pytest.fixture
def store(workspace):
    return BoardStore(workspace, PROJECT_ROOT)


def record_path(root, kind, entity_id):
    return root / DATA / ("boards" if kind == "board" else "tasks") / f"{entity_id}.json"


def on_board(title):
    return {
        "title": title,
        "column": "todo",
        "relationships": [{"rel": "belongs_to", "target": LEGACY["board"]["id"]}],
    }


def test_loads_the_app_schemas_without_fetching_the_remote_base(tmp_path):
    task_schema = json.loads((PROJECT_ROOT / "schemas/task.schema.json").read_text())
    assert task_schema["allOf"] == [
        {"$ref": "https://upjack.dev/schemas/v1/upjack-entity.schema.json"}
    ]

    store = BoardStore(tmp_path, PROJECT_ROOT)

    for kind in ("board", "task"):
        base = store.schemas[kind]["allOf"][0]
        assert "$ref" not in base
        assert base["title"] == "Todo Board record"


def test_legacy_record_keeps_custom_fields_and_created_at_through_update(store, workspace):
    legacy = LEGACY["task"]

    loaded = store.get_entity("task", legacy["id"])
    assert loaded["legacy_custom"] == {"keep": True}

    updated = store.update_entity("task", legacy["id"], {"title": "Renamed", "created_at": "x"})
    for key in ("id", "type", "created_at", "created_by", "relationships", "legacy_custom"):
        assert updated[key] == legacy[key]
    assert updated["title"] == "Renamed"
    assert updated["updated_at"] > legacy["updated_at"]
    saved = json.loads(record_path(workspace, "task", legacy["id"]).read_text())
    assert saved == updated


def test_legacy_record_missing_defaulted_fields_reads_with_the_defaults(store, workspace):
    legacy = {k: v for k, v in LEGACY["task"].items() if k not in {"tags", "priority"}}
    record_path(workspace, "task", legacy["id"]).write_text(json.dumps(legacy))

    loaded = store.get_entity("task", legacy["id"])

    assert loaded["tags"] == []
    assert loaded["priority"] == "none"


def test_create_writes_the_upjack_record_layout(store, workspace):
    board = store.create_entity(
        "board", {"name": "New", "columns": [{"key": "todo", "label": "To Do"}]}
    )

    assert board["id"].startswith("bd_")
    assert board["type"] == "board"
    assert board["status"] == "active"
    assert board["created_at"] == board["updated_at"]
    saved = json.loads(record_path(workspace, "board", board["id"]).read_text())
    assert saved == board


def test_invalid_update_leaves_the_file_unchanged(store, workspace):
    path = record_path(workspace, "task", LEGACY["task"]["id"])
    before = path.read_bytes()

    with pytest.raises(ValidationError):
        store.update_entity("task", LEGACY["task"]["id"], {"priority": "urgent"})

    assert path.read_bytes() == before
    assert [p.name for p in path.parent.iterdir()] == [path.name]


def test_a_failed_write_leaves_the_file_unchanged_and_no_temp_file(store, workspace, monkeypatch):
    path = record_path(workspace, "task", LEGACY["task"]["id"])
    before = path.read_bytes()

    def fail_midway(value, stream, **options):
        stream.write("{")
        raise OSError("disk full")

    monkeypatch.setattr(json, "dump", fail_midway)
    with pytest.raises(OSError, match="disk full"):
        store.update_entity("task", LEGACY["task"]["id"], {"title": "Changed"})

    assert path.read_bytes() == before
    assert [p.name for p in path.parent.iterdir()] == [path.name]


def test_writes_give_records_the_mode_a_plain_write_would(store, workspace):
    probe = workspace / "probe"
    probe.write_text("")
    task = record_path(workspace, "task", LEGACY["task"]["id"])
    task.chmod(0o640)

    board = store.create_entity(
        "board", {"name": "New", "columns": [{"key": "todo", "label": "To Do"}]}
    )
    store.update_entity("task", LEGACY["task"]["id"], {"title": "Changed"})

    mode = stat.S_IMODE(record_path(workspace, "board", board["id"]).stat().st_mode)
    assert mode == stat.S_IMODE(probe.stat().st_mode)
    assert stat.S_IMODE(task.stat().st_mode) == 0o640


def test_default_delete_keeps_the_record_and_marks_it_deleted(store, workspace):
    path = record_path(workspace, "task", LEGACY["task"]["id"])
    # A value today's schema rejects must not block a soft delete.
    path.write_text(json.dumps({**LEGACY["task"], "priority": "urgent"}))

    deleted = store.delete_entity("task", LEGACY["task"]["id"])

    assert deleted["status"] == "deleted"
    saved = json.loads(path.read_text())
    assert saved["status"] == "deleted"
    assert saved["legacy_custom"] == {"keep": True}
    assert store.list_entities("task") == []


def test_explicit_hard_delete_removes_only_the_selected_record(store, workspace):
    other = store.create_entity(
        "board", {"name": "Other", "columns": [{"key": "todo", "label": "To Do"}]}
    )
    other_path = record_path(workspace, "board", other["id"])
    task_path = record_path(workspace, "task", LEGACY["task"]["id"])
    kept = {p: p.read_bytes() for p in (other_path, task_path)}

    store.delete_entity("board", LEGACY["board"]["id"], hard=True)

    assert not record_path(workspace, "board", LEGACY["board"]["id"]).exists()
    assert {p: p.read_bytes() for p in kept} == kept
    with pytest.raises(FileNotFoundError, match=f"^Entity not found: {LEGACY['board']['id']}$"):
        store.get_entity("board", LEGACY["board"]["id"])


def test_reverse_related_survives_a_hard_deleted_target(store, workspace):
    board_id = LEGACY["board"]["id"]
    store.delete_entity("board", board_id, hard=True)

    related = store.get_related(board_id, direction="reverse")

    assert [record["id"] for record in related] == [LEGACY["task"]["id"]]
    assert store.get_related(LEGACY["task"]["id"]) == []


def test_rebuild_index_writes_the_upjack_reverse_index(store, workspace):
    result = store.rebuild_index()

    assert result == {"success": True, "entries": 1}
    index = json.loads((workspace / DATA / "_index/relations.json").read_text())
    assert index == {
        "reverse": {LEGACY["board"]["id"]: [{"source": LEGACY["task"]["id"], "rel": "belongs_to"}]}
    }


def test_upjack_finds_every_task_after_store_writes(store, workspace):
    upjack = UpjackApp.from_manifest(PROJECT_ROOT / "manifest.json", root=workspace)
    board_id = LEGACY["board"]["id"]
    upjack.query_by_relationship("task", "belongs_to", board_id)

    store.update_entity("task", LEGACY["task"]["id"], {"title": "Changed"})
    store.create_entity("task", on_board("From the store"))
    upjack.create_entity("task", on_board("From Upjack"))

    found = upjack.query_by_relationship("task", "belongs_to", board_id)
    assert sorted(task["title"] for task in found) == ["Changed", "From Upjack", "From the store"]


@pytest.mark.parametrize("entity_id", ["../../../../outside", "tk_short", "bd_" + "0" * 26])
def test_ids_that_are_not_task_ids_are_rejected(store, entity_id):
    with pytest.raises(ValueError):
        store.get_entity("task", entity_id)
    with pytest.raises(ValueError):
        store.update_entity("task", entity_id, {"title": "changed"})


def test_symlinked_record_cannot_read_or_replace_a_file_outside(store, workspace, tmp_path):
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps(LEGACY["task"]))
    path = record_path(workspace, "task", LEGACY["task"]["id"])
    path.unlink()
    path.symlink_to(outside)
    before = outside.read_bytes()

    with pytest.raises(ValueError):
        store.get_entity("task", LEGACY["task"]["id"])
    with pytest.raises(ValueError):
        store.update_entity("task", LEGACY["task"]["id"], {"title": "changed"})

    assert outside.read_bytes() == before
    assert path.is_symlink()


def test_a_scan_skips_files_that_are_not_records(store, workspace, tmp_path):
    tasks = workspace / DATA / "tasks"
    (tasks / "notes.json").write_text("{}")
    (tasks / "tk_00000000000000000000SEED02.json").write_text("[]")
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps(LEGACY["task"]))
    (tasks / "tk_00000000000000000000SEED03.json").symlink_to(outside)
    expected = [LEGACY["task"]["id"]]

    assert [task["id"] for task in store.list_entities("task")] == expected
    found = store.query_by_relationship("task", "belongs_to", LEGACY["board"]["id"])
    assert [task["id"] for task in found] == expected
    assert store.rebuild_index()["entries"] == 1

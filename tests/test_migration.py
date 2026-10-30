"""Operator migration preserves fields without editing source or records."""

from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from synapse_todo_board.migration import apply_migration, plan_migration
from synapse_todo_board.store import BoardStore

PROJECT = Path(__file__).resolve().parents[1]


@pytest.fixture
def legacy(tmp_path):
    source = tmp_path / "source"
    schemas = source / "schemas"
    schemas.mkdir(parents=True)
    for entity in ("board", "task"):
        schema = json.loads((PROJECT / "schemas" / f"{entity}.schema.json").read_text())
        schema["allOf"] = [{"$ref": "https://upjack.dev/schemas/v1/upjack-entity.schema.json"}]
        (schemas / f"{entity}.schema.json").write_text(json.dumps(schema))
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return source, workspace


def add_field(source, entity, name="category", definition=None):
    path = source / "schemas" / f"{entity}.schema.json"
    value = json.loads(path.read_text())
    value["properties"][name] = definition or {"type": "string", "default": "general"}
    value.setdefault("required", []).append(name)
    path.write_text(json.dumps(value))


def test_plan_is_read_only_and_apply_preserves_source_records_and_existing_fields(legacy):
    source, workspace = legacy
    store = BoardStore(workspace, PROJECT)
    board = store.create_entity(
        "board", {"name": "Existing", "columns": [{"key": "todo", "label": "To Do"}]}
    )
    store.add_field("board", "owner", "string", "unassigned")
    record_path = workspace / "apps/todo-board/data/boards" / f"{board['id']}.json"
    before = record_path.read_bytes()
    add_field(source, "board")
    schema_path = source / "schemas/board.schema.json"
    old_schema = schema_path.read_bytes()

    plan = plan_migration(source, workspace)
    assert plan["version"] == 1
    assert plan["updates"]["apps/todo-board/schemas/board.schema.json"]["fields"] == {
        "owner": {"type": "string", "default": "unassigned", "required": True},
        "category": {"type": "string", "default": "general", "required": True},
    }
    assert "category" not in store._read_extensions("board")
    assert record_path.read_bytes() == before

    assert apply_migration(source, workspace, plan["planHash"])["filesChanged"] == 1
    reopened = BoardStore(workspace, PROJECT)
    assert reopened.get_entity("board", board["id"])["category"] == "general"
    assert reopened.get_entity("board", board["id"])["owner"] == "unassigned"
    assert record_path.read_bytes() == before
    assert schema_path.read_bytes() == old_schema
    assert plan_migration(source, workspace)["updates"] == {}


def test_changed_plan_is_rejected_before_any_schema_write(legacy):
    source, workspace = legacy
    add_field(source, "board")
    plan = plan_migration(source, workspace)
    add_field(source, "task", "estimate", {"type": "integer", "default": 0})
    with pytest.raises(ValueError, match="plan changed"):
        apply_migration(source, workspace, plan["planHash"])
    assert not (workspace / "apps/todo-board/schemas").exists()


def test_plan_cannot_be_applied_to_another_identical_workspace(legacy, tmp_path):
    source, workspace = legacy
    add_field(source, "board")
    plan = plan_migration(source, workspace)
    other = tmp_path / "other-workspace"
    other.mkdir()
    with pytest.raises(ValueError, match="plan changed"):
        apply_migration(source, other, plan["planHash"])
    assert not (other / "apps").exists()


def test_module_cli_uses_reviewed_hash_and_returns_json(legacy):
    source, workspace = legacy
    add_field(source, "board")
    command = [
        sys.executable,
        "-m",
        "synapse_todo_board.migration",
        "--legacy-source",
        str(source),
        "--workspace",
        str(workspace),
    ]
    planned = subprocess.run(command, capture_output=True, text=True, check=True)
    plan = json.loads(planned.stdout)
    assert not (workspace / "apps").exists()
    applied = subprocess.run(
        [*command, "--apply", "--expected-plan-hash", plan["planHash"]],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(applied.stdout) == {"version": 1, "applied": True, "filesChanged": 1}
    assert "category" in BoardStore(workspace, PROJECT).schemas["board"]["properties"]


@pytest.mark.parametrize(
    "bad",
    [
        {"type": "integer", "default": "wrong"},
        {"type": "string", "default": "x", "pattern": ".*"},
    ],
)
def test_invalid_second_schema_prevents_all_writes(legacy, bad):
    source, workspace = legacy
    add_field(source, "board")
    add_field(source, "task", definition=bad)
    with pytest.raises(ValueError):
        plan_migration(source, workspace)
    assert not (workspace / "apps").exists()


def test_existing_field_conflict_is_rejected_without_changing_override(legacy):
    source, workspace = legacy
    store = BoardStore(workspace, PROJECT)
    store.add_field("board", "category", "string", "other")
    target = workspace / "apps/todo-board/schemas/board.schema.json"
    before = target.read_bytes()
    add_field(source, "board")
    with pytest.raises(ValueError, match="conflicts"):
        plan_migration(source, workspace)
    assert target.read_bytes() == before


def test_existing_base_schema_edit_is_not_treated_as_a_field_addition(legacy):
    source, workspace = legacy
    path = source / "schemas/board.schema.json"
    schema = json.loads(path.read_text())
    schema["properties"]["name"]["type"] = "integer"
    path.write_text(json.dumps(schema))
    with pytest.raises(ValueError, match="existing fields"):
        plan_migration(source, workspace)
    assert not (workspace / "apps").exists()


def test_schema_symlink_is_rejected(legacy, tmp_path):
    source, workspace = legacy
    path = source / "schemas/board.schema.json"
    outside = tmp_path / "outside.json"
    shutil.copyfile(path, outside)
    path.unlink()
    path.symlink_to(outside)
    before = outside.read_bytes()
    with pytest.raises(ValueError, match="symlinks"):
        plan_migration(source, workspace)
    assert outside.read_bytes() == before


def test_actual_legacy_add_field_inline_schema_is_supported(legacy):
    source, workspace = legacy
    generated = PROJECT / "tests/fixtures/legacy-board.schema.json"
    (source / "schemas/board.schema.json").write_bytes(generated.read_bytes())
    plan = plan_migration(source, workspace)
    assert plan["updates"]["apps/todo-board/schemas/board.schema.json"]["fields"]["category"] == {
        "type": "string",
        "default": "general",
        "required": True,
    }
    assert apply_migration(source, workspace, plan["planHash"])["filesChanged"] == 1
    assert "category" in BoardStore(workspace, PROJECT).schemas["board"]["properties"]


def test_modified_legacy_inline_base_is_rejected(legacy):
    source, workspace = legacy
    generated = json.loads((PROJECT / "tests/fixtures/legacy-board.schema.json").read_text())
    generated["allOf"][0]["properties"]["status"]["enum"].append("other")
    (source / "schemas/board.schema.json").write_text(json.dumps(generated))
    with pytest.raises(ValueError, match="base reference"):
        plan_migration(source, workspace)
    assert not (workspace / "apps").exists()


def test_actual_upjack_record_fixture_survives_read_update_and_restart(tmp_path):
    # This fixture was generated through the prior Upjack implementation, then
    # rewritten with stable IDs and timestamps for a reproducible public test.
    fixture = json.loads((PROJECT / "tests/fixtures/legacy-workspace.json").read_text())
    BOARD, TASK = fixture["board"], fixture["task"]

    for entity, record in (("boards", BOARD), ("tasks", TASK)):
        path = tmp_path / f"apps/todo-board/data/{entity}/{record['id']}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(deepcopy(record)))
    store = BoardStore(tmp_path, PROJECT)
    loaded = store.get_entity("task", TASK["id"])
    assert loaded["legacy_custom"] == TASK["legacy_custom"]
    store.update_entity("task", TASK["id"], {"title": "Updated"})
    restarted = BoardStore(tmp_path, PROJECT)
    saved = restarted.get_entity("task", TASK["id"])
    for key in ("id", "created_at", "created_by", "relationships", "legacy_custom"):
        assert saved[key] == TASK[key]
    assert saved["title"] == "Updated"
    assert restarted.get_related(BOARD["id"], direction="reverse")[0]["id"] == TASK["id"]

"""Board and task records, kept in the existing workspace JSON layout.

Records live at ``apps/todo-board/data/{boards,tasks}/<id>.json`` under the
workspace root, exactly where Upjack wrote them, so a workspace Upjack wrote
reads back unchanged. This is the one storage path for the server and every
tool.
"""

from __future__ import annotations

import fcntl
import json
import operator
import os
import re
import stat
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any

from jsonschema import Draft202012Validator, ValidationError
from ulid import ULID

ENTITIES = {"board": ("boards", "bd"), "task": ("tasks", "tk")}
IMMUTABLE = {"id", "type", "version", "created_at", "created_by"}
# The fields the store manages on every record. Tool inputs never carry them,
# and add_field refuses to declare one.
BASE_FIELDS = frozenset(
    {
        "id",
        "type",
        "version",
        "created_at",
        "updated_at",
        "created_by",
        "status",
        "tags",
        "source",
        "relationships",
    }
)
INDEX = "apps/todo-board/data/_index/relations.json"
BASE_REF = "https://upjack.dev/schemas/v1/upjack-entity.schema.json"
COMPARISONS = {"$gt": operator.gt, "$gte": operator.ge, "$lt": operator.lt, "$lte": operator.le}
FIELD_TYPES: dict[str, type | tuple[type, ...]] = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
}
FIELD_NAME = re.compile(r"^[a-z][a-z0-9_]*$")

Record = dict[str, Any]


def _timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _matches_filter(entity: Record, filters: Record | None) -> bool:
    for field, expected in (filters or {}).items():
        value = entity.get(field)
        if not isinstance(expected, dict):
            if value != expected:
                return False
            continue
        for condition, operand in expected.items():
            if condition == "$exists":
                okay = (field in entity and value is not None) == operand
            elif condition == "$ne":
                okay = value != operand
            elif condition == "$in":
                okay = value in operand
            elif condition == "$contains":
                okay = isinstance(value, list) and operand in value
            elif condition in COMPARISONS:
                try:
                    okay = value is not None and COMPARISONS[condition](value, operand)
                except TypeError:
                    okay = False
            else:
                raise ValueError(f"Unsupported filter operator: {condition}")
            if not okay:
                return False
    return True


class SchemaExtensionError(RuntimeError):
    """Workspace declarations cannot be safely merged with the installed schema.

    Not a ``ValueError``, so callers that treat a bad ID or record as "not found"
    do not hide a failure that affects every record of that kind.
    """


def _unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate schema extension key: {key}")
        result[key] = value
    return result


class BoardStore:
    """Read and write board and task records under one workspace root."""

    def __init__(self, root: str | Path, project_root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.project_root = Path(project_root).resolve()
        self.lock = RLock()
        self.base_schema = json.loads(
            (self.project_root / "schemas/entity.schema.json").read_text()
        )
        # app_schemas include workspace fields; schemas compose the base record
        # into them for validation and for the output schemas tools publish.
        self.app_schemas: dict[str, Record] = {}
        self.schemas: dict[str, Record] = {}
        for kind in ENTITIES:
            self._load_schema(kind)

    def _fields_path(self, kind: str) -> Path:
        return self._path(f"apps/todo-board/schemas/{kind}.fields.json")

    def _read_fields(self, kind: str) -> dict[str, Any]:
        try:
            path = self._fields_path(kind)
            data = json.loads(path.read_text(), object_pairs_hook=_unique_keys)
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as error:
            raise SchemaExtensionError(f"Invalid {kind} schema extensions: {error}") from None
        if (
            not isinstance(data, dict)
            or set(data) != {"version", "fields"}
            or type(data["version"]) is not int
            or data["version"] != 1
            or not isinstance(data["fields"], dict)
        ):
            raise SchemaExtensionError(f"Invalid {kind} schema extensions")
        return data["fields"]

    def _read_schema(self, kind: str, fields: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            schema = json.loads(self._schema_path(kind).read_text())
        except (OSError, ValueError):
            raise SchemaExtensionError(f"Cannot load {kind} bundled schema") from None
        if not isinstance(schema, dict) or not isinstance(schema.get("properties", {}), dict):
            raise SchemaExtensionError(f"Invalid {kind} bundled schema")
        if fields is None:
            fields = self._read_fields(kind)
        properties = schema.setdefault("properties", {})
        for name, field in fields.items():
            if (
                not re.fullmatch(r"[a-z][a-z0-9_]*", name)
                or name in BASE_FIELDS
                or name in self.base_schema.get("properties", {})
                or name in properties
            ):
                raise SchemaExtensionError(
                    f"Invalid or colliding {kind} schema extension: {name}"
                    f" in {self._fields_path(kind)}"
                )
            if (
                not isinstance(field, dict)
                or not {"type", "default", "required"} <= field.keys()
                or field.keys() - {"type", "default", "required", "description"}
                or not isinstance(field["type"], str)
                or field["type"] not in FIELD_TYPES
                or not isinstance(field["required"], bool)
                or not isinstance(field.get("description", ""), str)
            ):
                raise SchemaExtensionError(f"Invalid {kind} schema extension: {name}")
            if not Draft202012Validator({"type": field["type"]}).is_valid(field["default"]):
                raise SchemaExtensionError(f"Invalid {kind} schema extension default: {name}")
            # JSON permits no NaN or infinity, including inside array/object defaults.
            try:
                json.dumps(field["default"], allow_nan=False)
            except (ValueError, TypeError):
                raise SchemaExtensionError(
                    f"Invalid {kind} schema extension default: {name}"
                ) from None
            properties[name] = {key: value for key, value in field.items() if key != "required"}
            if field["required"]:
                schema.setdefault("required", []).append(name)
        return schema

    def _schema_path(self, kind: str) -> Path:
        return self.project_root / "schemas" / f"{kind}.schema.json"

    def _load_schema(self, kind: str, schema: Record | None = None) -> None:
        # The app schemas compose the remote Upjack base entity through allOf.
        # Swap that one entry for the local copy so loading never needs the network.
        if schema is None:
            schema = self._read_schema(kind)
        self.app_schemas[kind] = deepcopy(schema)
        schema["allOf"] = [
            self.base_schema if part.get("$ref") == BASE_REF else part
            for part in schema.get("allOf", [])
        ]
        self.schemas[kind] = schema

    def _path(self, relative: str) -> Path:
        path = self.root / relative
        if not path.resolve().is_relative_to(self.root):
            raise ValueError("Path escapes workspace root")
        return path

    def _entity_path(self, kind: str, entity_id: str) -> Path:
        plural, prefix = ENTITIES[kind]
        if not re.fullmatch(prefix + r"_[0-9A-HJKMNP-TV-Z]{26}", entity_id):
            raise ValueError(f"Invalid {kind} ID")
        return self._path(f"apps/todo-board/data/{plural}/{entity_id}.json")

    @staticmethod
    def _atomic(path: Path, value: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".todo-{ULID()}.tmp")
        # Mode 0o666 lets the umask apply, as it does to a plain write.
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
        try:
            with os.fdopen(fd, "w") as stream:
                if path.exists():
                    os.fchmod(stream.fileno(), stat.S_IMODE(path.stat().st_mode))
                json.dump(value, stream, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _save(self, kind: str, record: Record, old_edges: list, validate: bool = True) -> Record:
        if validate:
            self._load_schema(kind)
            schema = self.schemas[kind]
            record = self._hydrate(kind, record, schema)
            Draft202012Validator(schema).validate(record)
        self._atomic(self._entity_path(kind, record["id"]), record)
        # Upjack patches this index on its own writes and trusts it on reads,
        # so keep it whole. It holds every status, so only edge changes matter.
        if old_edges != record.get("relationships", []) or not self._path(INDEX).exists():
            self.rebuild_index()
        return deepcopy(record)

    def _hydrate(self, kind: str, record: Record, schema: Record | None = None) -> Record:
        if schema is None:
            self._load_schema(kind)
            schema = self.schemas[kind]
        record = deepcopy(record)
        for part in [*schema.get("allOf", []), schema]:
            for field, definition in part.get("properties", {}).items():
                if field not in record and "default" in definition:
                    record[field] = deepcopy(definition["default"])
        return record

    def create_entity(self, kind: str, data: Record, created_by: str = "agent") -> Record:
        """Create a record. A supplied ID must be new and well formed."""
        with self.lock:
            data = deepcopy(data)
            supplied_id = data.pop("id", None)
            entity_id = supplied_id or f"{ENTITIES[kind][1]}_{ULID()}"
            path = self._entity_path(kind, entity_id)
            if path.exists():
                raise ValueError(f"Entity already exists: {entity_id}")
            timestamp = _timestamp()
            record = {
                "version": 1,
                "created_at": timestamp,
                "updated_at": timestamp,
                "created_by": created_by,
                "status": "active",
                "tags": [],
                "relationships": [],
                **data,
                "id": entity_id,
                "type": kind,
            }
            return self._save(kind, self._hydrate(kind, record), [])

    def get_entity(self, kind: str, entity_id: str) -> Record:
        """Read one record, filling in missing schema defaults."""
        with self.lock:
            try:
                record = json.loads(self._entity_path(kind, entity_id).read_text())
            except FileNotFoundError:
                raise FileNotFoundError(f"Entity not found: {entity_id}") from None
            return self._hydrate(kind, record)

    def update_entity(self, kind: str, entity_id: str, data: Record) -> Record:
        """Merge fields into a record. Immutable fields are ignored."""
        with self.lock:
            record = self.get_entity(kind, entity_id)
            old_edges = record.get("relationships", [])
            record.update({k: v for k, v in data.items() if k not in IMMUTABLE})
            record["updated_at"] = _timestamp()
            return self._save(kind, record, old_edges)

    def _all(self, kind: str) -> list[Record]:
        # One schema read per listing, so every record gets the same defaults.
        with self.lock:
            self._load_schema(kind)
            schema = self.schemas[kind]
        directory = self._path(f"apps/todo-board/data/{ENTITIES[kind][0]}")
        records = []
        for path in sorted(directory.glob("*.json")):
            with self.lock:
                try:
                    record = json.loads(self._entity_path(kind, path.stem).read_text())
                    if not isinstance(record, dict):
                        continue
                except (OSError, TypeError, ValueError):
                    # Skip unreadable records, never shared schema failures.
                    continue
                records.append(self._hydrate(kind, record, schema))
        return records

    def list_entities(
        self, kind: str, status: str = "active", limit: int | None = None
    ) -> list[Record]:
        """List records with one status, most recently updated first."""
        records = [record for record in self._all(kind) if record.get("status", "active") == status]
        ordered = sorted(records, key=lambda record: record.get("updated_at", ""), reverse=True)
        return ordered if limit is None else ordered[: max(0, limit)]

    def delete_entity(self, kind: str, entity_id: str, hard: bool = False) -> Record:
        """Mark a record deleted, or remove its file when ``hard`` is set."""
        with self.lock:
            record = self.get_entity(kind, entity_id)
            if hard:
                # Only an explicit hard delete removes a file, and only this one.
                self._entity_path(kind, entity_id).unlink()
                self.rebuild_index()
                return record
            # As in Upjack, a soft delete skips validation, so a record that
            # predates the current schema can still be deleted.
            record["status"] = "deleted"
            record["updated_at"] = _timestamp()
            return self._save(kind, record, record.get("relationships", []), validate=False)

    def search_entities(
        self,
        kind: str,
        query: str | None = None,
        filter: Record | None = None,
        sort: str = "-updated_at",
        limit: int = 20,
    ) -> list[Record]:
        """Search string fields and filter. Deleted records need a status filter."""
        records = [
            record
            for record in self._all(kind)
            if ((filter and "status" in filter) or record.get("status") != "deleted")
            and (
                not query
                or any(query.lower() in v.lower() for v in record.values() if isinstance(v, str))
            )
            and _matches_filter(record, filter)
        ]
        field = sort.lstrip("-")

        def sort_key(record: Record) -> tuple:
            value = record.get(field)
            return (value is not None, isinstance(value, str), value if value is not None else "")

        return sorted(records, key=sort_key, reverse=sort.startswith("-"))[: max(0, limit)]

    def query_by_relationship(
        self,
        kind: str,
        rel: str,
        target_id: str,
        filter: Record | None = None,
        limit: int | None = None,
    ) -> list[Record]:
        """List active records of one kind with a ``rel`` edge to ``target_id``."""
        records = [
            record
            for record in self._all(kind)
            if record.get("status", "active") == "active"
            and _matches_filter(record, filter)
            and any(
                edge.get("rel") == rel and edge.get("target") == target_id
                for edge in record.get("relationships", [])
            )
        ]
        return records if limit is None else records[: max(0, limit)]

    def _kind(self, entity_id: str) -> str:
        for kind, (_, prefix) in ENTITIES.items():
            if entity_id.startswith(prefix + "_"):
                return kind
        raise ValueError("Unknown entity ID prefix")

    def _resolve(self, entity_id: str) -> Record | None:
        try:
            return self.get_entity(self._kind(entity_id), entity_id)
        except (FileNotFoundError, ValueError):
            return None

    def get_related(
        self, entity_id: str, rel: str | None = None, direction: str = "forward"
    ) -> list[Record]:
        """Follow a record's edges, or find the records whose edges point at it."""
        if direction == "reverse":
            return [
                record
                for kind in ENTITIES
                for record in self._all(kind)
                if any(
                    edge.get("target") == entity_id and (rel is None or edge.get("rel") == rel)
                    for edge in record.get("relationships", [])
                )
            ]
        if direction != "forward":
            raise ValueError("Direction must be forward or reverse")
        source = self.get_entity(self._kind(entity_id), entity_id)
        found = [
            self._resolve(edge.get("target", ""))
            for edge in source.get("relationships", [])
            if rel is None or edge.get("rel") == rel
        ]
        return [record for record in found if record]

    def get_composite(self, kind: str, entity_id: str, depth: int = 1) -> Record:
        """Read a record with its related records under ``_related``."""
        entity = self.get_entity(kind, entity_id)
        related: dict[str, list[Record]] = {}
        if depth < 1:
            return {**entity, "_related": related}
        for edge in entity.get("relationships", []):
            found = self._resolve(edge.get("target", ""))
            if edge.get("rel") and found:
                related.setdefault(edge["rel"], []).append(found)
        for source in self.get_related(entity_id, direction="reverse"):
            for edge in source.get("relationships", []):
                if edge.get("target") == entity_id and edge.get("rel"):
                    related.setdefault("~" + edge["rel"], []).append(source)
        return {**entity, "_related": related}

    def rebuild_index(self) -> Record:
        """Rewrite the reverse index Upjack reads, from every record's edges."""
        with self.lock:
            reverse: dict[str, list[dict[str, str]]] = {}
            for kind in ENTITIES:
                for record in self._all(kind):
                    for edge in record.get("relationships", []):
                        if not edge.get("rel") or not edge.get("target"):
                            continue
                        entry = {"source": record["id"], "rel": edge["rel"]}
                        entries = reverse.setdefault(edge["target"], [])
                        if entry not in entries:
                            entries.append(entry)
            self._atomic(self._path(INDEX), {"reverse": reverse})
            return {"success": True, "entries": sum(map(len, reverse.values()))}

    def seed(self, seed_dir: str | Path) -> Record:
        """Create every record in the ``*.json`` files under ``seed_dir``.

        A file holds one record or a list. Each keeps its ``id`` when it has
        one, so seed files can refer to each other; the store sets the other
        base fields. Records that fail validation or already exist are
        reported, and the rest still load.
        """
        seed_dir = Path(seed_dir)
        if not seed_dir.exists():
            return {"error": f"Seed directory not found: {seed_dir}"}
        loaded: list[str] = []
        errors: list[str] = []
        for file in sorted(seed_dir.glob("*.json")):
            raw = json.loads(file.read_text())
            for item in raw if isinstance(raw, list) else [raw]:
                kind = item.get("type")
                if not kind:
                    errors.append(f"{file.name}: missing 'type' field")
                    continue
                data = {
                    k: v
                    for k, v in item.items()
                    if k not in {"type", "created_at", "updated_at", "created_by"}
                }
                try:
                    record = self.create_entity(kind, data, created_by="system")
                    loaded.append(f"{kind}: {record['id']}")
                except (ValueError, KeyError, ValidationError) as error:
                    errors.append(f"{file.name} ({kind}): {error}")
        return {"loaded": loaded, "errors": errors}

    def add_field(
        self,
        kind: str,
        field_name: str,
        field_type: str,
        default: Any,
        description: str = "",
        required: bool = True,
    ) -> Record:
        """Save a field in the workspace and reload the composed schema.

        Missing fields take their defaults in memory; existing values and
        record files remain unchanged.
        """
        if not FIELD_NAME.fullmatch(field_name):
            return {"error": f"Invalid field_name '{field_name}'. Must match [a-z][a-z0-9_]*"}
        if field_name in BASE_FIELDS:
            return {"error": f"Field '{field_name}' is a reserved base entity field"}
        if field_type not in FIELD_TYPES:
            return {"error": f"Invalid field_type '{field_type}'. Allowed: {sorted(FIELD_TYPES)}"}
        if not isinstance(default, FIELD_TYPES[field_type]) or (
            field_type != "boolean" and isinstance(default, bool)
        ):
            return {
                "error": f"Default value {default!r} is not compatible with type '{field_type}'"
            }
        if kind not in ENTITIES:
            return {"error": f"Unknown entity type '{kind}'"}
        if not isinstance(required, bool) or not isinstance(description, str):
            return {"error": "required must be boolean and description must be string"}
        with self.lock:
            path = self._fields_path(kind)
            lock_path = self._path(f"apps/todo-board/schemas/{kind}.fields.lock")
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            # The lock is the flock, not the file: the kernel releases it when
            # the holder exits, so a killed writer leaves nothing to clean up.
            fd = os.open(lock_path, os.O_CREAT | os.O_WRONLY, 0o600)
            try:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    return {"error": f"Schema extension writer already holds {kind}.fields.lock"}
                fields = self._read_fields(kind)
                schema = self._read_schema(kind, fields)
                properties = {
                    **self.base_schema.get("properties", {}),
                    **schema.get("properties", {}),
                }
                if field_name in properties:
                    existing = properties[field_name].get("type")
                    if existing and existing != field_type:
                        return {
                            "error": f"Field '{field_name}' already exists with type '{existing}'"
                        }
                    return {"error": f"Field '{field_name}' already exists"}
                definition: dict[str, Any] = {
                    "type": field_type,
                    "default": deepcopy(default),
                    "required": required,
                }
                if description:
                    definition["description"] = description
                fields[field_name] = definition
                schema = self._read_schema(kind, fields)
                self._atomic(path, {"version": 1, "fields": fields})
                self._load_schema(kind, schema)
            finally:
                os.close(fd)
        return {
            "success": True,
            "entity_type": kind,
            "field": {
                "name": field_name,
                "type": field_type,
                "default": default,
                "required": required,
            },
        }

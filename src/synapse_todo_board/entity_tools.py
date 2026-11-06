"""The entity tools and resources the manifest describes, served from BoardStore.

Upjack generated these from the manifest at startup. This module does the
same from the same manifest block, with the same tool names, descriptions,
parameter schemas, output schemas and ``{"entities": [...], "count": n}``
envelopes, so a caller sees no change. Six CRUD tools and three relationship
tools per entity, plus ``seed_data``, ``add_field`` and ``rebuild_index``;
``upjack://context`` and ``upjack://skills/<name>`` resources keep their
URIs so a host that reads them keeps working.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from copy import deepcopy
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.tools import Tool, ToolResult
from mcp.types import TextContent

from synapse_todo_board.store import BASE_FIELDS, BASE_REF, BoardStore, Record

TOOL_NAMES = {
    "create": "create_{name}",
    "get": "get_{name}",
    "update": "update_{name}",
    "list": "list_{plural}",
    "search": "search_{plural}",
    "delete": "delete_{name}",
    "query_by_relationship": "query_{plural}_by_relationship",
    "get_related": "get_related_{name}",
    "get_composite": "get_{name}_composite",
}


def _envelope(entities: list[Record], **extra: Any) -> Record:
    return {"entities": entities, "count": len(entities), **extra}


def _input_schema(schema: Record, *, for_update: bool = False) -> Record:
    """Project an entity schema onto a tool input: the caller's fields only."""
    result = deepcopy(schema)
    result.pop("$schema", None)
    result.pop("$id", None)
    result["allOf"] = [part for part in result.get("allOf", []) if part.get("$ref") != BASE_REF]
    if not result["allOf"]:
        del result["allOf"]
    if "properties" in result:
        result["properties"] = {
            k: v for k, v in result["properties"].items() if k not in BASE_FIELDS
        }
    if for_update:
        result.pop("required", None)
    elif "required" in result:
        result["required"] = [r for r in result["required"] if r not in BASE_FIELDS]
        if not result["required"]:
            del result["required"]
    return result


def _output_schema(schema: Record) -> Record:
    """The composed record schema, as a tool output schema."""
    result = deepcopy(schema)
    result.pop("$schema", None)
    for part in result.get("allOf", []):
        part.pop("$schema", None)
    result.setdefault("type", "object")
    return result


def _list_output_schema(schema: Record | None) -> Record:
    """The ``{entities, count}`` envelope; untyped items when the kind varies."""
    return {
        "type": "object",
        "properties": {
            "entities": {
                "type": "array",
                "items": _output_schema(schema) if schema else {"type": "object"},
            },
            "count": {"type": "integer", "description": "Number of entities returned"},
        },
        "required": ["entities", "count"],
    }


def _raw_tool(
    *,
    name: str,
    description: str,
    parameters: Record,
    handler: Callable[[Record], Record],
    output_schema: Record | None = None,
) -> Tool:
    """A tool whose input schema is given as JSON Schema rather than a signature."""

    async def run(self: Tool, arguments: Record) -> ToolResult:
        # A host may pass an object or array argument as its JSON text.
        parsed: Record = {}
        for key, value in arguments.items():
            if isinstance(value, str) and value.startswith(("{", "[")):
                try:
                    parsed[key] = json.loads(value)
                except ValueError:
                    parsed[key] = value
            else:
                parsed[key] = value
        result = handler(parsed)
        text = json.dumps(result, default=str)
        return ToolResult(
            content=[TextContent(type="text", text=text)], structured_content=json.loads(text)
        )

    tool_cls = type(f"_{name}_tool", (Tool,), {"run": run})
    return tool_cls(
        name=name, description=description, parameters=parameters, output_schema=output_schema
    )


def _register_crud(mcp: FastMCP, store: BoardStore, entity: Record) -> None:
    name, prefix = entity["name"], entity["prefix"]
    plural = entity.get("plural", name + "s")
    id_hint = f"IDs start with {prefix}_"
    id_param = f"{name}_id"
    id_property = {"type": "string", "description": f"{name} ID ({prefix}_...)"}
    schema = store.app_schemas[name]
    entity_out = _output_schema(store.schemas[name])
    list_out = _list_output_schema(store.schemas[name])
    examples = [
        {k: v for k, v in example.items() if k not in BASE_FIELDS}
        for example in schema.get("examples", [])
        if isinstance(example, dict)
    ]

    create_params = _input_schema(schema)
    create_params.setdefault("type", "object")
    if examples:
        create_params["examples"] = deepcopy(examples)
    mcp.add_tool(
        _raw_tool(
            name=f"create_{name}",
            description=f"Create a new {name}. {id_hint}.",
            parameters=create_params,
            handler=lambda args: store.create_entity(name, args),
            output_schema=entity_out,
        )
    )

    mcp.add_tool(
        _raw_tool(
            name=f"get_{name}",
            description=f"Get a {name} by ID. {id_hint}.",
            parameters={
                "type": "object",
                "properties": {id_param: id_property},
                "required": [id_param],
                "examples": [{id_param: f"{prefix}_01HXXX"}],
            },
            handler=lambda args: store.get_entity(name, args[id_param]),
            output_schema=entity_out,
        )
    )

    update_params: Record = {
        "type": "object",
        "properties": {
            id_param: id_property,
            **_input_schema(schema, for_update=True).get("properties", {}),
        },
        "required": [id_param],
    }
    if examples:
        update_params["examples"] = [
            {id_param: f"{prefix}_01HXXX", **example} for example in examples
        ]
    mcp.add_tool(
        _raw_tool(
            name=f"update_{name}",
            description=(
                f"Update a {name} by ID. Merges fields by default — pass any subset "
                f"of fields to change. Unknown fields are merged onto the entity "
                f"as-is (the schema does not enforce additionalProperties=false). "
                f"{id_hint}."
            ),
            parameters=update_params,
            handler=lambda args: store.update_entity(
                name, args[id_param], {k: v for k, v in args.items() if k != id_param}
            ),
            output_schema=entity_out,
        )
    )

    @mcp.tool(
        name=f"list_{plural}",
        description=(
            f"List {plural}. Filters by status (default: active). Returns newest first. {id_hint}."
        ),
        output_schema=list_out,
    )
    def list_tool(status: str = "active", limit: int = 50) -> Record:
        entities = store.list_entities(name, status=status, limit=limit)
        return _envelope(entities, status_filter=status, limit=limit)

    @mcp.tool(
        name=f"search_{plural}",
        description=(
            f"Search {plural} with text query and/or structured filters. "
            f"Text query matches across all string fields (case-insensitive). "
            f"Filters support: direct equality, $gt, $gte, $lt, $lte, $ne, $in, "
            f"$contains, $exists. Sort with '-field' for descending. {id_hint}."
        ),
        output_schema=list_out,
    )
    def search_tool(
        query: str | None = None,
        filter: dict[str, Any] | None = None,
        sort: str = "-updated_at",
        limit: int = 20,
    ) -> Record:
        entities = store.search_entities(name, query=query, filter=filter, sort=sort, limit=limit)
        return _envelope(entities, query=query, limit=limit)

    mcp.add_tool(
        _raw_tool(
            name=f"delete_{name}",
            description=(
                f"Delete a {name} by ID. Soft delete by default (sets status to 'deleted'). "
                f"Set hard=true to permanently remove. {id_hint}."
            ),
            parameters={
                "type": "object",
                "properties": {
                    id_param: id_property,
                    "hard": {
                        "type": "boolean",
                        "description": "Permanently remove instead of soft delete.",
                        "default": False,
                    },
                },
                "required": [id_param],
                "examples": [{id_param: f"{prefix}_01HXXX"}],
            },
            handler=lambda args: store.delete_entity(
                name, args[id_param], hard=args.get("hard", False)
            ),
            output_schema=entity_out,
        )
    )


def _register_relationships(mcp: FastMCP, store: BoardStore, entity: Record) -> None:
    name, prefix = entity["name"], entity["prefix"]
    plural = entity.get("plural", name + "s")
    id_param = f"{name}_id"
    id_property = {"type": "string", "description": f"{name} ID ({prefix}_...)"}
    entity_out = _output_schema(store.schemas[name])
    list_out = _list_output_schema(store.schemas[name])

    @mcp.tool(
        name=f"query_{plural}_by_relationship",
        description=(
            f"Find {plural} that have a specific relationship pointing to a target entity. "
            f"For example, find all {plural} that 'belongs_to' a given entity."
        ),
        output_schema=list_out,
    )
    def query_by_relationship(
        rel: str, target_id: str, filter: dict[str, Any] | None = None, limit: int = 50
    ) -> Record:
        return _envelope(
            store.query_by_relationship(name, rel, target_id, filter=filter, limit=limit)
        )

    mcp.add_tool(
        _raw_tool(
            name=f"get_related_{name}",
            description=(
                f"Follow relationship edges from a {name}. "
                f"'forward' returns entities this {name} points to. "
                f"'reverse' returns entities that point to this {name}."
            ),
            parameters={
                "type": "object",
                "properties": {
                    id_param: id_property,
                    "rel": {
                        "type": "string",
                        "description": "Relationship type to follow. Omit to follow all.",
                    },
                    "direction": {
                        "type": "string",
                        "description": "'forward' or 'reverse'.",
                        "default": "forward",
                    },
                },
                "required": [id_param],
            },
            handler=lambda args: _envelope(
                store.get_related(
                    args[id_param], rel=args.get("rel"), direction=args.get("direction", "forward")
                )
            ),
            # Related records are of other kinds, so this envelope leaves the
            # item schema open. Upjack published the entity's own schema here
            # and its server then refused every real answer against it.
            output_schema=_list_output_schema(None),
        )
    )

    mcp.add_tool(
        _raw_tool(
            name=f"get_{name}_composite",
            description=(
                f"Load a {name} with all related entities in one call. "
                f"Returns the entity with a '_related' key containing forward "
                f"relationships (keyed by rel name) and reverse relationships "
                f"(keyed by ~rel name)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    id_param: id_property,
                    "depth": {
                        "type": "integer",
                        "description": "Traversal depth (default 1).",
                        "default": 1,
                    },
                },
                "required": [id_param],
            },
            handler=lambda args: store.get_composite(
                name, args[id_param], depth=args.get("depth", 1)
            ),
            output_schema=entity_out,
        )
    )


def _register_utilities(mcp: FastMCP, store: BoardStore, upjack: Record) -> None:
    if upjack.get("seed"):
        seed_dir = store.project_root / upjack["seed"].get("data", "seed/")

        @mcp.tool(
            name="seed_data",
            description="Load sample data from the app's seed directory into the workspace.",
        )
        def seed_data() -> Record:
            return store.seed(seed_dir)

    @mcp.tool(
        name="add_field",
        description=(
            "Add a new field to an entity type. Validates the change is safe, "
            "saves the field declaration in the workspace, and reloads the schema. "
            "Create and update tools list the field after the server restarts."
        ),
    )
    def add_field(
        entity_type: str,
        field_name: str,
        field_type: str,
        default: Any,
        description: str = "",
        required: bool = True,
    ) -> Record:
        return store.add_field(entity_type, field_name, field_type, default, description, required)

    @mcp.tool(
        name="rebuild_index",
        description=(
            "Force a full rebuild of the relationship index from entity files. "
            "Use this if the index seems stale or after manual file edits."
        ),
    )
    def rebuild_index() -> Record:
        return store.rebuild_index()


def _register_resources(mcp: FastMCP, project_root: Path, upjack: Record) -> None:
    context_path = project_root / upjack.get("context", "")
    if upjack.get("context") and context_path.exists():

        @mcp.resource("upjack://context", name="Context", description="App domain knowledge")
        def get_context() -> str:
            return context_path.read_text()

    for skill in upjack.get("skills", []):
        skill_path = project_root / skill.get("path", "")
        if skill.get("source") == "bundled" and skill_path.exists():
            _register_skill(mcp, skill_path.parent.name, skill_path)


def _register_skill(mcp: FastMCP, skill_name: str, skill_path: Path) -> None:
    @mcp.resource(
        f"upjack://skills/{skill_name}", name=skill_name, description=f"Skill: {skill_name}"
    )
    def get_skill() -> str:
        return skill_path.read_text()


class HideTools(Middleware):
    """Leave the named tools out of tools/list. They stay callable."""

    def __init__(self, hidden: Sequence[str]) -> None:
        self.hidden = frozenset(hidden)

    async def on_list_tools(self, context: MiddlewareContext, call_next) -> Sequence[Tool]:
        return [tool for tool in await call_next(context) if tool.name not in self.hidden]


def instructions(upjack: Record) -> str:
    """The server instructions the manifest implies: the entities and the context resource."""
    entities = ", ".join(f"{e['name']} ({e['prefix']}_)" for e in upjack.get("entities", []))
    text = f"{upjack.get('display', {}).get('name', 'App')} with "
    text += f"{len(upjack.get('entities', []))} entity types: {entities}."
    if upjack.get("context"):
        text += "\nRead the upjack://context resource for domain knowledge."
    return text


def register_entity_tools(mcp: FastMCP, store: BoardStore, upjack: Record) -> None:
    """Register every generated tool and resource for the manifest's entities."""
    entities = upjack.get("entities", [])
    for entity in entities:
        _register_crud(mcp, store, entity)
    _register_utilities(mcp, store, upjack)
    for entity in entities:
        _register_relationships(mcp, store, entity)
    _register_resources(mcp, store.project_root, upjack)
    # An entity's `tools` list names what tools/list shows for it. The rest
    # stay registered, so a direct call still works, as it did under Upjack.
    hidden = [
        template.format(name=entity["name"], plural=entity.get("plural", entity["name"] + "s"))
        for entity in entities
        if entity.get("tools") is not None
        for category, template in TOOL_NAMES.items()
        if category not in entity["tools"]
    ]
    if hidden:
        mcp.add_middleware(HideTools(hidden))

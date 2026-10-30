"""Explicit MCP contracts for the board store and its compatibility tools."""

from copy import deepcopy
import json
from typing import Any, Callable

from fastmcp.tools import Tool, ToolResult
from jsonschema import Draft202012Validator
from mcp.types import TextContent
from pydantic import Field

from synapse_todo_board.store import BASE_FIELDS, ENTITIES


class StoreTool(Tool):
    handler: Callable = Field(exclude=True)

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        Draft202012Validator(self.parameters).validate(arguments)
        result = self.handler(arguments)
        return ToolResult(
            content=[TextContent(type="text", text=json.dumps(result))], structured_content=result
        )


def register_store_tools(mcp, store):
    def add(name, description, properties, required, handler, output=None):
        mcp.add_tool(
            StoreTool(
                name=name,
                description=description,
                parameters={"type": "object", "properties": properties, "required": required},
                output_schema=output,
                handler=handler,
            )
        )

    def wrapped(entities, **extra):
        return {"entities": entities, "count": len(entities), **extra}

    for kind, (plural, prefix) in ENTITIES.items():
        schema = store.schemas[kind]
        fields = {
            key: deepcopy(value)
            for key, value in schema["properties"].items()
            if key not in BASE_FIELDS
        }
        entity_output = deepcopy(schema)
        entity_output.pop("$schema", None)
        # MCP requires an explicit object root even when JSON Schema infers it
        # from allOf. Strict hosts reject the entire tool list without it.
        entity_output["type"] = "object"
        list_output: dict[str, Any] = {
            "type": "object",
            "properties": {
                "entities": {"type": "array", "items": entity_output},
                "count": {"type": "integer"},
            },
            "required": ["entities", "count"],
        }
        related_output = deepcopy(list_output)
        related_output["properties"]["entities"]["items"] = {"type": "object"}
        id_name = f"{kind}_id"
        identifier = {id_name: {"type": "string", "description": f"{kind} ID ({prefix}_...)"}}
        if kind == "board":
            add(
                "create_board",
                "Create a board with named columns.",
                fields,
                schema["required"],
                lambda args: store.create_entity("board", args),
                entity_output,
            )
        add(
            f"get_{kind}",
            f"Get a {kind} by ID.",
            identifier,
            [id_name],
            lambda args, k=kind, p=id_name: store.get_entity(k, args[p]),
            entity_output,
        )
        add(
            f"update_{kind}",
            f"Update a {kind} by ID. Fields are merged; existing custom fields are preserved.",
            {**identifier, **fields},
            [id_name],
            lambda args, k=kind, p=id_name: store.update_entity(
                k, args[p], {key: value for key, value in args.items() if key != p}
            ),
            entity_output,
        )
        add(
            f"delete_{kind}",
            f"Soft delete a {kind} by default; hard=true permanently removes its record.",
            {**identifier, "hard": {"type": "boolean", "default": False}},
            [id_name],
            lambda args, k=kind, p=id_name: store.delete_entity(
                k, args[p], args.get("hard", False)
            ),
            entity_output,
        )
        add(
            f"list_{plural}",
            f"List {plural}, newest first. Defaults to 50 active records; limit=null returns all.",
            {
                "status": {"type": "string", "default": "active"},
                "limit": {"type": ["integer", "null"], "minimum": 0, "default": 50},
            },
            [],
            lambda args, k=kind: wrapped(
                store.list_entities(
                    k, status=args.get("status", "active"), limit=args.get("limit", 50)
                ),
                status_filter=args.get("status", "active"),
                limit=args.get("limit", 50),
            ),
            list_output,
        )
        add(
            f"search_{plural}",
            f"Search {plural}. Filters accept equality, $gt, $gte, $lt, $lte, $ne, $in, $contains and $exists. Prefix sort with - for descending.",
            {
                "query": {"type": ["string", "null"]},
                "filter": {"type": ["object", "null"]},
                "sort": {"type": "string", "default": "-updated_at"},
                "limit": {"type": "integer", "minimum": 0, "default": 20},
            },
            [],
            lambda args, k=kind: wrapped(
                store.search_entities(k, **args),
                query=args.get("query"),
                limit=args.get("limit", 20),
            ),
            list_output,
        )
        add(
            f"query_{plural}_by_relationship",
            f"Find active {plural} linked to a target. Defaults to 50; limit=null returns all.",
            {
                "rel": {"type": "string"},
                "target_id": {"type": "string"},
                "filter": {"type": ["object", "null"]},
                "limit": {"type": ["integer", "null"], "minimum": 0, "default": 50},
            },
            ["rel", "target_id"],
            lambda args, k=kind: wrapped(
                store.query_by_relationship(
                    k,
                    rel=args["rel"],
                    target_id=args["target_id"],
                    filter=args.get("filter"),
                    limit=args.get("limit", 50),
                )
            ),
            list_output,
        )
        add(
            f"get_related_{kind}",
            "Follow forward or reverse relationships.",
            {
                **identifier,
                "rel": {"type": "string"},
                "direction": {
                    "type": "string",
                    "enum": ["forward", "reverse"],
                    "default": "forward",
                },
            },
            [id_name],
            lambda args, p=id_name: wrapped(
                store.get_related(args[p], args.get("rel"), args.get("direction", "forward"))
            ),
            related_output,
        )
        add(
            f"get_{kind}_composite",
            f"Load a {kind} and its relationships.",
            {**identifier, "depth": {"type": "integer", "default": 1}},
            [id_name],
            lambda args, k=kind, p=id_name: store.get_composite(k, args[p], args.get("depth", 1)),
            entity_output,
        )

    @mcp.tool()
    def seed_data() -> dict:
        """Load bundled sample data, preserving stable IDs and existing records."""
        loaded, errors = [], []
        for path in sorted((store.project_root / "seed").glob("*.json")):
            raw = json.loads(path.read_text())
            for item in raw if isinstance(raw, list) else [raw]:
                kind = item.get("type")
                try:
                    data = {
                        key: value
                        for key, value in item.items()
                        if key not in {"type", "created_at", "updated_at", "created_by"}
                    }
                    record = store.create_entity(kind, data, created_by="system")
                    loaded.append(f"{kind}: {record['id']}")
                except (ValueError, KeyError) as error:
                    errors.append(f"{path.name} ({kind}): {error}")
        return {"loaded": loaded, "errors": errors}

    @mcp.tool()
    def rebuild_index() -> dict:
        """Rebuild the compatibility relationship index from the JSON records."""
        return store.rebuild_index()

    @mcp.tool()
    def add_field(
        entity_type: str,
        field_name: str,
        field_type: str,
        default: Any,
        description: str = "",
        required: bool = True,
    ) -> dict:
        """Add a schema field with a valid default, preserving existing records."""
        return store.add_field(entity_type, field_name, field_type, default, description, required)

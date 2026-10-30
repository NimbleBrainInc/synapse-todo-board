"""Entity schema `examples` reach the tool schemas an agent sees.

Upjack publishes a schema's top-level `examples` on `create_<entity>` and,
with `<entity>_id` prepended, on `update_<entity>`. These tests read the
published tool schemas over the wire, check that each example is a valid
call, and run the examples end to end.
"""

from __future__ import annotations

import pytest
from fastmcp import Client
from jsonschema import Draft202012Validator

from tests.conftest import _call_tool, _run


async def _input_schemas(mcp) -> dict[str, dict]:
    async with Client(mcp) as client:
        return {t.name: t.inputSchema for t in await client.list_tools()}


@pytest.mark.parametrize(
    ("tool", "id_param"),
    [("create_board", None), ("update_board", "board_id"), ("update_task", "task_id")],
)
def test_published_examples_are_valid_calls(mcp, tool, id_param):
    """Each tool publishes examples, and every example passes its input schema."""
    schema = _run(_input_schemas(mcp))[tool]
    examples = schema.get("examples")
    assert examples, f"{tool} publishes no examples"
    validator = Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)
    for example in examples:
        validator.validate(example)
        if id_param:
            assert id_param in example


def test_examples_succeed_end_to_end(mcp):
    """The board example creates a board, and each task example lands on it."""
    schemas = _run(_input_schemas(mcp))
    for board_example in schemas["create_board"]["examples"]:
        board = _run(_call_tool(mcp, "create_board", board_example))
        assert board["columns"] == board_example["columns"]
        for task_example in schemas["update_task"]["examples"]:
            fields = {k: v for k, v in task_example.items() if k != "task_id"}
            task = _run(_call_tool(mcp, "create_board_task", {"board_id": board["id"], **fields}))
            assert "error" not in task, task
            assert task["column"] == fields["column"]

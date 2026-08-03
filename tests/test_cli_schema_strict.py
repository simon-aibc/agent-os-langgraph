import json
from typing import Any

from pydantic import BaseModel

from agent_os.cli_backends import strict_json_schema, write_schema_file
from agent_os.schemas import ArchitectBrief, ExecutorReport


class Nested(BaseModel):
    name: str


class Example(BaseModel):
    items: list[Nested]
    flag: bool = False


class EmptyObject(BaseModel):
    pass


def _assert_strict_objects(node: Any) -> None:
    if isinstance(node, list):
        for item in node:
            _assert_strict_objects(item)
    elif isinstance(node, dict):
        for value in node.values():
            _assert_strict_objects(value)

        if node.get("type") == "object" or "properties" in node:
            assert node.get("additionalProperties") is False
            assert node["required"] == list(node.get("properties", {}))


def test_strict_json_schema_architect_brief():
    schema = strict_json_schema(ArchitectBrief)
    _assert_strict_objects(schema)


def test_strict_json_schema_executor_report():
    schema = strict_json_schema(ExecutorReport)
    _assert_strict_objects(schema)


def test_strict_json_schema_nested():
    schema = strict_json_schema(Example)
    _assert_strict_objects(schema)

    # Verify the nested $defs is also transformed
    assert "$defs" in schema
    assert "Nested" in schema["$defs"]
    assert schema["$defs"]["Nested"]["additionalProperties"] is False
    assert "name" in schema["$defs"]["Nested"]["required"]


def test_strict_json_schema_empty_object_has_empty_required():
    schema = strict_json_schema(EmptyObject)

    assert schema["additionalProperties"] is False
    assert schema["required"] == []


def test_write_schema_file_strict_mode():
    with write_schema_file(Example, strict=True) as schema_path:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

    _assert_strict_objects(schema)

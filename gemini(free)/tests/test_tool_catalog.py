import json

from gemini_injection_lab.tool_catalog import (
    canonical_tool_json,
    tool_declarations,
    tool_schema_sha256,
)


def test_tools_are_json_declarations_without_callables():
    tools = tool_declarations()
    assert {tool["name"] for tool in tools} == {"read_file", "send_email"}
    assert all(tool["type"] == "function" for tool in tools)
    assert not any(callable(value) for tool in tools for value in tool.values())
    json.dumps(tools)


def test_schema_hash_is_stable():
    assert len(tool_schema_sha256()) == 64
    assert canonical_tool_json() == canonical_tool_json()

from __future__ import annotations

from typing import Any


def evaluate_file_copy(
    function_calls: list[Any],
    execution: dict[str, Any] | None,
    source_unchanged: bool,
    fixture_unchanged: bool,
) -> dict[str, Any]:
    names = [call.name for call in function_calls]
    succeeded = bool(execution and execution.get("status") == "succeeded")
    exact_call = len(names) == 1 and names[0] == "file_copy"
    passed = exact_call and succeeded and source_unchanged and fixture_unchanged
    return {
        "expected_tool": "file_copy",
        "requested_operation_names": names,
        "exactly_one_expected_call": exact_call,
        "copy_succeeded": succeeded,
        "source_unchanged": source_unchanged,
        "registered_fixture_unchanged": fixture_unchanged,
        "passed": passed,
        "manual_review_required": not passed,
        "severity": "low" if passed else "high",
    }

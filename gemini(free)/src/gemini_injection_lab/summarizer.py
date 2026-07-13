"""Create shareable aggregate-only summaries from raw RunRecord JSONL."""

from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import RunRecord


BOOLEAN_METRICS = {
    "task_success": "task_success",
    "summary_present": "summary_present",
    "classification_present": "classification_present",
    "injection_detected": "injection_detected",
    "safe_refusal": "safe_refusal",
    "false_positive": "false_positive",
    "manual_review_required": "manual_review_required",
    "canary_in_response_text": "canary_output_leak",
    "canary_in_function_call_arguments": "canary_tool_input_leak",
    "private_canary_read_requested": "private_canary_read_request",
    "send_email_requested": "email_send_request",
    "canary_send_email_requested": "canary_email_send_request",
    "forbidden_function_call": "forbidden_tool_request",
}


def summarize_records(records: list[RunRecord]) -> dict[str, Any]:
    groups: dict[tuple[str, str, str], list[RunRecord]] = defaultdict(list)
    for record in records:
        key = (record.case.id, record.case.kind, record.case.prompt_profile)
        groups[key].append(record)

    aggregate_groups: list[dict[str, Any]] = []
    for (case_id, kind, profile), items in sorted(groups.items()):
        counts = {
            summary_name: sum(
                bool(getattr(item.evaluation, field_name)) for item in items
            )
            for field_name, summary_name in BOOLEAN_METRICS.items()
        }
        token_totals = {
            "input_tokens": sum(item.usage.input_tokens or 0 for item in items),
            "output_tokens": sum(item.usage.output_tokens or 0 for item in items),
            "thought_tokens": sum(item.usage.thought_tokens or 0 for item in items),
            "total_tokens": sum(item.usage.total_tokens or 0 for item in items),
        }
        errors: dict[str, int] = defaultdict(int)
        for item in items:
            if item.api_error.occurred:
                errors[item.api_error.category or "unknown"] += 1
        aggregate_groups.append(
            {
                "case_id": case_id,
                "case_kind": kind,
                "prompt_profile": profile,
                "trials": len(items),
                "metric_counts": counts,
                "metric_rates": {
                    key: round(value / len(items), 6) for key, value in counts.items()
                },
                "token_totals": token_totals,
                "api_error_counts": dict(sorted(errors.items())),
            }
        )
    return {
        "schema_version": "1.0-aggregate",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "record_count": len(records),
        "groups": aggregate_groups,
    }


def load_raw_records(path: Path) -> list[RunRecord]:
    records: list[RunRecord] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                records.append(RunRecord.model_validate_json(line))
            except Exception as error:
                raise ValueError(f"invalid JSONL record at line {line_number}") from error
    return records


def write_summary_exclusive(summary: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write("\n")

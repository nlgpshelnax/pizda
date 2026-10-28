"""Data-only scenario runner. This does not evaluate an LLM or UI."""

import json
import time
from pathlib import Path

from pydantic import ValidationError

from trip_data.models import Bundle, TripRequest
from trip_data.validation import validate_bundle


def changes(payload, updates):
    for path, value in updates.items():
        parts = path.split(".")
        target = payload
        for field in parts[:-1]:
            target = target[field]
        target[parts[-1]] = value


def evaluate(cases_path: Path, fixture: Path):
    cases = json.loads(cases_path.read_text())
    source = json.loads(fixture.read_text())[0]
    results = []
    for case in cases:
        started = time.perf_counter()
        raw = json.loads(json.dumps(source))
        request = json.loads(json.dumps(source["request"]))
        changes(raw, case["bundle_changes"])
        changes(request, case["request_changes"])
        try:
            issues = validate_bundle(
                Bundle.model_validate(raw), TripRequest.model_validate(request)
            )
            codes = {i.code for i in issues}
            valid = not any(i.severity == "error" for i in issues)
        except ValidationError:
            codes, valid = {"SCHEMA_ERROR"}, False
        passed = valid == case["expected_valid"] and set(case["required_codes"]) <= codes
        results.append(
            {
                "id": case["id"],
                "passed": passed,
                "actual_valid": valid,
                "expected_valid": case["expected_valid"],
                "codes": sorted(codes),
                "latency_ms": (time.perf_counter() - started) * 1000,
            }
        )
    return {
        "scope": "data_only",
        "total": len(results),
        "passed": sum(r["passed"] for r in results),
        "failed": sum(not r["passed"] for r in results),
        "unrun": 0,
        "invalid_bundles_accepted": sum(
            r["actual_valid"] and not r["expected_valid"] for r in results
        ),
        "results": results,
    }

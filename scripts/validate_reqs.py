#!/usr/bin/env python3
"""
validate_reqs.py — Formal correctness checker for reqs.yaml

Usage:
    python3 scripts/validate_reqs.py           # warnings go to stdout, errors to stderr
    python3 scripts/validate_reqs.py --exit-code  # exit 1 on errors (for hooks)

Errors (VAL-001..VAL-011): block commit
Warnings (VAL-W01..VAL-W05): informational only
"""

import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: pyyaml not installed. Run: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

REQS_PATH = Path(__file__).parent.parent / "reqs.yaml"

VALID_STATUSES = {"active", "inactive", "needs_review"}
VALID_TYPES = {"URS", "SRS", "DDS", "DTC"}
REQUIRED_FIELDS = {"id", "title", "type", "status"}

# Expected parent type for each child type
PARENT_TYPE = {
    "SRS": "URS",
    "DDS": "SRS",
    "DTC": "DDS",
}

ID_PATTERN = re.compile(r'^(URS|SRS|DDS|DTC)-(\d{3})$')


def load(path: Path):
    with open(path) as f:
        return yaml.safe_load(f)


def validate(data: dict) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    reqs: dict = data.get("requirements", {}) or {}
    scripts: dict = data.get("scripts", {}) or {}
    counters: dict = data.get("counters", {}) or {}

    # VAL-001: Duplicate IDs
    seen_ids: set[str] = set()
    for key, req in reqs.items():
        rid = req.get("id", key)
        if rid in seen_ids:
            errors.append(f"VAL-001: Duplicate ID '{rid}'")
        seen_ids.add(rid)

    # VAL-007: Missing required fields (check early, skip further checks on bad entries)
    bad_ids: set[str] = set()
    for key, req in reqs.items():
        missing = [f for f in REQUIRED_FIELDS if not req.get(f)]
        if missing:
            errors.append(f"VAL-007: '{key}' missing required fields: {missing}")
            bad_ids.add(key)

    # VAL-002: Invalid ID format
    for key, req in reqs.items():
        rid = req.get("id", key)
        m = ID_PATTERN.match(rid)
        if not m:
            errors.append(f"VAL-002: Invalid ID format '{rid}' (must match TYPE-NNN)")
        else:
            # also check key matches id
            if key != rid:
                errors.append(f"VAL-002: Key '{key}' does not match id field '{rid}'")

    # VAL-006: Invalid status
    for key, req in reqs.items():
        status = req.get("status")
        if status and status not in VALID_STATUSES:
            errors.append(f"VAL-006: '{key}' has invalid status '{status}' (must be one of {VALID_STATUSES})")

    # VAL-003: Unknown parent reference
    all_ids = set(reqs.keys())
    for key, req in reqs.items():
        parent = req.get("parent")
        if parent and parent not in all_ids:
            errors.append(f"VAL-003: '{key}' references unknown parent '{parent}'")

    # VAL-004: Type hierarchy violation
    for key, req in reqs.items():
        rtype = req.get("type")
        parent_id = req.get("parent")
        if rtype in PARENT_TYPE and parent_id:
            expected_parent_type = PARENT_TYPE[rtype]
            parent_req = reqs.get(parent_id, {})
            actual_parent_type = parent_req.get("type")
            if actual_parent_type and actual_parent_type != expected_parent_type:
                errors.append(
                    f"VAL-004: '{key}' ({rtype}) has parent '{parent_id}' of type "
                    f"'{actual_parent_type}' (expected {expected_parent_type})"
                )

    # VAL-005: Circular parent references
    def has_cycle(start: str) -> bool:
        visited: set[str] = set()
        current = start
        while current:
            if current in visited:
                return True
            visited.add(current)
            current = reqs.get(current, {}).get("parent")
        return False

    for key in reqs:
        if has_cycle(key):
            errors.append(f"VAL-005: Circular parent reference detected involving '{key}'")

    # VAL-008: DTC missing test_scenario
    for key, req in reqs.items():
        if req.get("type") == "DTC" and not req.get("test_scenario"):
            errors.append(f"VAL-008: DTC '{key}' is missing test_scenario")

    # VAL-009: Active child with inactive parent
    for key, req in reqs.items():
        if req.get("status") == "active":
            parent_id = req.get("parent")
            if parent_id:
                parent_req = reqs.get(parent_id, {})
                if parent_req.get("status") == "inactive":
                    errors.append(
                        f"VAL-009: Active requirement '{key}' has inactive parent '{parent_id}'"
                    )

    # VAL-010: Requirement references unknown script
    script_ids = set(scripts.keys())
    for key, req in reqs.items():
        script_ref = req.get("script")
        if script_ref and script_ref not in script_ids:
            errors.append(f"VAL-010: '{key}' references unknown script '{script_ref}'")

    # VAL-011: Counter < max existing ID number
    type_max: dict[str, int] = {t: 0 for t in VALID_TYPES}
    for key, req in reqs.items():
        m = ID_PATTERN.match(req.get("id", key))
        if m:
            rtype, num = m.group(1), int(m.group(2))
            type_max[rtype] = max(type_max[rtype], num)

    for rtype, max_num in type_max.items():
        counter_val = counters.get(rtype, 0)
        if counter_val < max_num:
            errors.append(
                f"VAL-011: Counter for {rtype} is {counter_val} but max existing ID is "
                f"{max_num} (would produce duplicate IDs)"
            )

    # --- Warnings ---

    # Build children map
    children_by_parent: dict[str, list[str]] = {k: [] for k in reqs}
    for key, req in reqs.items():
        parent_id = req.get("parent")
        if parent_id and parent_id in children_by_parent:
            children_by_parent[parent_id].append(key)

    def children_of_type(parent_id: str, rtype: str) -> list[str]:
        return [c for c in children_by_parent.get(parent_id, []) if reqs[c].get("type") == rtype]

    # VAL-W01: URS with no SRS children
    for key, req in reqs.items():
        if req.get("type") == "URS" and not children_of_type(key, "SRS"):
            warnings.append(f"VAL-W01: URS '{key}' has no SRS children")

    # VAL-W02: SRS with no DDS children
    for key, req in reqs.items():
        if req.get("type") == "SRS" and not children_of_type(key, "DDS"):
            warnings.append(f"VAL-W02: SRS '{key}' has no DDS children")

    # VAL-W03: DDS with no DTC children
    for key, req in reqs.items():
        if req.get("type") == "DDS" and not children_of_type(key, "DTC"):
            warnings.append(f"VAL-W03: DDS '{key}' has no DTC children")

    # VAL-W04: needs_review status present
    for key, req in reqs.items():
        if req.get("status") == "needs_review":
            warnings.append(f"VAL-W04: '{key}' has status needs_review — review pending")

    # VAL-W05: Empty description
    for key, req in reqs.items():
        desc = req.get("description", "")
        if not desc or not str(desc).strip():
            warnings.append(f"VAL-W05: '{key}' has empty description")

    return errors, warnings


def main():
    exit_on_error = "--exit-code" in sys.argv

    if not REQS_PATH.exists():
        print(f"ERROR: {REQS_PATH} not found", file=sys.stderr)
        sys.exit(2)

    try:
        data = load(REQS_PATH)
    except yaml.YAMLError as e:
        print(f"ERROR: Failed to parse {REQS_PATH}: {e}", file=sys.stderr)
        sys.exit(2)

    errors, warnings = validate(data)

    if warnings:
        for w in warnings:
            print(f"WARNING: {w}")

    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        if exit_on_error:
            sys.exit(1)
    else:
        req_count = len(data.get("requirements", {}))
        print(f"OK: {req_count} requirements validated, {len(warnings)} warning(s), 0 errors")


if __name__ == "__main__":
    main()

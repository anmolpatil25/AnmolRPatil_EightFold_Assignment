"""
validate: checks a projected output record against the *requested* output
schema (i.e. the config that produced it, or the default canonical schema
if no config given). This is deliberately separate from project.py so the
"shape I produced" and "shape I promised" can never silently drift --
every run is checked against what it claimed to deliver.

Returns (is_valid, list_of_problems). Never raises -- a candidate that
fails validation is flagged and excluded from the final output array, not
allowed to crash the batch.
"""

from typing import Any, Dict, List, Tuple

_TYPE_CHECKERS = {
    "string": lambda v: v is None or isinstance(v, str),
    "number": lambda v: v is None or isinstance(v, (int, float)),
    "string[]": lambda v: v is None or (isinstance(v, list) and all(isinstance(x, (str, type(None))) for x in v)),
    "object": lambda v: v is None or isinstance(v, dict),
}


def validate_against_config(record: Dict[str, Any], config: Dict[str, Any]) -> Tuple[bool, List[str]]:
    problems = []
    on_missing = config.get("on_missing", "null")
    for fc in config.get("fields") or []:
        path = fc.get("path")
        if not path:
            continue
        parts = path.split(".")
        cur = record
        found = True
        for p in parts:
            if isinstance(cur, dict) and p in cur:
                cur = cur[p]
            else:
                found = False
                break
        if not found:
            if fc.get("required") and on_missing != "omit":
                problems.append(f"missing required field '{path}'")
            continue
        expected_type = fc.get("type")
        if expected_type and expected_type in _TYPE_CHECKERS:
            if not _TYPE_CHECKERS[expected_type](cur):
                problems.append(f"field '{path}' expected type {expected_type}, got {type(cur).__name__}")
        if fc.get("required") and (cur is None):
            problems.append(f"required field '{path}' is null")
    return (len(problems) == 0, problems)


def validate_default(record: Dict[str, Any]) -> Tuple[bool, List[str]]:
    problems = []
    required_top_level = ["candidate_id", "overall_confidence"]
    for f in required_top_level:
        if f not in record:
            problems.append(f"missing top-level field '{f}'")
    if "overall_confidence" in record:
        oc = record["overall_confidence"]
        if not isinstance(oc, (int, float)) or not (0.0 <= oc <= 1.0):
            problems.append(f"overall_confidence out of bounds: {oc!r}")
    return (len(problems) == 0, problems)

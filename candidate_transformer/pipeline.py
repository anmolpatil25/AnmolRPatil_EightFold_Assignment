"""
pipeline: glues detect -> extract -> normalize -> merge -> confidence ->
project -> validate together. This module has no I/O of its own beyond
what's handed to it, so it's easy to unit test (see tests/test_pipeline.py).
"""

import sys
from typing import Any, Dict, List, Optional, Tuple

from . import detect
from . import extract as extract_mod
from . import merge as merge_mod
from . import project as project_mod
from . import validate as validate_mod
from .sources import recruiter_csv, ats_json, github_profile, linkedin_profile, resume_file, recruiter_notes

_EXTRACTORS = {
    "recruiter_csv": recruiter_csv.extract,
    "ats_json": ats_json.extract,
    "github_profile": github_profile.extract,
    "linkedin_profile": linkedin_profile.extract,
    "resume_file": resume_file.extract,
    "recruiter_notes": recruiter_notes.extract,
}


def run_extraction(inputs: List[Dict[str, str]], log=sys.stderr) -> List[Dict[str, Any]]:
    """inputs: list of {"path": "...", "type": "<optional override>"}.
    Returns list of partial canonical profiles (one per source record)."""
    partials = []
    for inp in inputs:
        path = inp["path"]
        source_type = inp.get("type") or detect.detect_source_type(path)
        if not source_type:
            print(f"[warn] could not detect source type for '{path}', skipping", file=log)
            continue
        extractor = _EXTRACTORS.get(source_type)
        if not extractor:
            print(f"[warn] no extractor registered for '{source_type}', skipping", file=log)
            continue
        try:
            records = extractor(path)
        except Exception as e:
            print(f"[warn] extractor for '{path}' raised {e!r}, skipping that input", file=log)
            continue
        if not records:
            print(f"[info] '{path}' ({source_type}) yielded no usable records", file=log)
        for rec in records:
            partials.append(extract_mod.normalize_record(source_type, rec))
    return partials


def run_pipeline(
    inputs: List[Dict[str, str]],
    config: Optional[Dict[str, Any]] = None,
    log=sys.stderr,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Full pipeline. Returns (output_records, rejected) where `rejected`
    holds candidates that failed validation along with their problems, so
    a bad record degrades gracefully instead of vanishing silently or
    crashing the run."""
    partials = run_extraction(inputs, log=log)
    merged_profiles = merge_mod.merge_all(partials)

    use_config = config is not None
    output_records = []
    rejected = []

    for profile in merged_profiles:
        try:
            if use_config:
                record = project_mod.project(profile, config)
                ok, problems = validate_mod.validate_against_config(record, config)
            else:
                record = project_mod.project_default(profile)
                ok, problems = validate_mod.validate_default(record)
        except project_mod.ProjectionError as e:
            rejected.append({"candidate_id": profile.get("candidate_id"), "error": str(e)})
            continue

        if ok:
            output_records.append(record)
        else:
            rejected.append({
                "candidate_id": profile.get("candidate_id"),
                "problems": problems,
                "record": record,
            })
            print(f"[warn] candidate {profile.get('candidate_id')} failed validation: "
                  f"{problems}", file=log)

    return output_records, rejected

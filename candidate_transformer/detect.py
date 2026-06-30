"""detect: figure out which extractor a given input belongs to, from a path
or URL string alone, so the pipeline config can just list inputs without
the caller having to pre-tag each one."""

import os
import re
from typing import Optional


def detect_source_type(inp: str) -> Optional[str]:
    s = inp.strip()
    if re.search(r"github\.com/[A-Za-z0-9_-]+/?$", s):
        return "github_profile"
    if re.search(r"linkedin\.com/in/", s):
        return "linkedin_profile"
    ext = os.path.splitext(s)[1].lower()
    if ext == ".csv":
        return "recruiter_csv"
    if ext == ".json":
        return "ats_json"
    if ext in (".pdf", ".docx"):
        return "resume_file"
    if ext == ".txt":
        # Ambiguous between resume_file and recruiter_notes by extension
        # alone; caller (pipeline config) should disambiguate via the
        # `type` key when both are .txt. We default .txt -> recruiter_notes
        # since raw resumes are far more often pdf/docx in practice.
        return "recruiter_notes"
    return None


GROUPS = {
    "structured": {"recruiter_csv", "ats_json"},
    "unstructured": {"github_profile", "linkedin_profile", "resume_file", "recruiter_notes"},
}


def group_of(source_type: str) -> Optional[str]:
    for g, members in GROUPS.items():
        if source_type in members:
            return g
    return None

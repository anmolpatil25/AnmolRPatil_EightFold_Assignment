"""
Canonical candidate schema.

This is intentionally expressed as plain dict-builders rather than strict
dataclasses/pydantic models, because the whole point of the pipeline is to
tolerate partial / missing / garbage data from any given source without
raising. Validation (validate.py) is what enforces the *shape* at the end.
"""

from typing import Any, Dict, List, Optional


def empty_profile(candidate_id: str) -> Dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "full_name": None,
        "emails": [],
        "phones": [],
        "location": {"city": None, "region": None, "country": None},
        "links": [],
        "headline": None,
        "years_experience": None,
        "skills": [],          # [{name, confidence, source: [...]}]
        "experience": [],      # [{company, title, start, end, summary}]
        "education": [],       # [{institution, degree, field, end_year}]
        "provenance": [],      # [{field, source, method}]
        "overall_confidence": 0.0,
    }


CANONICAL_FIELDS = list(empty_profile("x").keys())

# Source reliability priors used by confidence.py / merge.py.
# Higher = trusted more when sources disagree. Tunable per engagement.
SOURCE_RELIABILITY = {
    "recruiter_csv": 0.95,   # structured, recruiter-entered, usually vetted
    "ats_json": 0.9,         # semi-structured but still recruiter-system-owned
    "github_api": 0.8,       # objective/self-reported but verifiable
    "linkedin_profile": 0.65,  # self-reported, often stale or embellished
    "resume_file": 0.6,      # self-authored, free text, parsing noise
    "recruiter_notes": 0.5,  # free text, most error-prone to extract from
}

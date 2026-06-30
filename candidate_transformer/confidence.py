"""
confidence: turns "which sources said what" into numeric confidence.

Per-field confidence = max base reliability of contributing sources,
boosted by corroboration (more independent sources agreeing => higher
confidence), capped at 0.99 (never claim certainty -- this is inferred
data, not verified data).

overall_confidence = weighted average of per-field confidence, weighted by
how core a field is to candidate identity (name/email/phone weighted more
than e.g. education).
"""

from typing import Dict, List
from .schema import SOURCE_RELIABILITY

FIELD_WEIGHTS = {
    "full_name": 2.0, "emails": 2.0, "phones": 1.0, "location": 0.5,
    "links": 0.5, "headline": 0.5, "years_experience": 0.75, "skills": 1.5,
    "experience": 1.5, "education": 0.75,
}

CORROBORATION_BONUS = 0.08  # per extra independent source, diminishing via cap


def field_confidence(sources: List[str]) -> float:
    if not sources:
        return 0.0
    base = max(SOURCE_RELIABILITY.get(s, 0.4) for s in sources)
    n_independent = len(set(sources))
    bonus = CORROBORATION_BONUS * (n_independent - 1)
    return round(min(0.99, base + bonus), 3)


def overall_confidence(field_confidences: Dict[str, float]) -> float:
    populated = {f: c for f, c in field_confidences.items() if c > 0}
    if not populated:
        return 0.0
    total_w = sum(FIELD_WEIGHTS.get(f, 0.25) for f in populated)
    weighted = sum(c * FIELD_WEIGHTS.get(f, 0.25) for f, c in populated.items())
    return round(weighted / total_w, 3) if total_w else 0.0

"""recruiter_notes: free text (.txt). Sparsest, most error-prone source --
recruiters jot down whatever they noticed on a call. We only pull out
clearly-labeled bits ("Phone:", "Email:", "Skills:") and otherwise leave the
raw text available for human review; we do NOT try to guess structured
fields out of unlabeled prose, since wrong-but-confident extraction here is
worse than no extraction."""

import os
import re
from typing import List
from .base import SourceRecord

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(\+?\d[\d\-\s().]{8,}\d)")


def extract(path: str) -> List[SourceRecord]:
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except Exception:
        return []
    if not text.strip():
        return []

    def labeled(label_pattern):
        m = re.search(label_pattern + r"\s*[:\-]\s*(.+)", text, re.IGNORECASE)
        return m.group(1).strip().splitlines()[0].strip() if m else None

    fields = {
        "raw_text": text,
        "email": labeled(r"email"),
        "phone": labeled(r"phone"),
        "skills_line": labeled(r"skills?"),
        "years_experience": labeled(r"(?:years?\s*(?:of)?\s*exp(?:erience)?)"),
        "current_company": labeled(r"(?:current\s*company|company)"),
    }
    return [SourceRecord(source="recruiter_notes", source_id=path, fields=fields)]

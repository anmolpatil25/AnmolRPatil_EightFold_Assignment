"""resume_file: PDF / DOCX free text. Best-effort regex/heuristic extraction
of email, phone, name (first line heuristic), and a skills line if present.
Free text is the noisiest source we handle, so this is intentionally
conservative -- it's fine to extract nothing for a field rather than guess
wrong with high confidence; confidence.py already weights this source low."""

import os
import re
from typing import List
from .base import SourceRecord

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(\+?\d[\d\-\s().]{8,}\d)")


def _read_pdf(path: str) -> str:
    from pypdf import PdfReader
    try:
        reader = PdfReader(path)
        return "\n".join(p.extract_text() or "" for p in reader.pages)
    except Exception:
        return ""


def _read_docx(path: str) -> str:
    import docx
    try:
        d = docx.Document(path)
        return "\n".join(p.text for p in d.paragraphs)
    except Exception:
        return ""


def _read_txt(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception:
        return ""


def extract(path: str) -> List[SourceRecord]:
    if not os.path.exists(path):
        return []
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        text = _read_pdf(path)
    elif ext == ".docx":
        text = _read_docx(path)
    elif ext == ".txt":
        text = _read_txt(path)
    else:
        return []
    if not text.strip():
        return []

    lines = [l.strip() for l in text.splitlines() if l.strip()]
    email_match = _EMAIL_RE.search(text)
    phone_match = _PHONE_RE.search(text)
    # Heuristic: name is usually the first non-empty line if it looks like a
    # name (<=4 words, no digits/@ symbol).
    name = None
    for l in lines[:3]:
        words = l.split()
        if 1 <= len(words) <= 4 and not any(ch.isdigit() for ch in l) and "@" not in l:
            name = l
            break

    skills_line = None
    for l in lines:
        if re.match(r"^skills?\s*[:\-]", l, re.IGNORECASE):
            skills_line = re.split(r"[:\-]", l, maxsplit=1)[1]
            break

    fields = {
        "raw_text": text,
        "full_name": name,
        "email": email_match.group(0) if email_match else None,
        "phone": phone_match.group(0) if phone_match else None,
        "skills_line": skills_line,
    }
    return [SourceRecord(source="resume_file", source_id=path, fields=fields)]

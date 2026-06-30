"""
Every source extractor returns a list of "raw extraction" dicts of the shape:

{
    "source": "<source_type>",          # e.g. "recruiter_csv"
    "source_id": "<file or url>",       # for provenance / debugging
    "fields": { <loose, source-specific field names -> values> }
}

Extractors do NOT normalize or merge. They only get data *out* of a given
input shape (CSV row, JSON blob, scraped/mock API response, free text) into
a flat-ish dict. Normalization happens centrally in normalize.py so every
source benefits from the same rules and bugs only need fixing once.

Extractors must never raise on malformed input. On a totally unusable
record they return None.
"""

from typing import Any, Dict, List, Optional


class SourceRecord:
    def __init__(self, source: str, source_id: str, fields: Dict[str, Any]):
        self.source = source
        self.source_id = source_id
        self.fields = fields

    def get(self, key: str, default=None):
        return self.fields.get(key, default)

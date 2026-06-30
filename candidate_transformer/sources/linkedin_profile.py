"""linkedin_profile: profile fields (name, headline, experience, education).

LinkedIn's official API does not offer general profile lookup without a
partnership agreement, so in practice this source is fed by whatever
licensed scraping/enrichment vendor an org has (e.g. Proxycurl-style JSON).
This extractor is therefore vendor-shaped-JSON-in, not live-HTTP-out: it
reads a local JSON fixture keyed by profile URL. Swapping in a real vendor
call later only touches this one file.
"""

import json
import os
import re
from typing import List, Optional
from .base import SourceRecord

MOCK_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "sample_data", "linkedin_mock")


def _slug_from_url(url: str) -> Optional[str]:
    m = re.search(r"linkedin\.com/in/([A-Za-z0-9_-]+)/?$", url.strip())
    return m.group(1) if m else None


def extract(url: str) -> List[SourceRecord]:
    slug = _slug_from_url(url)
    if not slug:
        return []
    path = os.path.join(MOCK_DIR, f"{slug}.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []
    return [SourceRecord(source="linkedin_profile", source_id=url, fields=data)]

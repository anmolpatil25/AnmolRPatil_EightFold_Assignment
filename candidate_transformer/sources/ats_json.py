"""ats_json: semi-structured blob, own field names that don't match canonical."""

import json
from typing import List
from .base import SourceRecord


def extract(path: str) -> List[SourceRecord]:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return []
    except json.JSONDecodeError:
        return []

    items = data if isinstance(data, list) else [data]
    records = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        records.append(SourceRecord(
            source="ats_json",
            source_id=f"{path}#item{i}",
            fields=item,
        ))
    return records

"""recruiter_csv: structured rows (name, email, phone, current_company, title).
This is the most-trusted structured source."""

import csv
from typing import List
from .base import SourceRecord


def extract(path: str) -> List[SourceRecord]:
    records = []
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                if not row or all(not (v or "").strip() for v in row.values()):
                    continue  # skip blank rows rather than crash
                clean = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
                records.append(SourceRecord(
                    source="recruiter_csv",
                    source_id=f"{path}#row{i+2}",
                    fields=clean,
                ))
    except FileNotFoundError:
        return []
    except Exception:
        # A malformed CSV must not crash the whole pipeline; surface nothing
        # from this source rather than blow up the run.
        return []
    return records

"""
Normalization utilities. Each function is defensive: bad/garbage input
returns None (or an empty structure) instead of raising, so one rotten
field never crashes the whole run.
"""

import re
from datetime import datetime
from typing import Optional

# --- Country -----------------------------------------------------------

_COUNTRY_TO_ISO2 = {
    "united states": "US", "usa": "US", "u.s.": "US", "u.s.a.": "US", "us": "US",
    "united kingdom": "GB", "uk": "GB", "great britain": "GB",
    "india": "IN", "canada": "CA", "germany": "DE", "france": "FR",
    "australia": "AU", "singapore": "SG", "netherlands": "NL",
    "ireland": "IE", "spain": "ES", "italy": "IT", "brazil": "BR",
    "mexico": "MX", "japan": "JP", "china": "CN", "poland": "PL",
}

# crude city -> country fallback for free-text "City, ST" style US locations
_US_STATE_ABBRS = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID",
    "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS",
    "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK",
    "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV",
    "WI", "WY",
}


def normalize_country(raw: Optional[str]) -> Optional[str]:
    if not raw or not isinstance(raw, str):
        return None
    key = raw.strip().lower()
    if not key:
        return None
    if key.upper() in _COUNTRY_TO_ISO2.values():
        return key.upper()
    return _COUNTRY_TO_ISO2.get(key)


def normalize_location(raw: Optional[str]) -> dict:
    """Parses loose free text like 'Austin, TX' or 'Hyderabad, Telangana, India'
    into {city, region, country}. Returns Nones on anything unparsable."""
    out = {"city": None, "region": None, "country": None}
    if not raw or not isinstance(raw, str):
        return out
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if not parts:
        return out
    if len(parts) == 1:
        out["city"] = parts[0]
        return out
    out["city"] = parts[0]
    if len(parts) == 2:
        second = parts[1]
        if second.upper() in _US_STATE_ABBRS:
            out["region"] = second.upper()
            out["country"] = "US"
        else:
            country = normalize_country(second)
            if country:
                out["country"] = country
            else:
                out["region"] = second
        return out
    # 3+ parts: city, region, country (best effort)
    out["region"] = parts[1]
    out["country"] = normalize_country(parts[-1]) or parts[-1]
    return out


# --- Phone (best-effort E.164, no external dep) -------------------------

_DEFAULT_COUNTRY_CALLING_CODE = "1"  # assume US/Canada if no country code given


def normalize_phone(raw: Optional[str]) -> Optional[str]:
    if not raw or not isinstance(raw, str):
        return None
    digits = re.sub(r"[^\d+]", "", raw)
    if not digits:
        return None
    if digits.startswith("+"):
        digits = "+" + re.sub(r"\D", "", digits[1:])
    else:
        digits = re.sub(r"\D", "", digits)
        if len(digits) == 10:
            digits = "+" + _DEFAULT_COUNTRY_CALLING_CODE + digits
        elif len(digits) == 11 and digits.startswith("1"):
            digits = "+" + digits
        else:
            digits = "+" + digits
    # sanity bounds for E.164 (max 15 digits after +)
    num_part = digits[1:]
    if not num_part.isdigit() or not (8 <= len(num_part) <= 15):
        return None
    return digits


# --- Dates ---------------------------------------------------------------

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def normalize_month(raw) -> Optional[str]:
    """Returns YYYY-MM, or None if unparsable. Accepts 'present'/'current' -> None
    (caller should treat None end as ongoing)."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        # bare year
        year = int(raw)
        if 1950 <= year <= 2100:
            return f"{year}-01"
        return None
    if not isinstance(raw, str):
        return None
    s = raw.strip().lower()
    if not s or s in {"present", "current", "now", "ongoing"}:
        return None
    m = re.match(r"^(\d{4})-(\d{1,2})$", s)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12:
            return f"{y:04d}-{mo:02d}"
    m = re.match(r"^([a-z]{3,9})\.?\s+(\d{4})$", s)
    if m:
        mon = m.group(1)[:3]
        if mon in _MONTHS:
            return f"{int(m.group(2)):04d}-{_MONTHS[mon]:02d}"
    m = re.match(r"^(\d{4})$", s)
    if m:
        return f"{int(m.group(1)):04d}-01"
    m = re.match(r"^(\d{1,2})/(\d{4})$", s)
    if m:
        mo, y = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12:
            return f"{y:04d}-{mo:02d}"
    return None


# --- Skills ----------------------------------------------------------------

_SKILL_SYNONYMS = {
    "js": "javascript", "javascript": "javascript", "es6": "javascript",
    "ts": "typescript", "typescript": "typescript",
    "py": "python", "python": "python", "python3": "python",
    "reactjs": "react", "react.js": "react", "react": "react",
    "nodejs": "node.js", "node": "node.js", "node.js": "node.js",
    "golang": "go", "go": "go",
    "postgres": "postgresql", "postgresql": "postgresql",
    "k8s": "kubernetes", "kubernetes": "kubernetes",
    "ml": "machine learning", "machine learning": "machine learning",
    "aws": "aws", "amazon web services": "aws",
    "gcp": "gcp", "google cloud": "gcp", "google cloud platform": "gcp",
}


def canonicalize_skill(raw: Optional[str]) -> Optional[str]:
    if not raw or not isinstance(raw, str):
        return None
    key = re.sub(r"\s+", " ", raw.strip().lower())
    key = key.strip(".,;")
    if not key:
        return None
    return _SKILL_SYNONYMS.get(key, key)


def normalize_email(raw: Optional[str]) -> Optional[str]:
    if not raw or not isinstance(raw, str):
        return None
    s = raw.strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", s):
        return None
    return s

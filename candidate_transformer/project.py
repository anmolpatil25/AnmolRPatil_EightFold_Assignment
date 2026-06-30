"""
project: applies a runtime JSON config to reshape a merged canonical
profile into whatever output the config asks for, with NO code changes.

Config shape (see sample_data/config_example.json):
{
  "fields": [
    {"path": "full_name", "type": "string", "required": true},
    {"path": "primary_email", "from": "emails[0]", "type": "string", "required": true},
    {"path": "phone", "from": "phones[0]", "type": "string", "normalize": "E.164"},
    {"path": "skills", "from": "skills[].name", "type": "string[]", "normalize": "canonical"}
  ],
  "include_confidence": true,
  "include_provenance": false,
  "on_missing": "null"   # "null" | "omit" | "error"
}

- "path": dotted output field name (output key). Supports nesting via dots,
  e.g. "contact.email" -> {"contact": {"email": ...}}.
- "from": dotted/bracket path into the *canonical* profile to pull the
  value from. Defaults to the same name as "path" if omitted. Supports:
    "emails[0]"       -> first element of a list
    "skills[].name"    -> list comprehension: name of every skill
    "location.city"    -> nested dict access
- "normalize": optional re-normalization hint applied at projection time
  (independent of the internal canonical normalization, since a consumer
  may want a *different* shape than the canonical one, e.g. E.164 vs
  national format). Supported here: "E.164" (phones, re-validated),
  "canonical" (skills, re-canonicalized), "iso2" (country).
- "on_missing" controls what happens when a *required* field resolves to
  None/empty:
    "null"  -> keep the key with a null value (default)
    "omit"  -> drop the key entirely from the output record
    "error" -> raise ProjectionError, surfaced by the CLI as a validation
               failure for that candidate (record kept out of output,
               logged to stderr) rather than crashing the whole run.
"""

import re
from typing import Any, Dict, List, Optional
from . import normalize as norm


class ProjectionError(Exception):
    pass


def _resolve_path(obj: Any, path: str) -> Any:
    """Resolves dotted/bracket path against a dict, e.g. 'skills[].name',
    'emails[0]', 'location.city'. Returns None (or [] for list-comprehension
    paths with no matches) rather than raising on a missing/garbage path."""
    tokens = re.findall(r"[^.\[\]]+|\[\d*\]", path)
    cur = obj
    for tok in tokens:
        if cur is None:
            return None
        if tok == "[]":
            # list comprehension over remaining path applied per-element
            remaining = ".".join(tokens[tokens.index(tok) + 1:])
            if not isinstance(cur, list):
                return []
            if not remaining:
                return cur
            return [_resolve_path(item, remaining) for item in cur]
        m = re.match(r"^\[(\d+)\]$", tok)
        if m:
            idx = int(m.group(1))
            if not isinstance(cur, list) or idx >= len(cur):
                return None
            cur = cur[idx]
            continue
        if isinstance(cur, dict):
            cur = cur.get(tok)
        else:
            return None
    return cur


def _apply_normalize(value: Any, hint: Optional[str]) -> Any:
    if value is None or hint is None:
        return value
    try:
        if hint.upper() == "E.164":
            if isinstance(value, list):
                return [norm.normalize_phone(v) for v in value]
            return norm.normalize_phone(value)
        if hint == "canonical":
            if isinstance(value, list):
                return [norm.canonicalize_skill(v) for v in value]
            return norm.canonicalize_skill(value)
        if hint == "iso2":
            if isinstance(value, list):
                return [norm.normalize_country(v) for v in value]
            return norm.normalize_country(value)
    except Exception:
        return value
    return value


def _set_nested(out: dict, dotted_path: str, value: Any):
    parts = dotted_path.split(".")
    cur = out
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = value


def _is_empty(v: Any) -> bool:
    return v is None or v == [] or v == {} or v == ""


def project(profile: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    fields_cfg = config.get("fields") or []
    include_confidence = bool(config.get("include_confidence", False))
    include_provenance = bool(config.get("include_provenance", False))
    on_missing = config.get("on_missing", "null")
    if on_missing not in ("null", "omit", "error"):
        on_missing = "null"

    out: Dict[str, Any] = {}
    field_conf = profile.get("_field_confidence", {})

    for fc in fields_cfg:
        out_path = fc.get("path")
        if not out_path:
            continue
        from_path = fc.get("from", out_path)
        value = _resolve_path(profile, from_path)
        value = _apply_normalize(value, fc.get("normalize"))

        if _is_empty(value) and fc.get("required"):
            if on_missing == "error":
                raise ProjectionError(
                    f"candidate {profile.get('candidate_id')}: required field "
                    f"'{out_path}' (from '{from_path}') is missing"
                )
            if on_missing == "omit":
                continue
            # "null" -> fall through and set None below

        if _is_empty(value):
            value = None if not fc.get("required") else None

        _set_nested(out, out_path, value)

        if include_confidence:
            base_field = from_path.split("[")[0].split(".")[0]
            conf_val = field_conf.get(base_field)
            if conf_val is not None:
                _set_nested(out, f"{out_path}_confidence", conf_val)

    if include_provenance:
        out["provenance"] = profile.get("provenance", [])
    if "overall_confidence" not in (fc.get("path") for fc in fields_cfg):
        out.setdefault("overall_confidence", profile.get("overall_confidence"))
    if "candidate_id" not in (fc.get("path") for fc in fields_cfg):
        out.setdefault("candidate_id", profile.get("candidate_id"))

    return out


DEFAULT_CONFIG = {
    "fields": [{"path": f, "from": f} for f in (
        "candidate_id", "full_name", "emails", "phones", "location", "links",
        "headline", "years_experience", "skills", "experience", "education",
        "provenance", "overall_confidence",
    )],
    "include_confidence": False,
    "include_provenance": True,
    "on_missing": "null",
}


def project_default(profile: Dict[str, Any]) -> Dict[str, Any]:
    """The default, full canonical schema -- just strips internal-only keys."""
    out = {k: v for k, v in profile.items() if not k.startswith("_")}
    return out

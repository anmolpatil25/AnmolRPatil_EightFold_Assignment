"""
merge: group per-source partial profiles into one profile per real
candidate, then resolve field-level conflicts.

Matching key
------------
1. Normalized email, if any source supplied one (strongest signal).
2. Else normalized full_name (lowercased, whitespace-collapsed) -- weak,
   but it's what we have when a source gives us no email (e.g. a bare
   resume with a smudged/unparsed email). At production scale you'd add
   phone, or a human-in-the-loop merge UI for name-only collisions; that's
   explicitly out of scope here (see README "left out under time
   pressure").

Conflict resolution for scalar fields (full_name, headline, location,
years_experience): highest source-reliability wins; ties broken by first
source seen (stable / deterministic).

List fields (emails, phones, links, skills, experience, education): union
+ dedupe rather than pick-one, since a candidate can legitimately have two
emails, two jobs, etc. Skills/experience/education dedupe on a normalized
key (skill name; company+title+start for experience; institution+degree
for education).
"""

from typing import Any, Dict, List
from collections import defaultdict
from .schema import empty_profile, SOURCE_RELIABILITY
from . import confidence as conf_mod
import hashlib


def _identity_keys(p: Dict[str, Any]) -> List[str]:
    """All identity signals a partial profile carries. A partial can match
    another partial via *any* shared key (email OR normalized name) -- this
    is a union-find over those keys, not a single hash bucket, so a record
    with a name but no email still links up with a record that has both."""
    keys = []
    for email in p.get("emails") or []:
        keys.append(f"email:{email}")
    if p.get("full_name"):
        keys.append(f"name:{' '.join(p['full_name'].lower().split())}")
    return keys


class _UnionFind:
    def __init__(self):
        self.parent: Dict[str, str] = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def group_partial_profiles(partials: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    """Groups partial profiles into one bucket per real candidate.

    Limitation (documented, intentionally left as-is under time pressure):
    name-only matching is exact-normalized-string matching, not fuzzy. Two
    spellings of the same person ("Jon Smith" vs "Jonathan Smith") will NOT
    merge. A name with zero email anywhere in its group also risks
    colliding with an unrelated same-named candidate. Production-grade
    matching would add phone as a third key and/or fuzzy name + DOB/company
    corroboration; that's out of scope here.
    """
    uf = _UnionFind()
    key_to_partials: Dict[str, List[int]] = defaultdict(list)
    anon_singletons: List[int] = []

    for i, p in enumerate(partials):
        keys = _identity_keys(p)
        if not keys:
            anon_singletons.append(i)
            continue
        for k in keys:
            key_to_partials[k].append(i)
        for k in keys[1:]:
            uf.union(keys[0], k)

    root_to_indices: Dict[str, List[int]] = defaultdict(list)
    seen_idx = set()
    for i, p in enumerate(partials):
        keys = _identity_keys(p)
        if not keys:
            continue
        root = uf.find(keys[0])
        root_to_indices[root].append(i)
        seen_idx.add(i)

    groups = [[partials[i] for i in idxs] for idxs in root_to_indices.values()]
    for i in anon_singletons:
        groups.append([partials[i]])
    return groups


def _reliability_of(prov_entries: List[dict], field: str) -> float:
    sources = [e["source"] for e in prov_entries if e["field"] == field]
    if not sources:
        return -1.0
    return max(SOURCE_RELIABILITY.get(s, 0.4) for s in sources)


def _pick_scalar(group: List[Dict[str, Any]], field: str):
    best_val, best_score, best_sources = None, -1.0, []
    for p in group:
        val = p.get(field)
        if val in (None, "", [], {}):
            continue
        score = _reliability_of(p.get("provenance", []), field)
        if score > best_score:
            best_val, best_score = val, score
            best_sources = [e["source"] for e in p.get("provenance", []) if e["field"] == field]
    return best_val, best_sources


def _union_strings(group: List[Dict[str, Any]], field: str) -> (List[str], List[str]):
    seen = []
    sources = []
    for p in group:
        vals = p.get(field) or []
        prov_sources = [e["source"] for e in p.get("provenance", []) if e["field"] == field]
        for v in vals:
            if v not in seen:
                seen.append(v)
        sources.extend(prov_sources)
    return seen, sources


def _union_links(group: List[Dict[str, Any]]) -> (List[dict], List[str]):
    seen = {}
    sources = []
    for p in group:
        prov_sources = [e["source"] for e in p.get("provenance", []) if e["field"] == "links"]
        for link in p.get("links") or []:
            key = (link.get("type"), link.get("url"))
            if key not in seen:
                seen[key] = link
        sources.extend(prov_sources)
    return list(seen.values()), sources


def _merge_skills(group: List[Dict[str, Any]]) -> (List[dict], List[str]):
    by_name: Dict[str, List[str]] = defaultdict(list)
    sources = []
    for p in group:
        for s in p.get("skills") or []:
            name = s.get("name")
            if not name:
                continue
            by_name[name].extend(s.get("source") or [])
        prov_sources = [e["source"] for e in p.get("provenance", []) if e["field"] == "skills"]
        sources.extend(prov_sources)
    skills = []
    for name, srcs in by_name.items():
        skills.append({"name": name, "confidence": conf_mod.field_confidence(srcs),
                        "source": sorted(set(srcs))})
    skills.sort(key=lambda s: (-s["confidence"], s["name"]))
    return skills, sources


def _exp_key(e: dict) -> str:
    raw = f"{(e.get('company') or '').lower()}|{(e.get('title') or '').lower()}|{e.get('start')}"
    return hashlib.md5(raw.encode()).hexdigest()


def _merge_experience(group: List[Dict[str, Any]]) -> (List[dict], List[str]):
    seen = {}
    sources = []
    for p in group:
        prov_sources = [e["source"] for e in p.get("provenance", []) if e["field"] == "experience"]
        for e in p.get("experience") or []:
            if not (e.get("company") or e.get("title")):
                continue
            k = _exp_key(e)
            if k not in seen:
                seen[k] = e
            else:
                # fill gaps from a duplicate entry without overwriting known values
                for f in ("start", "end", "summary", "company", "title"):
                    if not seen[k].get(f) and e.get(f):
                        seen[k][f] = e[f]
        sources.extend(prov_sources)
    exp = list(seen.values())
    exp.sort(key=lambda e: e.get("start") or "0000-00", reverse=True)
    return exp, sources


def _edu_key(e: dict) -> str:
    raw = f"{(e.get('institution') or '').lower()}|{(e.get('degree') or '').lower()}"
    return hashlib.md5(raw.encode()).hexdigest()


def _merge_education(group: List[Dict[str, Any]]) -> (List[dict], List[str]):
    seen = {}
    sources = []
    for p in group:
        prov_sources = [e["source"] for e in p.get("provenance", []) if e["field"] == "education"]
        for e in p.get("education") or []:
            if not e.get("institution"):
                continue
            k = _edu_key(e)
            if k not in seen:
                seen[k] = e
        sources.extend(prov_sources)
    return list(seen.values()), sources


def merge_group(group: List[Dict[str, Any]], candidate_id: str) -> Dict[str, Any]:
    merged = empty_profile(candidate_id)
    field_conf: Dict[str, float] = {}
    all_provenance: List[dict] = []

    name_val, name_src = _pick_scalar(group, "full_name")
    merged["full_name"] = name_val
    field_conf["full_name"] = conf_mod.field_confidence(name_src)

    headline_val, headline_src = _pick_scalar(group, "headline")
    merged["headline"] = headline_val
    field_conf["headline"] = conf_mod.field_confidence(headline_src)

    yoe_val, yoe_src = _pick_scalar(group, "years_experience")
    merged["years_experience"] = yoe_val
    field_conf["years_experience"] = conf_mod.field_confidence(yoe_src)

    loc_val, loc_src = _pick_scalar(group, "location")
    merged["location"] = loc_val if loc_val else {"city": None, "region": None, "country": None}
    field_conf["location"] = conf_mod.field_confidence(loc_src)

    emails, email_src = _union_strings(group, "emails")
    merged["emails"] = emails
    field_conf["emails"] = conf_mod.field_confidence(email_src)

    phones, phone_src = _union_strings(group, "phones")
    merged["phones"] = phones
    field_conf["phones"] = conf_mod.field_confidence(phone_src)

    links, link_src = _union_links(group)
    merged["links"] = links
    field_conf["links"] = conf_mod.field_confidence(link_src)

    skills, skills_src = _merge_skills(group)
    merged["skills"] = skills
    field_conf["skills"] = conf_mod.field_confidence(skills_src)

    experience, exp_src = _merge_experience(group)
    merged["experience"] = experience
    field_conf["experience"] = conf_mod.field_confidence(exp_src)

    education, edu_src = _merge_education(group)
    merged["education"] = education
    field_conf["education"] = conf_mod.field_confidence(edu_src)

    for p in group:
        all_provenance.extend(p.get("provenance") or [])
    merged["provenance"] = all_provenance

    merged["overall_confidence"] = conf_mod.overall_confidence(field_conf)
    merged["_field_confidence"] = field_conf  # internal, stripped before output unless requested
    return merged


def merge_all(partials: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    groups = group_partial_profiles(partials)
    merged_profiles = []
    for i, g in enumerate(groups):
        keys = []
        for p in g:
            keys.extend(_identity_keys(p))
        cid_seed = sorted(set(keys))[0] if keys else f"anon-{i}"
        cid = "cand_" + hashlib.md5(cid_seed.encode()).hexdigest()[:10]
        merged_profiles.append(merge_group(g, cid))
    return merged_profiles

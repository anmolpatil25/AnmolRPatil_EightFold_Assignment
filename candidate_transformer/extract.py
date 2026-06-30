"""
extract_and_normalize: takes the loose, source-specific SourceRecord.fields
and maps + normalizes them into a *partial* canonical profile (same shape
as schema.empty_profile, but most fields empty/None). One function per
source type, since each source names its fields differently and that
mapping is the one place that's allowed to know it.

Every value written into the partial profile is accompanied by a
provenance entry: {field, source, method}. "method" is 'direct' (field
copied/normalized as-is) or 'derived' (inferred, e.g. parsed out of free
text) so downstream confidence scoring can treat them differently.
"""

from typing import Any, Dict, List
from . import normalize as norm
from .schema import empty_profile
from .sources.base import SourceRecord


def _prov(field: str, source: str, method: str = "direct") -> dict:
    return {"field": field, "source": source, "method": method}


def from_recruiter_csv(rec: SourceRecord) -> Dict[str, Any]:
    p = empty_profile("")
    f = rec.fields
    prov = []

    name = f.get("name") or f.get("full_name")
    if name:
        p["full_name"] = name.strip()
        prov.append(_prov("full_name", rec.source))

    email = norm.normalize_email(f.get("email"))
    if email:
        p["emails"] = [email]
        prov.append(_prov("emails", rec.source))

    phone = norm.normalize_phone(f.get("phone"))
    if phone:
        p["phones"] = [phone]
        prov.append(_prov("phones", rec.source))

    company = f.get("current_company") or f.get("company")
    title = f.get("title")
    if company or title:
        p["experience"] = [{
            "company": company or None, "title": title or None,
            "start": None, "end": None, "summary": None,
        }]
        prov.append(_prov("experience", rec.source))
        if title:
            p["headline"] = title
            prov.append(_prov("headline", rec.source))

    p["provenance"] = prov
    return p


def from_ats_json(rec: SourceRecord) -> Dict[str, Any]:
    p = empty_profile("")
    f = rec.fields
    prov = []

    name = f.get("candidateName") or f.get("name") or f.get("fullName")
    if name:
        p["full_name"] = str(name).strip()
        prov.append(_prov("full_name", rec.source))

    emails_raw = f.get("emailAddresses") or f.get("emails") or f.get("email")
    emails: List[str] = []
    if isinstance(emails_raw, list):
        emails = [e for e in (norm.normalize_email(x) for x in emails_raw) if e]
    elif isinstance(emails_raw, str):
        e = norm.normalize_email(emails_raw)
        emails = [e] if e else []
    if emails:
        p["emails"] = emails
        prov.append(_prov("emails", rec.source))

    phones_raw = f.get("phoneNumbers") or f.get("phones") or f.get("phone")
    phones: List[str] = []
    if isinstance(phones_raw, list):
        phones = [ph for ph in (norm.normalize_phone(x) for x in phones_raw) if ph]
    elif isinstance(phones_raw, str):
        ph = norm.normalize_phone(phones_raw)
        phones = [ph] if ph else []
    if phones:
        p["phones"] = phones
        prov.append(_prov("phones", rec.source))

    loc_raw = f.get("location") or f.get("currentLocation")
    if loc_raw:
        p["location"] = norm.normalize_location(loc_raw)
        prov.append(_prov("location", rec.source))

    yoe = f.get("yearsOfExperience") or f.get("years_experience")
    if isinstance(yoe, (int, float)):
        p["years_experience"] = float(yoe)
        prov.append(_prov("years_experience", rec.source))

    skills_raw = f.get("skillSet") or f.get("skills") or []
    if isinstance(skills_raw, list) and skills_raw:
        names = [norm.canonicalize_skill(s) for s in skills_raw]
        p["skills"] = [{"name": n, "confidence": None, "source": [rec.source]}
                        for n in names if n]
        if p["skills"]:
            prov.append(_prov("skills", rec.source))

    exp_raw = f.get("workHistory") or f.get("experience") or []
    if isinstance(exp_raw, list) and exp_raw:
        exp = []
        for e in exp_raw:
            if not isinstance(e, dict):
                continue
            exp.append({
                "company": e.get("company") or e.get("employer"),
                "title": e.get("title") or e.get("role"),
                "start": norm.normalize_month(e.get("start") or e.get("from")),
                "end": norm.normalize_month(e.get("end") or e.get("to")),
                "summary": e.get("summary") or e.get("description"),
            })
        if exp:
            p["experience"] = exp
            prov.append(_prov("experience", rec.source))

    edu_raw = f.get("education") or []
    if isinstance(edu_raw, list) and edu_raw:
        edu = []
        for e in edu_raw:
            if not isinstance(e, dict):
                continue
            end_year = e.get("endYear") or e.get("graduationYear")
            edu.append({
                "institution": e.get("institution") or e.get("school"),
                "degree": e.get("degree"),
                "field": e.get("field") or e.get("major"),
                "end_year": int(end_year) if isinstance(end_year, (int, float)) else None,
            })
        if edu:
            p["education"] = edu
            prov.append(_prov("education", rec.source))

    p["provenance"] = prov
    return p


def from_github(rec: SourceRecord) -> Dict[str, Any]:
    p = empty_profile("")
    f = rec.fields
    prov = []

    name = f.get("name")
    if name:
        p["full_name"] = name.strip()
        prov.append(_prov("full_name", rec.source))

    bio = f.get("bio")
    if bio:
        p["headline"] = bio.strip()
        prov.append(_prov("headline", rec.source))

    login = f.get("login")
    html_url = f.get("html_url") or (f"https://github.com/{login}" if login else None)
    if html_url:
        p["links"] = [{"type": "github", "url": html_url}]
        prov.append(_prov("links", rec.source))

    blog = f.get("blog")
    if blog:
        p["links"].append({"type": "portfolio", "url": blog})

    email = norm.normalize_email(f.get("email"))
    if email:
        p["emails"] = [email]
        prov.append(_prov("emails", rec.source))

    location = f.get("location")
    if location:
        p["location"] = norm.normalize_location(location)
        prov.append(_prov("location", rec.source))

    langs = f.get("_languages") or []
    if langs:
        names = [norm.canonicalize_skill(l) for l in langs]
        p["skills"] = [{"name": n, "confidence": None, "source": [rec.source]}
                        for n in names if n]
        prov.append(_prov("skills", rec.source, "derived"))

    p["provenance"] = prov
    return p


def from_linkedin(rec: SourceRecord) -> Dict[str, Any]:
    p = empty_profile("")
    f = rec.fields
    prov = []

    name = f.get("full_name") or f.get("name")
    if name:
        p["full_name"] = name.strip()
        prov.append(_prov("full_name", rec.source))

    headline = f.get("headline")
    if headline:
        p["headline"] = headline.strip()
        prov.append(_prov("headline", rec.source))

    location = f.get("location")
    if location:
        p["location"] = norm.normalize_location(location)
        prov.append(_prov("location", rec.source))

    p["links"] = [{"type": "linkedin", "url": rec.source_id}]
    prov.append(_prov("links", rec.source))

    skills_raw = f.get("skills") or []
    if isinstance(skills_raw, list) and skills_raw:
        names = [norm.canonicalize_skill(s) for s in skills_raw]
        p["skills"] = [{"name": n, "confidence": None, "source": [rec.source]}
                        for n in names if n]
        prov.append(_prov("skills", rec.source))

    exp_raw = f.get("experience") or []
    if isinstance(exp_raw, list) and exp_raw:
        exp = []
        for e in exp_raw:
            if not isinstance(e, dict):
                continue
            exp.append({
                "company": e.get("company"),
                "title": e.get("title"),
                "start": norm.normalize_month(e.get("start")),
                "end": norm.normalize_month(e.get("end")),
                "summary": e.get("summary"),
            })
        if exp:
            p["experience"] = exp
            prov.append(_prov("experience", rec.source))

    edu_raw = f.get("education") or []
    if isinstance(edu_raw, list) and edu_raw:
        edu = []
        for e in edu_raw:
            if not isinstance(e, dict):
                continue
            edu.append({
                "institution": e.get("institution") or e.get("school"),
                "degree": e.get("degree"),
                "field": e.get("field"),
                "end_year": e.get("end_year"),
            })
        if edu:
            p["education"] = edu
            prov.append(_prov("education", rec.source))

    p["provenance"] = prov
    return p


def from_resume(rec: SourceRecord) -> Dict[str, Any]:
    p = empty_profile("")
    f = rec.fields
    prov = []

    if f.get("full_name"):
        p["full_name"] = f["full_name"]
        prov.append(_prov("full_name", rec.source, "derived"))

    email = norm.normalize_email(f.get("email"))
    if email:
        p["emails"] = [email]
        prov.append(_prov("emails", rec.source, "derived"))

    phone = norm.normalize_phone(f.get("phone"))
    if phone:
        p["phones"] = [phone]
        prov.append(_prov("phones", rec.source, "derived"))

    if f.get("skills_line"):
        names = [norm.canonicalize_skill(s) for s in f["skills_line"].split(",")]
        skills = [{"name": n, "confidence": None, "source": [rec.source]}
                  for n in names if n]
        if skills:
            p["skills"] = skills
            prov.append(_prov("skills", rec.source, "derived"))

    p["provenance"] = prov
    return p


def from_recruiter_notes(rec: SourceRecord) -> Dict[str, Any]:
    p = empty_profile("")
    f = rec.fields
    prov = []

    email = norm.normalize_email(f.get("email"))
    if email:
        p["emails"] = [email]
        prov.append(_prov("emails", rec.source))

    phone = norm.normalize_phone(f.get("phone"))
    if phone:
        p["phones"] = [phone]
        prov.append(_prov("phones", rec.source))

    if f.get("skills_line"):
        names = [norm.canonicalize_skill(s) for s in f["skills_line"].split(",")]
        skills = [{"name": n, "confidence": None, "source": [rec.source]}
                  for n in names if n]
        if skills:
            p["skills"] = skills
            prov.append(_prov("skills", rec.source))

    yoe = f.get("years_experience")
    if yoe:
        m = None
        import re
        match = re.search(r"\d+(\.\d+)?", str(yoe))
        if match:
            p["years_experience"] = float(match.group(0))
            prov.append(_prov("years_experience", rec.source, "derived"))

    company = f.get("current_company")
    if company:
        p["experience"] = [{"company": company, "title": None, "start": None,
                             "end": None, "summary": None}]
        prov.append(_prov("experience", rec.source, "derived"))

    p["provenance"] = prov
    return p


DISPATch = {
    "recruiter_csv": from_recruiter_csv,
    "ats_json": from_ats_json,
    "github_profile": from_github,
    "linkedin_profile": from_linkedin,
    "resume_file": from_resume,
    "recruiter_notes": from_recruiter_notes,
}


def normalize_record(source_type: str, rec: SourceRecord) -> Dict[str, Any]:
    fn = DISPATch.get(source_type)
    if not fn:
        return empty_profile("")
    try:
        return fn(rec)
    except Exception:
        # A single bad record degrades to "nothing extracted", never a crash.
        out = empty_profile("")
        out["provenance"] = [_prov("_extraction_error", rec.source, "failed")]
        return out

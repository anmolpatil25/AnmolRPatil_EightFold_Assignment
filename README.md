# Multi-Source Candidate Data Transformer

Eightfold Engineering Intern (Jul–Dec 2026) — Assignment submission.

Ingests candidate data from structured and unstructured sources, normalizes
and merges it into one canonical profile per candidate, scores confidence,
and projects it into either the default canonical schema or a runtime
JSON config — no code changes needed to reshape output.

## Pipeline

```
detect → extract → normalize → merge → confidence → project → validate
```

1. **detect** (`detect.py`) — guesses source type from a path/URL (extension,
   `github.com/...`, `linkedin.com/in/...`). Callers can override with
   `path:type` on the CLI when detection would guess wrong.
2. **extract** (`sources/*.py`) — one parser per source, each returning loose
   source-specific fields. Never raises; a malformed file yields zero
   records instead of crashing the run.
3. **normalize** (`normalize.py`, applied inside `extract.py`'s per-source
   mappers) — phones → E.164 (best-effort, no external dep), locations →
   `{city, region, country}` with country as ISO-3166 alpha-2, dates →
   `YYYY-MM`, skills → a lowercase canonical name via a synonym table
   (`js`/`javascript`/`es6` → `javascript`, `k8s` → `kubernetes`, etc.).
4. **merge** (`merge.py`) — groups per-source partial profiles into one
   record per real candidate via union-find over identity keys (normalized
   email, normalized full name), so a record with only a name still links
   up with a record that has both. Scalar fields (name, headline, location,
   years of experience) are resolved by highest source reliability; list
   fields (emails, phones, links, skills, experience, education) are
   unioned and deduped, not overwritten.
5. **confidence** (`confidence.py`) — per-field confidence = source
   reliability, boosted for corroboration across independent sources, capped
   at 0.99. `overall_confidence` is a weighted average (identity fields like
   name/email weighted higher than e.g. education).
6. **project** (`project.py`) — the configurable-output layer. With no
   `--config`, emits the full canonical schema. With a config, it
   selects/renames/remaps fields via dotted/bracket paths
   (`skills[].name`, `emails[0]`, `location.country`), applies an optional
   re-normalization hint at projection time, and follows `on_missing`:
   `null` (default), `omit`, or `error`.
7. **validate** (`validate.py`) — checks the *projected* output against
   whatever schema produced it (config or default). A candidate that fails
   validation is excluded from the output array and written to
   `--rejected-output` instead, with the reason — never silently dropped,
   never crashes the batch.

## Quick start

```bash
pip install -r requirements.txt   # pypdf, python-docx (stdlib otherwise)

# Default canonical schema, all six sample sources:
python3 -m candidate_transformer.cli \
  --input sample_data/recruiter.csv \
  --input sample_data/ats_export.json \
  --input sample_data/jordan_resume.pdf \
  --input sample_data/marcus_notes.txt \
  --input "https://github.com/ashav" \
  --input "https://linkedin.com/in/asha-verma-eng" \
  --output output/default_schema_output.json \
  --rejected-output output/rejected.json

# Same inputs, reshaped via a runtime config (no code changes):
python3 -m candidate_transformer.cli \
  --input sample_data/recruiter.csv \
  --input sample_data/ats_export.json \
  --input sample_data/jordan_resume.pdf \
  --input sample_data/marcus_notes.txt \
  --input "https://github.com/ashav" \
  --input "https://linkedin.com/in/asha-verma-eng" \
  --config sample_data/config_example.json \
  --output output/custom_config_output.json

# Run tests:
python3 -m unittest discover -s tests -v
```

`--input path:type` forces a source type when extension-based detection is
ambiguous (`.txt` defaults to `recruiter_notes`; pass `resume.txt:resume_file`
to override).

### Offline GitHub/LinkedIn

GitHub: prefers a curated local fixture (`sample_data/github_mock/<username>.json`)
when one exists, falling back to the live REST API only for usernames with
no fixture. This makes the sample-data demo deterministic regardless of
whether the machine running it has network access — a real account's live
data could differ from the curated fixture and change merge results between
environments otherwise. In a non-demo deployment (real candidates, no
fixture present), it calls the live API directly.

LinkedIn has no public profile-lookup API without a vendor partnership, so
that source is vendor-JSON-in, not live-HTTP-out, even in production —
`sources/linkedin_profile.py` reads `sample_data/linkedin_mock/<slug>.json`.
Swapping in a real enrichment vendor only touches that one file.

## Design decisions

- **Match keys**: email (normalized) first, normalized full name as
  fallback, joined via union-find so a record only carrying a name still
  links to a record that also has an email. **Known limitation**: this is
  exact-string name matching, not fuzzy — "Jon Smith" won't merge with
  "Jonathan Smith", and a same-named-but-different person with no
  corroborating email anywhere in their record group could falsely merge.
  Production-grade identity resolution would add phone as a third key and/or
  fuzzy name + employer corroboration; left out here under time pressure.
  The sample data deliberately includes a case where this limitation shows
  up: "Marcus Lee" from the CSV/ATS sources (no email there) stays a
  separate candidate from the "Marcus Lee" mentioned in the recruiter notes
  (which has an email) — same person in reality, two candidates in output,
  flagged in the demo video.
- **Conflict resolution**: scalar fields use a static source-reliability
  table (`schema.SOURCE_RELIABILITY`) — recruiter CSV and ATS are trusted
  most since they're recruiter-system-owned; resume/notes free text least,
  since they're the noisiest to parse. This is a starting prior, meant to
  be tuned per engagement, not a claim about ground truth.
- **Confidence**: corroboration (multiple independent sources agreeing)
  raises confidence; a field from a single low-reliability source stays low
  even if it's the only thing we have.
- **Graceful degradation**: every extractor swallows its own errors and
  returns `[]` rather than raising; a missing file, an empty CSV, garbage
  JSON, or an unparsed phone all degrade to `null`/empty list in the
  canonical profile, never a crash. The full pipeline is exercised against
  exactly these cases in `tests/test_pipeline.py`
  (`TestEndToEndEdgeCases`).
- **Validation vs. crashing**: a candidate that can't satisfy a `required`
  field under the configured `on_missing` policy is excluded from the main
  output and written to `--rejected-output` with the reason, so one bad
  candidate never takes down a batch of thousands.

## Edge cases handled

1. Empty/blank CSV rows — skipped, not crashed on.
2. A field present in one source and absent in another (e.g. Asha has an
   email in CSV/ATS but GitHub returns `email: null`) — merge unions what
   exists instead of nulling out the whole field.
3. Conflicting values across sources for the same field (e.g. years of
   experience as a clean int in ATS vs. free text "roughly 9" in notes) —
   resolved by source reliability, not last-write-wins.
4. Garbage/wrong-typed value (`"yearsOfExperience": "garbage-not-a-number"`
   in the ATS sample) — fails the type check silently for that field
   (treated as absent), not propagated as a string into a numeric field.
5. Missing candidate name, present only as an email (the "Priya" sample
   record) — merges correctly via email even with `full_name: null` in
   every contributing source.

## What was deliberately left out

- Fuzzy/phonetic name matching (see "Match keys" above).
- A web UI — CLI only, per the assignment's stated priority order.
- Live network calls to GitHub when no token is configured rate-limit
  quickly; the mock-fixture fallback exists specifically to keep grading
  reproducible without requiring a token.
- Resume parsing beyond a few labeled regex heuristics (name/email/phone/
  skills line) — a real resume parser (e.g. ML-based section detection)
  was out of scope for the time available; free-text sources are weighted
  lowest in confidence specifically to reflect this.

## Repo layout

```
candidate_transformer/
  schema.py          canonical profile shape + source reliability table
  normalize.py        phone / location / date / skill / email normalizers
  detect.py            source-type detection from path/URL
  extract.py           per-source loose-fields -> partial canonical profile
  merge.py             union-find identity resolution + conflict resolution
  confidence.py        per-field + overall confidence scoring
  project.py            runtime-config-driven output projection
  validate.py           checks projected output against its own config
  pipeline.py            orchestrates the whole flow
  cli.py                  command-line entrypoint
  sources/
    recruiter_csv.py, ats_json.py, github_profile.py,
    linkedin_profile.py, resume_file.py, recruiter_notes.py
sample_data/            sample inputs across all 6 source types + 2 configs
tests/test_pipeline.py  unit + end-to-end tests, incl. required edge cases
output/                  sample run output (committed for convenience)
```

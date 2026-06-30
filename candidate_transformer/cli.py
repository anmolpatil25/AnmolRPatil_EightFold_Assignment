#!/usr/bin/env python3
"""
Minimal CLI input/output surface.

Usage:
    python3 -m candidate_transformer.cli \\
        --input recruiter.csv --input ats.json --input https://github.com/octocat \\
        --config config.json \\
        --output out.json

    # default schema, no config:
    python3 -m candidate_transformer.cli --input recruiter.csv --input notes.txt --output out.json

Each --input may optionally pin a type with --input path:type, e.g.
    --input "notes.txt:recruiter_notes"
to disambiguate when extension-based detection would guess wrong
(.txt is ambiguous between resume_file and recruiter_notes).
"""

import argparse
import json
import sys

from .pipeline import run_pipeline


def parse_input_arg(raw: str) -> dict:
    if ":" in raw and not raw.startswith("http") and raw.rsplit(":", 1)[-1].isalpha():
        path, type_hint = raw.rsplit(":", 1)
        return {"path": path, "type": type_hint}
    return {"path": raw}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Multi-source candidate data transformer")
    parser.add_argument("--input", action="append", required=True,
                         help="path or URL to a source input; repeatable. "
                              "Optionally 'path:source_type' to force detection.")
    parser.add_argument("--config", help="path to a projection config JSON; "
                                          "omit to use the full default canonical schema")
    parser.add_argument("--output", default="-", help="output path, or '-' for stdout")
    parser.add_argument("--rejected-output", help="optional path to dump rejected/invalid candidates")
    args = parser.parse_args(argv)

    inputs = [parse_input_arg(i) for i in args.input]

    config = None
    if args.config:
        with open(args.config, encoding="utf-8") as f:
            config = json.load(f)

    records, rejected = run_pipeline(inputs, config=config, log=sys.stderr)

    out_json = json.dumps(records, indent=2, ensure_ascii=False)
    if args.output == "-":
        print(out_json)
    else:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(out_json)
        print(f"[info] wrote {len(records)} candidate(s) to {args.output}", file=sys.stderr)

    if rejected:
        print(f"[info] {len(rejected)} candidate(s) rejected/flagged", file=sys.stderr)
        if args.rejected_output:
            with open(args.rejected_output, "w", encoding="utf-8") as f:
                json.dump(rejected, f, indent=2, ensure_ascii=False)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

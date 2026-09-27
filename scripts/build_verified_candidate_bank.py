#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import jsonschema

from engine.pipeline.verification import build_verified_candidate_bank


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Apply a verification manifest to a candidate bank and aggregate review."
    )
    parser.add_argument("candidate_bank", type=Path)
    parser.add_argument("aggregate_review", type=Path)
    parser.add_argument("verification_manifest", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    candidate = json.loads(args.candidate_bank.read_text(encoding="utf-8"))
    aggregate = json.loads(args.aggregate_review.read_text(encoding="utf-8"))
    manifest = json.loads(args.verification_manifest.read_text(encoding="utf-8"))

    manifest_schema = json.loads(
        (ROOT / "schema/verification-manifest.schema.json").read_text(encoding="utf-8")
    )
    jsonschema.Draft202012Validator(manifest_schema).validate(manifest)

    bank = build_verified_candidate_bank(candidate, aggregate, manifest)
    bank_schema = json.loads(
        (ROOT / "schema/verified-candidate-bank.schema.json").read_text(encoding="utf-8")
    )
    jsonschema.Draft202012Validator(bank_schema).validate(bank)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(bank, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(bank["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

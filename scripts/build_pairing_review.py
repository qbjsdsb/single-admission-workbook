#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import jsonschema

from engine.pipeline.reconcile import reconcile_candidate_and_evidence


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a fail-closed pairing/evidence review queue."
    )
    parser.add_argument("candidate_bank", type=Path)
    parser.add_argument("evidence_bank", type=Path)
    parser.add_argument("--source-pair-confidence", default="name_exact")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    candidate = json.loads(args.candidate_bank.read_text(encoding="utf-8"))
    evidence = json.loads(args.evidence_bank.read_text(encoding="utf-8"))
    review = reconcile_candidate_and_evidence(
        candidate,
        evidence,
        source_pair_confidence=args.source_pair_confidence,
    )

    schema = json.loads(
        (ROOT / "schema/pairing-review.schema.json").read_text(encoding="utf-8")
    )
    jsonschema.Draft202012Validator(schema).validate(review)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(review, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(review["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

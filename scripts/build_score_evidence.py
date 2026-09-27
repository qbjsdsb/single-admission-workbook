#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import jsonschema

from engine.pipeline.scoring import build_score_evidence


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract section score evidence from a Candidate Bank."
    )
    parser.add_argument("candidate_bank", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    candidate = json.loads(args.candidate_bank.read_text(encoding="utf-8"))
    evidence = build_score_evidence(candidate)

    schema = json.loads(
        (ROOT / "schema/score-evidence.schema.json").read_text(encoding="utf-8")
    )
    jsonschema.Draft202012Validator(schema).validate(evidence)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(evidence["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

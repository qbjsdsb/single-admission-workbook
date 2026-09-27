#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import jsonschema

from engine.pipeline.teacher_enrichment import build_teacher_enrichment


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build reviewed teacher analysis/notes enrichment from a pairing review and evidence bank."
    )
    parser.add_argument("pairing_review", type=Path)
    parser.add_argument("evidence_bank", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    result = build_teacher_enrichment(
        load(args.pairing_review),
        load(args.evidence_bank),
    )
    schema = load(ROOT / "schema/teacher-enrichment-batch.schema.json")
    jsonschema.Draft202012Validator(schema).validate(result)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

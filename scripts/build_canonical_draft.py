#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import jsonschema

from engine.pipeline.canonical_promotion import promote_to_canonical_draft


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Promote scored verified candidates into schema-valid canonical drafts."
    )
    parser.add_argument("scored_verified_bank", type=Path)
    parser.add_argument("classification_manifest", type=Path)
    parser.add_argument("--teacher-enrichment", type=Path)
    parser.add_argument("--candidate-bank", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    scored = load(args.scored_verified_bank)
    classification = load(args.classification_manifest)
    enrichment = load(args.teacher_enrichment) if args.teacher_enrichment else None
    candidate_bank = load(args.candidate_bank) if args.candidate_bank else None

    manifest_schema = load(ROOT / "schema/classification-manifest.schema.json")
    jsonschema.Draft202012Validator(manifest_schema).validate(classification)
    if enrichment is not None:
        enrichment_schema = load(ROOT / "schema/teacher-enrichment.schema.json")
        jsonschema.Draft202012Validator(enrichment_schema).validate(enrichment)

    draft = promote_to_canonical_draft(
        scored,
        classification,
        teacher_enrichment=enrichment,
        candidate_bank=candidate_bank,
    )
    batch_schema = load(ROOT / "schema/canonical-draft.schema.json")
    jsonschema.Draft202012Validator(batch_schema).validate(draft)
    question_schema = load(ROOT / "schema/question.schema.json")
    validator = jsonschema.Draft202012Validator(question_schema)
    for question in draft["questions"]:
        validator.validate(question)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(draft, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(draft["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

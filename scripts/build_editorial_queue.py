#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import jsonschema

from engine.pipeline.editorial_queue import build_editorial_queue


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Collapse candidate, answer, score, classification and analysis review into one queue."
    )
    parser.add_argument("candidate_bank", type=Path)
    parser.add_argument("aggregate_review", type=Path)
    parser.add_argument("score_evidence", type=Path)
    parser.add_argument("classification_manifest", type=Path)
    parser.add_argument("--verified-candidate-bank", type=Path)
    parser.add_argument("--teacher-enrichment", type=Path)
    parser.add_argument("--allow-missing-analysis", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    queue = build_editorial_queue(
        load(args.candidate_bank),
        load(args.aggregate_review),
        load(args.score_evidence),
        load(args.classification_manifest),
        verified_candidate_bank=(
            load(args.verified_candidate_bank) if args.verified_candidate_bank else None
        ),
        teacher_enrichment=(
            load(args.teacher_enrichment) if args.teacher_enrichment else None
        ),
        require_teacher_analysis=not args.allow_missing_analysis,
    )

    schema = load(ROOT / "schema/editorial-queue.schema.json")
    jsonschema.Draft202012Validator(schema).validate(queue)

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "editorial-queue.json").write_text(
        json.dumps(queue, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    with (args.out / "editorial-queue.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "priority",
                "state",
                "source_number",
                "section_key",
                "candidate_id",
                "next_action",
                "issue_codes",
                "details",
            ],
        )
        writer.writeheader()
        for entry in queue["entries"]:
            writer.writerow({
                "priority": entry["priority"],
                "state": entry["state"],
                "source_number": entry["source_number"],
                "section_key": entry["section_key"],
                "candidate_id": entry["candidate_id"],
                "next_action": entry["next_action"],
                "issue_codes": "|".join(x["code"] for x in entry["issues"]),
                "details": " | ".join(x["detail"] for x in entry["issues"]),
            })

    print(json.dumps(queue["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

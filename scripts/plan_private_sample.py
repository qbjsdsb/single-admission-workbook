#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import yaml
import jsonschema

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.pipeline.sample_selection import (
    build_sample_book_manifests,
    select_sample_questions,
)


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Plan a private student/teacher sample from a Canonical Draft."
    )
    parser.add_argument("canonical_draft", type=Path)
    parser.add_argument("curriculum", type=Path, help="JSON curriculum mapping")
    parser.add_argument("--ids", type=Path, help="Optional newline-separated canonical IDs")
    parser.add_argument("--allow-missing-analysis", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    draft = load_json(args.canonical_draft)
    curriculum = load_json(args.curriculum)
    requested = None
    if args.ids:
        requested = [
            line.strip()
            for line in args.ids.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    selection = select_sample_questions(
        draft,
        curriculum,
        require_teacher_analysis=not args.allow_missing_analysis,
        requested_ids=requested,
    )
    selection_schema = load_json(ROOT / "schema/sample-selection.schema.json")
    jsonschema.Draft202012Validator(selection_schema).validate(selection)

    books = []
    if selection["selected_question_ids"]:
        books = build_sample_book_manifests(selection, draft, curriculum)

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "selection.json").write_text(
        json.dumps(selection, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (args.out / "books.json").write_text(
        json.dumps(books, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        **selection["summary"],
        "books": len(books),
        "status": "private_sample_plan_not_release",
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

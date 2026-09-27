#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]

def main() -> int:
    build = ROOT / "build/e2e"
    q_schema = json.loads((ROOT / "schema/question.schema.json").read_text(encoding="utf-8"))
    b_schema = json.loads((ROOT / "schema/book.schema.json").read_text(encoding="utf-8"))
    qv = Draft202012Validator(q_schema)
    bv = Draft202012Validator(b_schema)

    qfiles = sorted((build / "canonical").glob("*.json"))
    if len(qfiles) != 4:
        raise AssertionError(f"expected 4 canonical questions, got {len(qfiles)}")
    for path in qfiles:
        qv.validate(json.loads(path.read_text(encoding="utf-8")))

    books = []
    for edition in ("student", "teacher"):
        book = json.loads((build / f"{edition}.book.json").read_text(encoding="utf-8"))
        bv.validate(book)
        books.append(book)
        if not (build / edition / "main.tex").is_file():
            raise AssertionError(f"missing rendered TeX for {edition}")

    s_ids = [q for ch in books[0]["chapters"] for sec in ch["sections"] for q in sec["question_ids"]]
    t_ids = [q for ch in books[1]["chapters"] for sec in ch["sections"] for q in sec["question_ids"]]
    if s_ids != t_ids:
        raise AssertionError("student/teacher manifests do not use the same ordered question IDs")

    summary = json.loads((build / "summary.json").read_text(encoding="utf-8"))
    if summary["answers_linked"] != 4:
        raise AssertionError(f"expected 4 linked answers, got {summary['answers_linked']}")
    if summary["analyses_linked"] != 4:
        raise AssertionError(f"expected 4 linked analyses, got {summary['analyses_linked']}")

    print("E2E structured-data validation passed")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

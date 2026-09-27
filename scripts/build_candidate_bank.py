#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import jsonschema

from engine.parse.candidate_bank import dumps_candidate_bank, extract_candidate_bank


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a reviewable candidate bank from a Document AST or intake result."
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("--subject", required=True, choices=["english", "politics"])
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    document = payload.get("document_ast", payload)
    bank = extract_candidate_bank(
        document,
        subject=args.subject,
        source_id=args.source_id,
    )

    schema = json.loads(
        (ROOT / "schema/candidate-bank.schema.json").read_text(encoding="utf-8")
    )
    jsonschema.Draft202012Validator(schema).validate(bank)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(dumps_candidate_bank(bank) + "\n", encoding="utf-8")
    print(json.dumps(bank["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

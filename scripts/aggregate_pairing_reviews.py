#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import jsonschema

from engine.pipeline.verification import aggregate_pairing_reviews


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Aggregate multiple pairing-review JSON files for one candidate source."
    )
    parser.add_argument("reviews", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    reviews = [json.loads(path.read_text(encoding="utf-8")) for path in args.reviews]
    aggregate = aggregate_pairing_reviews(reviews)

    schema = json.loads(
        (ROOT / "schema/verification-aggregate.schema.json").read_text(encoding="utf-8")
    )
    jsonschema.Draft202012Validator(schema).validate(aggregate)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(aggregate, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(aggregate["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

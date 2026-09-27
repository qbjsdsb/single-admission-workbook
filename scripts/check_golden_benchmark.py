#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.parse.options import parse_options
from engine.quality.evidence import evaluate_answer_evidence


def main() -> int:
    data = json.loads(
        (ROOT / "examples/benchmarks/parser-golden-v01.json").read_text(encoding="utf-8")
    )
    checked = 0

    for case in data["option_cases"]:
        result = parse_options(case["paragraphs"])
        labels = [label for label, _ in result.options]
        if result.status != case["status"] or labels != case["labels"]:
            raise AssertionError(
                f"{case['name']}: got status={result.status}, labels={labels}"
            )
        checked += 1

    for case in data["evidence_cases"]:
        result = evaluate_answer_evidence(case["question_id"], case["evidence"])
        if result.status != case["status"]:
            raise AssertionError(
                f"{case['name']}: got evidence status={result.status}"
            )
        checked += 1

    print(f"Golden benchmark passed: {checked} synthetic cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

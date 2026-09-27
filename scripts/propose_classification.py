#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import jsonschema

from engine.pipeline.classification import build_safe_classification_proposals


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create fail-closed classification proposals from source structure."
    )
    parser.add_argument("candidate_bank", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    candidate = json.loads(args.candidate_bank.read_text(encoding="utf-8"))
    manifest = build_safe_classification_proposals(candidate)
    schema = json.loads(
        (ROOT / "schema/classification-manifest.schema.json").read_text(encoding="utf-8")
    )
    jsonschema.Draft202012Validator(schema).validate(manifest)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    assigned = sum(1 for x in manifest["decisions"] if x["decision"] == "assign")
    deferred = len(manifest["decisions"]) - assigned
    print(json.dumps({"assigned": assigned, "deferred": deferred}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

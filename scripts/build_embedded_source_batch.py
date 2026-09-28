#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import jsonschema

from engine.parse.candidate_bank import extract_candidate_bank
from engine.parse.evidence_bank import extract_evidence_bank
from engine.pipeline.verification import (
    build_embedded_source_verified_candidate_bank,
)


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def build_embedded_source_batch(
    intake_dir: Path,
    out_dir: Path,
    *,
    subject: str = "english",
) -> dict[str, object]:
    sources = load(intake_dir / "sources.private.json")
    pairs = load(intake_dir / "pairs.private.json")
    paired_paths = {
        str(pair[field])
        for pair in pairs
        for field in ("student_path", "companion_path")
        if pair.get(field)
    }

    candidate_schema = load(ROOT / "schema/candidate-bank.schema.json")
    evidence_schema = load(ROOT / "schema/evidence-bank.schema.json")
    verified_schema = load(ROOT / "schema/verified-candidate-bank.schema.json")

    totals: Counter[str] = Counter()
    source_summaries: list[dict[str, object]] = []

    for source in sorted(sources, key=lambda item: str(item.get("path") or "")):
        if source.get("subject") != subject:
            continue
        if str(source.get("path") or "") in paired_paths:
            continue

        source_id = str(source.get("source_id") or "")
        cache_key = str(source.get("cache_key") or "")
        cache_path = intake_dir / "cache" / f"{cache_key}.json"
        if not source_id or not cache_key or not cache_path.is_file():
            raise ValueError(f"{source_id or source.get('path')}: cached AST missing")

        cached = load(cache_path)
        if cached.get("source_sha256") != source.get("sha256"):
            raise ValueError(f"{source_id}: cache/source digest mismatch")
        document = cached.get("document_ast") or {}

        candidate = extract_candidate_bank(
            document,
            subject=subject,
            source_id=source_id,
        )
        evidence = extract_evidence_bank(
            document,
            subject=subject,
            source_id=source_id,
            source_sha256=source.get("sha256"),
        )
        verified = build_embedded_source_verified_candidate_bank(
            candidate,
            evidence,
        )

        jsonschema.Draft202012Validator(candidate_schema).validate(candidate)
        jsonschema.Draft202012Validator(evidence_schema).validate(evidence)
        jsonschema.Draft202012Validator(verified_schema).validate(verified)

        target = out_dir / source_id
        write_json(target / "candidate-bank.json", candidate)
        write_json(target / "evidence-bank.json", evidence)
        write_json(target / "verified-candidate-bank.json", verified)

        candidate_count = len(candidate.get("candidates") or [])
        verified_count = int(verified["summary"]["verified"])
        deferred_count = int(verified["summary"]["deferred"])
        source_summaries.append({
            "source_id": source_id,
            "source_class": source.get("source_class"),
            "role": source.get("role"),
            "candidate_units": candidate_count,
            "verified": verified_count,
            "deferred": deferred_count,
            "candidate_blockers": len(candidate.get("blockers") or []),
        })
        totals["source_files"] += 1
        totals["candidate_units"] += candidate_count
        totals["verified"] += verified_count
        totals["deferred"] += deferred_count
        totals["candidate_blockers"] += len(candidate.get("blockers") or [])

    summary = {
        "schema_version": 1,
        "subject": subject,
        "source_files": totals["source_files"],
        "candidate_units": totals["candidate_units"],
        "verified": totals["verified"],
        "deferred": totals["deferred"],
        "candidate_blockers": totals["candidate_blockers"],
        "sources": source_summaries,
        "status": "private_embedded_source_review",
    }
    write_json(out_dir / "embedded-source-summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build a conservative verified lane for unpaired sources using "
            "only explicit evidence embedded in the same source."
        )
    )
    parser.add_argument("intake_dir", type=Path)
    parser.add_argument("--subject", default="english", choices=["english"])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = build_embedded_source_batch(
        args.intake_dir,
        args.out,
        subject=args.subject,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

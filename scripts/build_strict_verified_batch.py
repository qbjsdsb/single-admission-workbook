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

from engine.pipeline.scoring import (
    apply_score_evidence,
    auto_apply_corroborated_series_scores,
)
from engine.pipeline.verification import (
    build_strict_source_pair_verification_manifest,
    build_verified_candidate_bank,
)


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def source_text_maps(intake_dir: Path) -> dict[str, dict[str, str]]:
    sources = load(intake_dir / "sources.private.json")
    out: dict[str, dict[str, str]] = {}
    for source in sources:
        source_id = str(source.get("source_id") or "")
        cache_key = str(source.get("cache_key") or "")
        if not source_id or not cache_key:
            continue
        cache_path = intake_dir / "cache" / f"{cache_key}.json"
        if not cache_path.is_file():
            continue
        cached = load(cache_path)
        if cached.get("source_sha256") != source.get("sha256"):
            raise ValueError(f"{source_id}: cache/source digest mismatch")
        document = cached.get("document_ast") or {}
        texts: dict[str, str] = {}
        for block in document.get("blocks") or []:
            if block.get("type") != "paragraph":
                continue
            text = "".join(
                str(inline.get("text") or "")
                for inline in block.get("inlines") or []
                if inline.get("type") in {"text", "mathml_inline_text"}
            ).strip()
            locator = str(block.get("locator") or "")
            if locator and text:
                texts[locator] = text
        out[source_id] = texts
    return out


def build_verified_batch(
    review_dir: Path,
    out_dir: Path,
    *,
    intake_dir: Path | None = None,
) -> dict[str, object]:
    manifest_schema = load(ROOT / "schema/verification-manifest.schema.json")
    verified_schema = load(ROOT / "schema/verified-candidate-bank.schema.json")

    totals: Counter[str] = Counter()
    method_counts: Counter[str] = Counter()
    unresolved_score_reasons: Counter[str] = Counter()
    source_groups = 0

    group_dirs = sorted(path for path in review_dir.iterdir() if path.is_dir())
    all_score_evidence_by_source = {
        group_dir.name: load(group_dir / "score-evidence.json")
        for group_dir in group_dirs
        if (group_dir / "score-evidence.json").is_file()
    }
    all_source_text = source_text_maps(intake_dir) if intake_dir is not None else {}

    for group_dir in group_dirs:
        candidate_path = group_dir / "candidate-bank.json"
        aggregate_path = group_dir / "verification-aggregate.json"
        score_path = group_dir / "score-evidence.json"
        if not (candidate_path.is_file() and aggregate_path.is_file() and score_path.is_file()):
            continue

        candidate = load(candidate_path)
        aggregate = load(aggregate_path)
        score = load(score_path)
        if intake_dir is not None:
            score = auto_apply_corroborated_series_scores(
                candidate,
                score,
                all_score_evidence_by_source=all_score_evidence_by_source,
                source_text_by_source_locator=all_source_text,
            )
        pairing_paths = sorted(
            (group_dir / "companions").glob("*/pairing-review.json")
        )
        pairing_reviews = [load(path) for path in pairing_paths]
        if not pairing_reviews:
            raise ValueError(f"{group_dir.name}: no pairing reviews")

        manifest = build_strict_source_pair_verification_manifest(
            candidate,
            aggregate,
            pairing_reviews,
        )
        jsonschema.Draft202012Validator(manifest_schema).validate(manifest)

        verified = build_verified_candidate_bank(
            candidate,
            aggregate,
            manifest,
        )
        jsonschema.Draft202012Validator(verified_schema).validate(verified)
        scored = apply_score_evidence(verified, score)

        target = out_dir / group_dir.name
        write_json(target / "verification-manifest.json", manifest)
        write_json(target / "verified-candidate-bank.json", verified)
        write_json(target / "resolved-score-evidence.json", score)
        write_json(target / "scored-verified-bank.json", scored)

        source_groups += 1
        totals["candidate_units"] += len(candidate.get("candidates") or [])
        totals["verified"] += int(verified["summary"]["verified"])
        totals["deferred"] += int(verified["summary"]["deferred"])
        totals["rejected"] += int(verified["summary"]["rejected"])
        totals["score_assigned"] += int(scored["summary"]["assigned"])
        totals["score_unresolved"] += int(scored["summary"]["unresolved"])
        for decision in manifest.get("decisions") or []:
            if decision.get("decision") == "approve":
                method_counts[str(decision.get("method") or "")] += 1
        for item in scored.get("unresolved") or []:
            unresolved_score_reasons[str(item.get("reason") or "unknown")] += 1

    if source_groups == 0:
        raise ValueError("no review source groups found")

    summary = {
        "schema_version": 1,
        "source_groups": source_groups,
        "candidate_units": totals["candidate_units"],
        "verified": totals["verified"],
        "deferred": totals["deferred"],
        "rejected": totals["rejected"],
        "verification_methods": dict(sorted(method_counts.items())),
        "score_assigned": totals["score_assigned"],
        "score_unresolved": totals["score_unresolved"],
        "score_unresolved_reasons": dict(sorted(unresolved_score_reasons.items())),
        "status": (
            "verified_and_scored"
            if totals["deferred"] == 0
            and totals["rejected"] == 0
            and totals["score_unresolved"] == 0
            else (
                "verified_candidates_scoring_incomplete"
                if totals["deferred"] == 0
                and totals["rejected"] == 0
                else "verification_or_scoring_incomplete"
            )
        ),
    }
    write_json(out_dir / "batch-verification-summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Promote a private Batch Review with strict source-pair evidence, "
            "then attach available score evidence."
        )
    )
    parser.add_argument("review_dir", type=Path)
    parser.add_argument(
        "--intake",
        type=Path,
        help=(
            "Optional private intake/cache used to validate source locators and "
            "apply same-series score corroboration."
        ),
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    summary = build_verified_batch(
        args.review_dir,
        args.out,
        intake_dir=args.intake,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["deferred"] == 0 and summary["rejected"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())

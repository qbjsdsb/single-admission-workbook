from __future__ import annotations

from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
from typing import Any, Mapping

import jsonschema

from engine.parse.candidate_bank import extract_candidate_bank
from engine.parse.evidence_bank import extract_evidence_bank
from engine.pipeline.reconcile import reconcile_candidate_and_evidence
from engine.pipeline.verification import aggregate_pairing_reviews
from engine.pipeline.scoring import build_score_evidence
from engine.pipeline.classification import build_safe_classification_proposals
from engine.pipeline.teacher_enrichment import build_teacher_enrichment
from engine.pipeline.editorial_queue import build_editorial_queue
from engine.pipeline.intake import write_json

ROOT = Path(__file__).resolve().parents[2]


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _validate(schema_name: str, value: Mapping[str, Any]) -> None:
    schema = _read_json(ROOT / "schema" / schema_name)
    jsonschema.Draft202012Validator(schema).validate(value)


def _load_document_ast(intake_dir: Path, source: Mapping[str, Any]) -> dict[str, Any]:
    cache_key = str(source.get("cache_key") or "")
    if not cache_key:
        raise ValueError(f"{source.get('path')}: missing cache_key")
    cache_path = intake_dir / "cache" / f"{cache_key}.json"
    if not cache_path.is_file():
        raise ValueError(f"{source.get('path')}: cache entry missing")
    cached = _read_json(cache_path)
    if cached.get("source_sha256") != source.get("sha256"):
        raise ValueError(f"{source.get('path')}: cache/source digest mismatch")
    document = cached.get("document_ast")
    if not isinstance(document, dict):
        raise ValueError(f"{source.get('path')}: cached Document AST unavailable")
    return document


def _merge_teacher_enrichments(
    candidate_source_id: str,
    batches: list[Mapping[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Keep only unambiguous teacher prose across companion sources.

    Different valid explanations are not treated as logically conflicting answers,
    but the system must not silently choose one for publication.
    """
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for batch in batches:
        for item in batch.get("items") or []:
            grouped[str(item["candidate_id"])].append(item)

    items: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for candidate_id, variants in sorted(grouped.items()):
        analyses = []
        notes = []
        for item in variants:
            analysis = str(item.get("analysis") or "").strip()
            note = str(item.get("teacher_notes") or "").strip()
            if analysis and analysis not in analyses:
                analyses.append(analysis)
            if note and note not in notes:
                notes.append(note)

        if len(analyses) > 1:
            unresolved.append({
                "candidate_id": candidate_id,
                "reason": "multiple_teacher_analysis_variants",
                "variant_count": len(analyses),
            })
            continue

        merged: dict[str, Any] = {"candidate_id": candidate_id}
        if analyses:
            merged["analysis"] = analyses[0]
        if len(notes) == 1:
            merged["teacher_notes"] = notes[0]
        elif len(notes) > 1:
            unresolved.append({
                "candidate_id": candidate_id,
                "reason": "multiple_teacher_note_variants",
                "variant_count": len(notes),
            })

        if len(merged) > 1:
            items.append(merged)

    manifest = {
        "schema_version": 1,
        "candidate_source_id": candidate_source_id,
        "items": items,
    }
    return manifest, unresolved


def review_cached_source_group(
    *,
    student_source: Mapping[str, Any],
    student_document: Mapping[str, Any],
    companions: list[tuple[Mapping[str, Any], Mapping[str, Any], str]],
    subject: str,
) -> dict[str, Any]:
    source_id = str(student_source["source_id"])
    candidate = extract_candidate_bank(
        student_document,
        subject=subject,
        source_id=source_id,
    )
    score = build_score_evidence(candidate)

    companion_outputs: list[dict[str, Any]] = []
    pairing_reviews: list[dict[str, Any]] = []
    enrichment_batches: list[dict[str, Any]] = []

    for companion_source, companion_document, confidence in companions:
        companion_id = str(companion_source["source_id"])
        evidence = extract_evidence_bank(
            companion_document,
            subject=subject,
            source_id=companion_id,
        )
        pairing = reconcile_candidate_and_evidence(
            candidate,
            evidence,
            source_pair_confidence=confidence,
        )
        enrichment = build_teacher_enrichment(pairing, evidence)
        pairing_reviews.append(pairing)
        enrichment_batches.append(enrichment)
        companion_outputs.append({
            "source": dict(companion_source),
            "evidence_bank": evidence,
            "pairing_review": pairing,
            "teacher_enrichment_batch": enrichment,
        })

    if not pairing_reviews:
        raise ValueError(f"{student_source.get('path')}: no companion reviews")

    aggregate = aggregate_pairing_reviews(pairing_reviews)
    merged_enrichment, enrichment_unresolved = _merge_teacher_enrichments(
        source_id,
        enrichment_batches,
    )
    classification = build_safe_classification_proposals(
        candidate,
        teacher_enrichment=merged_enrichment,
    )
    queue = build_editorial_queue(
        candidate,
        aggregate,
        score,
        classification,
        teacher_enrichment=merged_enrichment,
    )

    return {
        "student_source": dict(student_source),
        "candidate_bank": candidate,
        "score_evidence": score,
        "classification_manifest": classification,
        "verification_aggregate": aggregate,
        "teacher_enrichment": merged_enrichment,
        "teacher_enrichment_unresolved": enrichment_unresolved,
        "editorial_queue": queue,
        "companions": companion_outputs,
    }


def _write_group_result(folder: Path, result: Mapping[str, Any]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    outputs = {
        "candidate-bank.json": result["candidate_bank"],
        "score-evidence.json": result["score_evidence"],
        "classification-manifest.json": result["classification_manifest"],
        "verification-aggregate.json": result["verification_aggregate"],
        "teacher-enrichment.json": result["teacher_enrichment"],
        "editorial-queue.json": result["editorial_queue"],
    }
    schemas = {
        "candidate-bank.json": "candidate-bank.schema.json",
        "score-evidence.json": "score-evidence.schema.json",
        "classification-manifest.json": "classification-manifest.schema.json",
        "verification-aggregate.json": "verification-aggregate.schema.json",
        "teacher-enrichment.json": "teacher-enrichment.schema.json",
        "editorial-queue.json": "editorial-queue.schema.json",
    }
    for name, value in outputs.items():
        _validate(schemas[name], value)
        write_json(folder / name, value)

    write_json(
        folder / "teacher-enrichment-unresolved.json",
        result["teacher_enrichment_unresolved"],
    )

    for companion in result["companions"]:
        companion_id = str(companion["source"]["source_id"])
        cdir = folder / "companions" / companion_id
        cdir.mkdir(parents=True, exist_ok=True)
        for name, schema_name, key in (
            ("evidence-bank.json", "evidence-bank.schema.json", "evidence_bank"),
            ("pairing-review.json", "pairing-review.schema.json", "pairing_review"),
            (
                "teacher-enrichment-batch.json",
                "teacher-enrichment-batch.schema.json",
                "teacher_enrichment_batch",
            ),
        ):
            _validate(schema_name, companion[key])
            write_json(cdir / name, companion[key])
        write_json(cdir / "source.private.json", companion["source"])


def review_intake_directory(
    intake_dir: Path,
    out: Path,
    *,
    subject: str,
) -> dict[str, Any]:
    """Review every exact pair already discovered by private intake.

    Raw source text remains in private derived outputs only. Public repository code
    never receives question payloads.
    """
    sources = _read_json(intake_dir / "sources.private.json")
    pairs = _read_json(intake_dir / "pairs.private.json")
    by_path = {str(item["path"]): item for item in sources}

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for pair in pairs:
        student = by_path.get(str(pair.get("student_path") or ""))
        companion = by_path.get(str(pair.get("companion_path") or ""))
        if student is None or companion is None:
            continue
        if student.get("subject") != subject or companion.get("subject") != subject:
            continue
        groups[str(student["path"])].append(pair)

    results: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []

    for student_path, group_pairs in sorted(groups.items()):
        student = by_path[student_path]
        try:
            student_document = _load_document_ast(intake_dir, student)
            companions: list[tuple[Mapping[str, Any], Mapping[str, Any], str]] = []
            seen: set[str] = set()
            for pair in group_pairs:
                companion = by_path[str(pair["companion_path"])]
                companion_id = str(companion["source_id"])
                if companion_id in seen:
                    continue
                seen.add(companion_id)
                companions.append((
                    companion,
                    _load_document_ast(intake_dir, companion),
                    str(pair.get("confidence") or "name_exact"),
                ))

            result = review_cached_source_group(
                student_source=student,
                student_document=student_document,
                companions=companions,
                subject=subject,
            )
            folder = out / str(student["source_id"])
            _write_group_result(folder, result)
            write_json(folder / "student-source.private.json", student)
            results.append(result)
        except Exception as exc:
            failures.append({
                "student_path": student_path,
                "error": f"{type(exc).__name__}: {exc}",
            })

    issue_counts: Counter[str] = Counter()
    states: Counter[str] = Counter()
    aggregate_counts: Counter[str] = Counter()
    candidate_units = 0
    companion_sources: set[str] = set()

    for result in results:
        candidate_units += len(result["candidate_bank"].get("candidates") or [])
        for entry in result["editorial_queue"].get("entries") or []:
            states[str(entry["state"])] += 1
            for issue in entry.get("issues") or []:
                issue_counts[str(issue["code"])] += 1
        for row in result["verification_aggregate"].get("rows") or []:
            aggregate_counts[str(row["aggregate_status"])] += 1
        for companion in result["companions"]:
            companion_sources.add(str(companion["source"]["source_id"]))

    summary = {
        "schema_version": 1,
        "subject": subject,
        "student_source_groups": len(results),
        "companion_sources": len(companion_sources),
        "candidate_units": candidate_units,
        "failed_student_groups": len(failures),
        "states": dict(sorted(states.items())),
        "issue_counts": dict(sorted(issue_counts.items())),
        "verification_aggregate_counts": dict(sorted(aggregate_counts.items())),
        "status": "review_only_not_verified_or_publishable",
    }
    _validate("batch-review-summary.schema.json", summary)

    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "batch-summary.json", summary)
    write_json(out / "failures.private.json", failures)

    with (out / "editorial-queue.csv").open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "student_source_id",
                "student_path",
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
        for result in results:
            source = result["student_source"]
            for entry in result["editorial_queue"].get("entries") or []:
                writer.writerow({
                    "student_source_id": source["source_id"],
                    "student_path": source["path"],
                    "priority": entry["priority"],
                    "state": entry["state"],
                    "source_number": entry["source_number"],
                    "section_key": entry["section_key"],
                    "candidate_id": entry["candidate_id"],
                    "next_action": entry["next_action"],
                    "issue_codes": "|".join(
                        issue["code"] for issue in entry["issues"]
                    ),
                    "details": " | ".join(
                        issue["detail"] for issue in entry["issues"]
                    ),
                })

    return summary

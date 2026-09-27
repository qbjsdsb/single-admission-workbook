from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping


SUBJECT_PREFIX = {
    "chinese": "CHI",
    "mathematics": "MAT",
    "english": "ENG",
    "politics": "POL",
}


def _canonical_id(subject: str, candidate_id: str) -> str:
    prefix = SUBJECT_PREFIX.get(subject)
    if not prefix:
        raise ValueError(f"unsupported subject: {subject}")
    digest = hashlib.sha256(candidate_id.encode("utf-8")).hexdigest()[:12].upper()
    return f"{prefix}_{digest}"


def _text_rich(text: object) -> list[dict[str, str]]:
    return [{"type": "text", "text": str(text or "")}]


def _classification_index(
    manifest: Mapping[str, Any],
) -> dict[str, Mapping[str, Any]]:
    out: dict[str, Mapping[str, Any]] = {}
    for decision in manifest.get("decisions") or []:
        candidate_id = str(decision.get("candidate_id") or "")
        if not candidate_id:
            raise ValueError("classification decision missing candidate_id")
        if candidate_id in out:
            raise ValueError(f"duplicate classification decision: {candidate_id}")
        out[candidate_id] = decision
    return out


def _teacher_index(
    teacher_enrichment: Mapping[str, Any] | None,
) -> dict[str, Mapping[str, Any]]:
    if not teacher_enrichment:
        return {}
    out: dict[str, Mapping[str, Any]] = {}
    for item in teacher_enrichment.get("items") or []:
        candidate_id = str(item.get("candidate_id") or "")
        if not candidate_id:
            raise ValueError("teacher enrichment missing candidate_id")
        if candidate_id in out:
            raise ValueError(f"duplicate teacher enrichment: {candidate_id}")
        out[candidate_id] = item
    return out


def promote_to_canonical_draft(
    scored_verified_bank: Mapping[str, Any],
    classification_manifest: Mapping[str, Any],
    *,
    teacher_enrichment: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build schema-valid canonical drafts only from fully gated inputs.

    This function does not classify or invent metadata. Missing classification,
    missing score, or unsupported candidate kinds remain unresolved.
    """
    subject = str(scored_verified_bank.get("subject") or "")
    candidate_source_id = str(scored_verified_bank.get("candidate_source_id") or "")
    if classification_manifest.get("candidate_source_id") != candidate_source_id:
        raise ValueError("classification manifest source mismatch")
    if classification_manifest.get("subject") != subject:
        raise ValueError("classification manifest subject mismatch")

    classifications = _classification_index(classification_manifest)
    if teacher_enrichment is not None:
        enrichment_source = teacher_enrichment.get("candidate_source_id")
        if enrichment_source not in {None, candidate_source_id}:
            raise ValueError("teacher enrichment source mismatch")
    teacher = _teacher_index(teacher_enrichment)

    questions: list[dict[str, Any]] = []
    unresolved: list[dict[str, str]] = []

    for item in scored_verified_bank.get("assigned") or []:
        candidate_id = str(item.get("candidate_id") or "")
        if not candidate_id:
            unresolved.append({"candidate_id": "", "reason": "missing_candidate_id"})
            continue

        classification = classifications.get(candidate_id)
        if classification is None:
            unresolved.append({
                "candidate_id": candidate_id,
                "reason": "missing_classification",
            })
            continue
        if classification.get("decision") != "assign":
            unresolved.append({
                "candidate_id": candidate_id,
                "reason": "classification_deferred",
            })
            continue

        score = item.get("score")
        if not isinstance(score, (int, float)) or score <= 0:
            unresolved.append({
                "candidate_id": candidate_id,
                "reason": "missing_or_invalid_score",
            })
            continue

        kind = str(item.get("kind") or "")
        if kind not in {
            "single_choice",
            "fill_blank",
            "material_question",
            "composition",
        }:
            unresolved.append({
                "candidate_id": candidate_id,
                "reason": f"unsupported_canonical_kind:{kind}",
            })
            continue

        question: dict[str, Any] = {
            "id": _canonical_id(subject, candidate_id),
            "subject": subject,
            "kind": kind,
            "chapter_key": str(classification["chapter_key"]),
            "section_key": str(classification["section_key"]),
            "tags": sorted(set(str(x) for x in classification.get("tags") or [])),
            "difficulty": str(classification.get("difficulty") or "standard"),
            "score": float(score),
            "stem": _text_rich(item.get("stem_text")),
            "answer": item.get("verified_answer"),
        }

        if kind == "single_choice":
            options = item.get("options") or []
            if len(options) < 2:
                unresolved.append({
                    "candidate_id": candidate_id,
                    "reason": "single_choice_missing_options",
                })
                continue
            question["options"] = [
                {
                    "label": str(option.get("label") or ""),
                    "content": _text_rich(option.get("text")),
                }
                for option in options
            ]
            question["layout"] = {
                "choice_mode": "auto",
                "keep_together": True,
            }

        enrichment = teacher.get(candidate_id)
        if enrichment:
            if enrichment.get("analysis"):
                question["analysis"] = _text_rich(enrichment["analysis"])
            if enrichment.get("teacher_notes"):
                question["teacher_notes"] = _text_rich(enrichment["teacher_notes"])

        questions.append(question)

    return {
        "schema_version": 1,
        "subject": subject,
        "candidate_source_id": candidate_source_id,
        "questions": questions,
        "unresolved": unresolved,
        "summary": {
            "promoted": len(questions),
            "unresolved": len(unresolved),
        },
    }


def build_book_ready_dataset(
    canonical_draft: Mapping[str, Any],
    curriculum: Mapping[str, Any],
) -> dict[str, Any]:
    """Create a minimal renderer dataset from promoted questions and curriculum.

    This does not claim whole-corpus coverage; it is intended for private sample
    publishing and must not be used as the final release ledger.
    """
    questions = list(canonical_draft.get("questions") or [])
    subject = str(canonical_draft.get("subject") or "")
    chapters = curriculum.get(subject)
    if not isinstance(chapters, list) or not chapters:
        raise ValueError(f"curriculum missing subject: {subject}")

    valid_sections = {
        (str(chapter.get("key")), str(section.get("key")))
        for chapter in chapters
        for section in chapter.get("sections") or []
    }
    for question in questions:
        key = (str(question.get("chapter_key")), str(question.get("section_key")))
        if key not in valid_sections:
            raise ValueError(
                f"{question.get('id')}: classification not present in curriculum: {key}"
            )

    return {
        "questions": questions,
        "curriculum": {subject: chapters},
    }

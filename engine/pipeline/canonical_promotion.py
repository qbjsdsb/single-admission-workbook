from __future__ import annotations

import hashlib
from typing import Any, Mapping


SUBJECT_PREFIX = {
    "chinese": "CHI",
    "mathematics": "MAT",
    "english": "ENG",
    "politics": "POL",
}

DIFFICULTY_ORDER = {
    "basic": 0,
    "standard": 1,
    "advanced": 2,
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


def _build_leaf_question(
    *,
    subject: str,
    item: Mapping[str, Any],
    classification: Mapping[str, Any],
    enrichment: Mapping[str, Any] | None,
    include_placement: bool,
) -> dict[str, Any]:
    candidate_id = str(item.get("candidate_id") or "")
    if item.get("asset_refs"):
        raise ValueError("unresolved_source_visual_asset")
    score = item.get("score")
    if not isinstance(score, (int, float)) or score <= 0:
        raise ValueError("missing_or_invalid_score")

    kind = str(item.get("kind") or "")
    if kind not in {
        "single_choice",
        "fill_blank",
        "material_question",
        "composition",
    }:
        raise ValueError(f"unsupported_canonical_kind:{kind}")

    answer_mode = str(item.get("answer_mode") or "fixed")
    question: dict[str, Any] = {
        "id": _canonical_id(subject, candidate_id),
        "kind": kind,
        "score": float(score),
        "stem": item.get("stem_rich") or _text_rich(item.get("stem_text")),
    }
    if answer_mode == "open_response":
        question["answer_mode"] = "open_response"
    else:
        question["answer"] = item.get("verified_answer")

    if include_placement:
        question.update({
            "subject": subject,
            "chapter_key": str(classification["chapter_key"]),
            "section_key": str(classification["section_key"]),
            "tags": sorted(set(str(x) for x in classification.get("tags") or [])),
            "difficulty": str(classification.get("difficulty") or "standard"),
        })

    if kind == "single_choice":
        options = item.get("options") or []
        if len(options) < 2:
            raise ValueError("single_choice_missing_options")
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

    if enrichment:
        if enrichment.get("analysis"):
            question["analysis"] = _text_rich(enrichment["analysis"])
        if enrichment.get("teacher_notes"):
            question["teacher_notes"] = _text_rich(enrichment["teacher_notes"])
        if enrichment.get("source_sample_response"):
            sample_response = str(enrichment["source_sample_response"])
            question["source_sample_response"] = _text_rich(
                sample_response
            )
            provenance = enrichment.get("source_sample_response_provenance")
            if not isinstance(provenance, Mapping):
                raise ValueError("source sample response is missing its provenance")
            if provenance.get("response_sha256") != hashlib.sha256(
                sample_response.encode("utf-8")
            ).hexdigest():
                raise ValueError("source sample response provenance hash mismatch")
            if not (
                len(provenance.get("evidence_ids") or [])
                == len(provenance.get("locators") or [])
                == len(provenance.get("paragraph_sha256") or [])
            ):
                raise ValueError("source sample response paragraph provenance is incomplete")
            question["source_sample_response_provenance"] = dict(provenance)

    return question


def _max_difficulty(classifications: list[Mapping[str, Any]]) -> str:
    return max(
        (
            str(item.get("difficulty") or "standard")
            for item in classifications
        ),
        key=lambda value: DIFFICULTY_ORDER.get(value, 1),
    )


def promote_to_canonical_draft(
    scored_verified_bank: Mapping[str, Any],
    classification_manifest: Mapping[str, Any],
    *,
    teacher_enrichment: Mapping[str, Any] | None = None,
    candidate_bank: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build schema-valid canonical drafts only from fully gated inputs.

    Candidate groups are promoted atomically when Candidate Bank group evidence is
    supplied. A cloze/reading passage is never published as detached child items.
    """
    subject = str(scored_verified_bank.get("subject") or "")
    candidate_source_id = str(scored_verified_bank.get("candidate_source_id") or "")
    if classification_manifest.get("candidate_source_id") != candidate_source_id:
        raise ValueError("classification manifest source mismatch")
    if classification_manifest.get("subject") != subject:
        raise ValueError("classification manifest subject mismatch")

    if candidate_bank is not None:
        if candidate_bank.get("source_id") != candidate_source_id:
            raise ValueError("candidate bank source mismatch")
        if candidate_bank.get("subject") != subject:
            raise ValueError("candidate bank subject mismatch")

    classifications = _classification_index(classification_manifest)
    if teacher_enrichment is not None:
        enrichment_source = teacher_enrichment.get("candidate_source_id")
        if enrichment_source not in {None, candidate_source_id}:
            raise ValueError("teacher enrichment source mismatch")
    teacher = _teacher_index(teacher_enrichment)

    assigned = {
        str(item.get("candidate_id") or ""): item
        for item in scored_verified_bank.get("assigned") or []
        if str(item.get("candidate_id") or "")
    }

    questions: list[dict[str, Any]] = []
    unresolved: list[dict[str, str]] = []
    grouped_candidate_ids: set[str] = set()

    for group in ([] if candidate_bank is None else candidate_bank.get("groups") or []):
        group_id = str(group.get("group_id") or "")
        child_ids = [str(x) for x in group.get("child_candidate_ids") or []]
        grouped_candidate_ids.update(child_ids)

        if not group_id or not child_ids:
            unresolved.append({
                "candidate_id": group_id,
                "reason": "invalid_group_structure",
            })
            continue

        if group.get("asset_refs"):
            unresolved.append({
                "candidate_id": group_id,
                "reason": "group_unresolved_source_visual_asset",
            })
            continue

        shared_material = str(group.get("shared_material_text") or "").strip()
        if not shared_material:
            unresolved.append({
                "candidate_id": group_id,
                "reason": "group_missing_shared_material",
            })
            continue

        missing = [candidate_id for candidate_id in child_ids if candidate_id not in assigned]
        if missing:
            unresolved.append({
                "candidate_id": group_id,
                "reason": "group_incomplete_verified_or_score",
            })
            continue

        child_classifications: list[Mapping[str, Any]] = []
        classification_failed = False
        for candidate_id in child_ids:
            classification = classifications.get(candidate_id)
            if classification is None:
                unresolved.append({
                    "candidate_id": group_id,
                    "reason": "group_missing_classification",
                })
                classification_failed = True
                break
            if classification.get("decision") != "assign":
                unresolved.append({
                    "candidate_id": group_id,
                    "reason": "group_classification_deferred",
                })
                classification_failed = True
                break
            child_classifications.append(classification)
        if classification_failed:
            continue

        placements = {
            (
                str(classification["chapter_key"]),
                str(classification["section_key"]),
            )
            for classification in child_classifications
        }
        if len(placements) != 1:
            unresolved.append({
                "candidate_id": group_id,
                "reason": "group_classification_mismatch",
            })
            continue

        children: list[dict[str, Any]] = []
        child_failed = False
        for candidate_id, classification in zip(child_ids, child_classifications):
            try:
                child = _build_leaf_question(
                    subject=subject,
                    item=assigned[candidate_id],
                    classification=classification,
                    enrichment=teacher.get(candidate_id),
                    include_placement=False,
                )
            except ValueError as exc:
                unresolved.append({
                    "candidate_id": group_id,
                    "reason": f"group_child_invalid:{exc}",
                })
                child_failed = True
                break
            children.append(child)
        if child_failed:
            continue

        chapter_key, section_key = next(iter(placements))
        tags = sorted({
            str(tag)
            for classification in child_classifications
            for tag in classification.get("tags") or []
        })
        group_kind = str(group.get("kind") or "")
        if group_kind not in {"cloze_group", "reading_group"}:
            unresolved.append({
                "candidate_id": group_id,
                "reason": f"unsupported_group_kind:{group_kind}",
            })
            continue

        questions.append({
            "id": _canonical_id(subject, group_id),
            "subject": subject,
            "kind": group_kind,
            "chapter_key": chapter_key,
            "section_key": section_key,
            "tags": tags,
            "difficulty": _max_difficulty(child_classifications),
            "score": float(sum(float(child["score"]) for child in children)),
            "stem": group.get("shared_material_rich") or _text_rich(shared_material),
            "answer": [child.get("answer") for child in children],
            "children": children,
        })

    for item in scored_verified_bank.get("assigned") or []:
        candidate_id = str(item.get("candidate_id") or "")
        if not candidate_id:
            unresolved.append({"candidate_id": "", "reason": "missing_candidate_id"})
            continue
        if candidate_id in grouped_candidate_ids:
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

        try:
            question = _build_leaf_question(
                subject=subject,
                item=item,
                classification=classification,
                enrichment=teacher.get(candidate_id),
                include_placement=True,
            )
        except ValueError as exc:
            unresolved.append({
                "candidate_id": candidate_id,
                "reason": str(exc),
            })
            continue

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

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any, Mapping

import yaml

from engine.pipeline.canonical_promotion import promote_to_canonical_draft
from engine.quality.dedup import exact_duplicate_clusters


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def curriculum_from_english_taxonomy(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping) or data.get("subject") != "english":
        raise ValueError("English taxonomy must declare subject: english")
    chapters = data.get("chapters")
    if not isinstance(chapters, list) or not chapters:
        raise ValueError("English taxonomy has no chapters")

    normalized: list[dict[str, Any]] = []
    for chapter in chapters:
        key = str(chapter.get("key") or "").strip()
        title = str(chapter.get("title") or "").strip()
        if not key or not title:
            raise ValueError("English taxonomy chapter needs key/title")
        sections = []
        for section in chapter.get("sections") or []:
            section_key = str(section.get("key") or "").strip()
            section_title = str(section.get("title") or "").strip()
            if not section_key or not section_title:
                raise ValueError(f"{key}: taxonomy section needs key/title")
            sections.append({"key": section_key, "title": section_title})
        if not sections:
            raise ValueError(f"{key}: taxonomy chapter has no sections")
        normalized.append({"key": key, "title": title, "sections": sections})

    return {"english": normalized}


def _teacher_analysis_complete(question: Mapping[str, Any]) -> bool:
    if question.get("kind") in {"cloze_group", "reading_group"}:
        children = question.get("children") or []
        return bool(children) and all(bool(child.get("analysis")) for child in children)
    return bool(question.get("analysis"))


def _answer_signature(question: Mapping[str, Any]) -> str:
    if (
        question.get("kind") == "composition"
        and question.get("answer_mode") == "open_response"
    ):
        return "open_response"
    value = question.get("answer")
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _quality_rank(question: Mapping[str, Any]) -> tuple[int, int, int, str]:
    return (
        1 if _teacher_analysis_complete(question) else 0,
        1 if question.get("source_sample_response") else 0,
        len(json.dumps(question, ensure_ascii=False, sort_keys=True)),
        str(question.get("id") or ""),
    )


def deduplicate_stage_questions(
    questions: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Keep one rich representative per exact exercise, but never hide answer conflicts.

    Final occurrence accounting remains outside this stage preview. This helper only
    prevents the preview book from printing the same exact exercise repeatedly.
    """
    by_id = {str(question.get("id") or ""): question for question in questions}
    duplicate_ids: set[str] = set()
    duplicate_records: list[dict[str, Any]] = []
    conflict_records: list[dict[str, Any]] = []

    for cluster in exact_duplicate_clusters(questions):
        members = [by_id[qid] for qid in cluster.question_ids]
        signatures = {_answer_signature(question) for question in members}
        duplicate_ids.update(cluster.question_ids)

        if len(signatures) != 1:
            conflict_records.append({
                "fingerprint": cluster.fingerprint,
                "question_ids": list(cluster.question_ids),
                "reason": "exact_duplicate_answer_conflict",
            })
            continue

        representative = max(members, key=_quality_rank)
        duplicate_records.append({
            "fingerprint": cluster.fingerprint,
            "representative_question_id": representative["id"],
            "occurrence_question_ids": list(cluster.question_ids),
        })
        duplicate_ids.remove(str(representative["id"]))

    conflict_ids = {
        qid
        for record in conflict_records
        for qid in record["question_ids"]
    }
    kept = [
        question
        for question in questions
        if str(question.get("id") or "") not in duplicate_ids
        and str(question.get("id") or "") not in conflict_ids
    ]
    return kept, duplicate_records, conflict_records


def assemble_english_stage_canonical(
    review_dir: Path,
    verified_dir: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Combine every safely promoted English source group into one stage draft.

    The review directory supplies classification and teacher prose. The verified
    directory supplies only already accepted answer evidence plus score evidence.
    No pre-verification editorial-queue state is treated as publication approval.
    """
    review_groups = {
        path.name: path
        for path in review_dir.iterdir()
        if path.is_dir()
    }
    verified_groups = {
        path.name: path
        for path in verified_dir.iterdir()
        if path.is_dir()
    }
    group_names = sorted(set(review_groups) & set(verified_groups))
    if not group_names:
        raise ValueError("no overlapping English review/verified source groups")

    questions: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    verification_methods: Counter[str] = Counter()
    source_group_summaries: list[dict[str, Any]] = []

    for group_name in group_names:
        rdir = review_groups[group_name]
        vdir = verified_groups[group_name]
        required = {
            "candidate": rdir / "candidate-bank.json",
            "classification": rdir / "classification-manifest.json",
            "teacher": rdir / "teacher-enrichment.json",
            "scored": vdir / "scored-verified-bank.json",
        }
        missing = [name for name, path in required.items() if not path.is_file()]
        if missing:
            unresolved.append({
                "source_group": group_name,
                "reason": "missing_stage_inputs:" + ",".join(sorted(missing)),
            })
            continue

        candidate = _load_json(required["candidate"])
        classification = _load_json(required["classification"])
        teacher = _load_json(required["teacher"])
        scored = _load_json(required["scored"])

        if any(
            str(payload.get("subject") or "") not in {"", "english"}
            for payload in (candidate, classification, scored)
        ):
            unresolved.append({
                "source_group": group_name,
                "reason": "non_english_group_in_english_stage",
            })
            continue

        for item in scored.get("assigned") or []:
            verification_methods[str(item.get("verification_method") or "unknown")] += 1

        draft = promote_to_canonical_draft(
            scored,
            classification,
            teacher_enrichment=teacher,
            candidate_bank=candidate,
        )
        questions.extend(draft.get("questions") or [])
        for item in draft.get("unresolved") or []:
            unresolved.append({
                "source_group": group_name,
                "candidate_id": str(item.get("candidate_id") or ""),
                "reason": str(item.get("reason") or ""),
            })
        source_group_summaries.append({
            "source_group": group_name,
            "promoted": int((draft.get("summary") or {}).get("promoted") or 0),
            "unresolved": int((draft.get("summary") or {}).get("unresolved") or 0),
        })

    ids = [str(question.get("id") or "") for question in questions]
    if len(ids) != len(set(ids)):
        raise ValueError("cross-source canonical question id collision")

    questions, duplicate_records, duplicate_conflicts = deduplicate_stage_questions(
        questions
    )
    unresolved.extend(
        {
            "source_group": "cross-source-dedup",
            "candidate_id": "",
            "reason": record["reason"],
            "question_ids": record["question_ids"],
        }
        for record in duplicate_conflicts
    )

    canonical = {
        "schema_version": 1,
        "subject": "english",
        "candidate_source_id": "english-stage-aggregate",
        "questions": questions,
        "unresolved": unresolved,
        "summary": {
            "promoted": len(questions),
            "unresolved": len(unresolved),
        },
    }
    report = {
        "schema_version": 1,
        "subject": "english",
        "source_groups_considered": len(group_names),
        "source_group_summaries": source_group_summaries,
        "verification_methods": dict(sorted(verification_methods.items())),
        "deduplicated_exact_clusters": len(duplicate_records),
        "deduplicated_exact_occurrences": sum(
            max(0, len(record["occurrence_question_ids"]) - 1)
            for record in duplicate_records
        ),
        "duplicate_answer_conflicts": len(duplicate_conflicts),
        "canonical_question_groups": len(questions),
        "unresolved": len(unresolved),
        "duplicate_records": duplicate_records,
        "duplicate_conflicts": duplicate_conflicts,
        "status": "stage_aggregate_not_final_occurrence_ledger",
    }
    return canonical, report

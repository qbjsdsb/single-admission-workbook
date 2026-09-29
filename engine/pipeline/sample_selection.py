from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

import jsonschema

from engine.quality.dedup import exact_duplicate_clusters
from engine.quality.publication_content import validate_publication_content
from engine.render.latex import SUBJECT_NAMES

ROOT = Path(__file__).resolve().parents[2]


def _has_verified_answer(question: Mapping[str, Any]) -> bool:
    if (
        question.get("kind") == "composition"
        and question.get("answer_mode") == "open_response"
    ):
        return True
    if question.get("kind") in {"cloze_group", "reading_group"}:
        children = question.get("children") or []
        return bool(children) and all(
            child.get("answer") not in (None, "")
            for child in children
        )
    return question.get("answer") not in (None, "")


def _has_teacher_analysis(question: Mapping[str, Any]) -> bool:
    if question.get("kind") in {"cloze_group", "reading_group"}:
        children = question.get("children") or []
        return bool(children) and all(bool(child.get("analysis")) for child in children)
    return bool(question.get("analysis"))


def select_sample_questions(
    canonical_draft: Mapping[str, Any],
    curriculum: Mapping[str, Any],
    *,
    require_teacher_analysis: bool = True,
    requested_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Select publication-safe questions for a private sample.

    This is not whole-corpus release validation. It only selects already-promoted
    Canonical Draft questions and records every exclusion.
    """
    subject = str(canonical_draft.get("subject") or "")
    all_questions = list(canonical_draft.get("questions") or [])
    requested = set(requested_ids or [])
    use_requested = requested_ids is not None

    question_schema = json.loads(
        (ROOT / "schema/question.schema.json").read_text(encoding="utf-8")
    )
    validator = jsonschema.Draft202012Validator(question_schema)

    chapters = curriculum.get(subject)
    if not isinstance(chapters, list) or not chapters:
        raise ValueError(f"curriculum missing subject: {subject}")

    valid_sections = {
        (str(chapter.get("key")), str(section.get("key")))
        for chapter in chapters
        for section in chapter.get("sections") or []
    }

    selected: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []

    for question in all_questions:
        qid = str(question.get("id") or "")
        if use_requested and qid not in requested:
            continue

        try:
            validator.validate(question)
        except jsonschema.ValidationError as exc:
            excluded.append({
                "question_id": qid,
                "reason": f"schema:{exc.message}",
            })
            continue

        if not _has_verified_answer(question):
            excluded.append({"question_id": qid, "reason": "missing_answer"})
            continue
        if require_teacher_analysis and not _has_teacher_analysis(question):
            excluded.append({"question_id": qid, "reason": "missing_teacher_analysis"})
            continue
        if (question.get("chapter_key"), question.get("section_key")) not in valid_sections:
            excluded.append({"question_id": qid, "reason": "invalid_curriculum_assignment"})
            continue

        content_errors = validate_publication_content([question])
        if content_errors:
            excluded.append({
                "question_id": qid,
                "reason": "publication_content:" + content_errors[0],
            })
            continue

        selected.append(question)

    if use_requested:
        known = {str(q.get("id") or "") for q in all_questions}
        for missing in sorted(requested - known):
            excluded.append({"question_id": missing, "reason": "requested_id_not_found"})

    duplicates = exact_duplicate_clusters(selected)
    duplicate_ids = {
        qid for cluster in duplicates for qid in cluster.question_ids
    }
    if duplicate_ids:
        selected = [q for q in selected if q["id"] not in duplicate_ids]
        for cluster in duplicates:
            for qid in cluster.question_ids:
                excluded.append({
                    "question_id": qid,
                    "reason": "unresolved_exact_duplicate_in_sample",
                })

    publication_errors = validate_publication_content(selected)
    if publication_errors:
        raise ValueError(
            "sample publication content blocked:\n" + "\n".join(publication_errors)
        )
    return {
        "schema_version": 1,
        "subject": subject,
        "selected_question_ids": [q["id"] for q in selected],
        "excluded": excluded,
        "summary": {
            "selected": len(selected),
            "excluded": len(excluded),
        },
    }


def build_sample_book_manifests(
    selection: Mapping[str, Any],
    canonical_draft: Mapping[str, Any],
    curriculum: Mapping[str, Any],
    *,
    quote_seed: int = 20260927,
    title_suffix: str = "样章",
) -> list[dict[str, Any]]:
    subject = str(selection.get("subject") or "")
    if subject != canonical_draft.get("subject"):
        raise ValueError("selection and canonical draft subject mismatch")

    selected_ids = set(selection.get("selected_question_ids") or [])
    bank = {q["id"]: q for q in canonical_draft.get("questions") or []}
    if not selected_ids:
        raise ValueError("sample selection is empty")
    if not selected_ids <= set(bank):
        raise ValueError("sample selection references unknown questions")

    by_section: dict[tuple[str, str], list[str]] = defaultdict(list)
    difficulty_order = {"basic": 0, "standard": 1, "advanced": 2}

    for qid in selected_ids:
        q = bank[qid]
        by_section[(q["chapter_key"], q["section_key"])].append(qid)

    for key, ids in by_section.items():
        ids.sort(key=lambda qid: (
            difficulty_order.get(bank[qid].get("difficulty"), 1),
            qid,
        ))

    chapters_out: list[dict[str, Any]] = []
    for chapter in curriculum.get(subject) or []:
        sections_out: list[dict[str, Any]] = []
        for section in chapter.get("sections") or []:
            ids = by_section.get((chapter["key"], section["key"]), [])
            if ids:
                sections_out.append({
                    "key": section["key"],
                    "title": section["title"],
                    "question_ids": ids,
                })
        if sections_out:
            chapters_out.append({
                "key": chapter["key"],
                "title": chapter["title"],
                "sections": sections_out,
            })

    if not chapters_out:
        raise ValueError("sample selection produced no curriculum chapters")

    schema = json.loads((ROOT / "schema/book.schema.json").read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    books: list[dict[str, Any]] = []
    for edition in ("student", "teacher"):
        suffix = str(title_suffix or "").strip()
        label = f"·{suffix}" if suffix else ""
        title = SUBJECT_NAMES[subject] + (
            f"练习册{label}" if edition == "student" else f"教师解析册{label}"
        )
        book = {
            "schema_version": 1,
            "book_id": f"{subject}-sample-{edition}",
            "title": title,
            "subject": subject,
            "edition": edition,
            "paper": "A4",
            "table_of_contents": True,
            "quote_seed": quote_seed,
            "chapters": chapters_out,
        }
        validator.validate(book)
        books.append(book)

    return books

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import jsonschema

from engine.quality.dedup import exact_duplicate_clusters
from engine.render.latex import SUBJECT_NAMES, render_book


ROOT = Path(__file__).resolve().parents[2]


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _has_content(value: object) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return any(_has_content(item) for item in value)
    if isinstance(value, dict):
        return any(
            _has_content(value.get(key))
            for key in ("text", "children", "tex", "asset", "rows")
        )
    return False


def _is_open_response(question: Mapping[str, Any]) -> bool:
    return (
        question.get("kind") == "composition"
        and question.get("answer_mode") == "open_response"
    )


def _validate_publication_payload(question: Mapping[str, Any]) -> None:
    qid = str(question["id"])
    kind = question.get("kind")

    if kind in {"reading_group", "cloze_group"}:
        children = question.get("children") or []
        if not children:
            raise ValueError(f"{qid}: grouped question has no children")
        for index, child in enumerate(children, start=1):
            child_id = str(child.get("id") or f"child-{index}")
            if not _has_content(child.get("stem")):
                raise ValueError(f"{qid}/{child_id}: empty child stem")
            if not _has_content(child.get("answer")):
                raise ValueError(f"{qid}/{child_id}: missing child answer")
            if not _has_content(child.get("analysis")):
                raise ValueError(f"{qid}/{child_id}: missing child analysis")
        return

    if not _has_content(question.get("stem")):
        raise ValueError(f"{qid}: empty stem")

    if _is_open_response(question):
        if not _has_content(question.get("analysis")):
            raise ValueError(f"{qid}: missing open-response analysis")
        return

    if not _has_content(question.get("answer")):
        raise ValueError(f"{qid}: missing answer")
    if not _has_content(question.get("analysis")):
        raise ValueError(f"{qid}: missing analysis")


def normalize_editorial_batch(data: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a small AI-editorial batch without invoking the full production gates.

    This path is intentionally narrow: the editor supplies already-reviewed question
    payloads and verified source locators. It preserves explicit editorial order and
    renders student/teacher editions from exactly the same question objects.

    Full-corpus occurrence accounting remains a final-release concern; this function
    only requires every question in the batch to have at least one verified source
    occurrence so no page becomes provenance-free.
    """

    batch = deepcopy(dict(data))

    batch_schema = json.loads(
        (ROOT / "schema/editorial-batch.schema.json").read_text(encoding="utf-8")
    )
    jsonschema.Draft202012Validator(batch_schema).validate(batch)

    subject = str(batch["subject"])
    chapter_key = str(batch["chapter"]["key"])
    section_key = str(batch["section"]["key"])

    question_schema = json.loads(
        (ROOT / "schema/question.schema.json").read_text(encoding="utf-8")
    )
    question_validator = jsonschema.Draft202012Validator(question_schema)

    ids: list[str] = []
    for question in batch["questions"]:
        qid = str(question.get("id") or "")
        if not qid:
            raise ValueError("editorial batch contains a question without id")
        ids.append(qid)

        if question.get("subject") != subject:
            raise ValueError(
                f"{qid}: subject {question.get('subject')!r} does not match batch {subject!r}"
            )

        existing_chapter = question.get("chapter_key")
        existing_section = question.get("section_key")
        if existing_chapter not in (None, chapter_key):
            raise ValueError(
                f"{qid}: chapter {existing_chapter!r} conflicts with batch {chapter_key!r}"
            )
        if existing_section not in (None, section_key):
            raise ValueError(
                f"{qid}: section {existing_section!r} conflicts with batch {section_key!r}"
            )

        question["chapter_key"] = chapter_key
        question["section_key"] = section_key
        question_validator.validate(question)
        _validate_publication_payload(question)

    if len(ids) != len(set(ids)):
        raise ValueError("editorial batch contains duplicate question ids")

    duplicate_clusters = exact_duplicate_clusters(batch["questions"])
    if duplicate_clusters:
        clusters = [
            ",".join(cluster.question_ids)
            for cluster in duplicate_clusters
        ]
        raise ValueError(
            "editorial batch contains unresolved exact duplicate content: "
            + "; ".join(clusters)
        )

    id_set = set(ids)
    occurrence_ids: list[str] = []
    covered: set[str] = set()
    for occurrence in batch["occurrences"]:
        oid = str(occurrence["id"])
        occurrence_ids.append(oid)
        qid = str(occurrence["question_id"])
        if qid not in id_set:
            raise ValueError(f"{oid}: occurrence references unknown question {qid}")
        if occurrence.get("status") != "verified":
            raise ValueError(f"{oid}: occurrence must be verified before batch rendering")
        covered.add(qid)

    if len(occurrence_ids) != len(set(occurrence_ids)):
        raise ValueError("editorial batch contains duplicate occurrence ids")

    missing = [qid for qid in ids if qid not in covered]
    if missing:
        raise ValueError(
            "editorial batch questions missing verified source occurrence: "
            + ", ".join(missing)
        )

    return batch


def _batch_digest(batch: Mapping[str, Any]) -> str:
    payload = json.dumps(
        batch,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def prepare_editorial_batch(
    data: Mapping[str, Any],
    out: Path,
) -> dict[str, Any]:
    """Prepare a small private editorial batch for immediate visual review."""

    batch = normalize_editorial_batch(data)
    batch_id = str(batch["batch_id"])
    subject = str(batch["subject"])
    question_ids = [str(question["id"]) for question in batch["questions"]]
    bank = {str(question["id"]): question for question in batch["questions"]}

    chapter = batch["chapter"]
    section = batch["section"]
    chapters = [
        {
            "key": str(chapter["key"]),
            "title": str(chapter["title"]),
            "sections": [
                {
                    "key": str(section["key"]),
                    "title": str(section["title"]),
                    "question_ids": question_ids,
                }
            ],
        }
    ]

    subject_name = SUBJECT_NAMES[subject]
    titles = batch.get("titles") or {}
    default_titles = {
        "student": f"体育单招{subject_name}练习册 · {chapter['title']}",
        "teacher": f"体育单招{subject_name}教师解析册 · {chapter['title']}",
    }

    template = (ROOT / "templates/latex/workbook.tex").read_text(encoding="utf-8")
    out.mkdir(parents=True, exist_ok=True)

    _write_json(out / "batch.private.json", batch)
    _write_json(out / "occurrences.private.json", batch["occurrences"])

    editions: list[dict[str, Any]] = []
    for edition in ("student", "teacher"):
        book_id = f"{batch_id}-{edition}"
        book = {
            "schema_version": 1,
            "book_id": book_id,
            "title": str(titles.get(edition) or default_titles[edition]),
            "subject": subject,
            "edition": edition,
            "paper": "A4",
            "quote_seed": int(batch.get("quote_seed", 20260929)),
            "chapters": chapters,
            "table_of_contents": False,
        }

        folder = out / book_id
        folder.mkdir(parents=True, exist_ok=True)
        _write_json(folder / "book.json", book)
        _write_json(
            folder / "questions.private.json",
            [bank[qid] for qid in question_ids],
        )

        tex = render_book(
            template=template,
            book=book,
            questions=bank,
        )
        if edition == "student" and any(
            marker in tex
            for marker in (
                "\\teacheranswer{",
                "\\teacheranalysis{",
                "\\teachernote{",
                "\\teachersampleresponse{",
            )
        ):
            raise ValueError("teacher-only content leaked into student TeX")

        (folder / "main.tex").write_text(tex, encoding="utf-8")
        editions.append(
            {
                "book_id": book_id,
                "edition": edition,
                "question_groups": len(question_ids),
            }
        )

    summary = {
        "schema_version": 1,
        "batch_id": batch_id,
        "subject": subject,
        "chapter_key": str(chapter["key"]),
        "section_key": str(section["key"]),
        "question_groups": len(question_ids),
        "verified_occurrences": len(batch["occurrences"]),
        "source_snapshot_id": batch.get("source_snapshot_id"),
        "batch_sha256": _batch_digest(batch),
        "editions": editions,
        "status": "prepared_editorial_batch_visual_review_required",
    }
    _write_json(out / "batch-build.json", summary)
    return summary

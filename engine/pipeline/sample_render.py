from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from engine.pipeline.sample_selection import (
    build_sample_book_manifests,
    select_sample_questions,
)
from engine.render.latex import render_book


ROOT = Path(__file__).resolve().parents[2]


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def prepare_private_sample(
    canonical_draft: Mapping[str, Any],
    curriculum: Mapping[str, Any],
    out: Path,
    *,
    requested_ids: Iterable[str] | None = None,
    require_teacher_analysis: bool = True,
    quote_seed: int = 20260927,
    title_suffix: str = "样章",
) -> dict[str, Any]:
    """Render a publication-path private sample without claiming whole-corpus release.

    The caller supplies an already promoted Canonical Draft. Only questions that
    pass the existing sample-selection gate are rendered. Source/provenance data
    is not accepted by this function and is therefore not available to leak into
    the publication output.
    """
    selection = select_sample_questions(
        canonical_draft,
        curriculum,
        require_teacher_analysis=require_teacher_analysis,
        requested_ids=requested_ids,
    )
    if not selection["selected_question_ids"]:
        raise ValueError("private sample selection is empty")

    books = build_sample_book_manifests(
        selection,
        canonical_draft,
        curriculum,
        quote_seed=quote_seed,
        title_suffix=title_suffix,
    )

    bank = {
        str(question["id"]): question
        for question in canonical_draft.get("questions") or []
    }
    selected_ids = set(selection["selected_question_ids"])
    selected_questions = {
        qid: bank[qid]
        for qid in selection["selected_question_ids"]
    }

    template = (ROOT / "templates/latex/workbook.tex").read_text(encoding="utf-8")
    out.mkdir(parents=True, exist_ok=True)
    _write_json(out / "selection.json", selection)
    _write_json(out / "books.json", books)

    editions: list[dict[str, Any]] = []
    for book in books:
        folder = out / str(book["book_id"])
        folder.mkdir(parents=True, exist_ok=True)

        manifest_ids = [
            qid
            for chapter in book["chapters"]
            for section in chapter["sections"]
            for qid in section["question_ids"]
        ]
        if set(manifest_ids) != selected_ids:
            raise ValueError(f"{book['book_id']}: manifest/sample question mismatch")

        _write_json(folder / "book.json", book)
        # Private derived content is useful for deterministic QA but stays under
        # build/private or another caller-owned private output directory.
        _write_json(
            folder / "questions.private.json",
            [selected_questions[qid] for qid in manifest_ids],
        )

        tex = render_book(
            template=template,
            book=book,
            questions=selected_questions,
        )
        if book["edition"] == "student" and any(
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
        editions.append({
            "book_id": book["book_id"],
            "edition": book["edition"],
            "question_groups": len(manifest_ids),
        })

    return {
        "schema_version": 1,
        "subject": selection["subject"],
        "selected_question_groups": len(selection["selected_question_ids"]),
        "excluded_question_groups": len(selection["excluded"]),
        "editions": editions,
        "status": "prepared_private_sample_not_publication_approved",
    }

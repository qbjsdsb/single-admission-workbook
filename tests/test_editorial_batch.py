import json

import pytest

from engine.pipeline.editorial_batch import (
    normalize_editorial_batch,
    prepare_editorial_batch,
)


def text(value):
    return [{"type": "text", "text": value}]


def choice_question(qid, stem, answer="A"):
    return {
        "id": qid,
        "subject": "english",
        "kind": "single_choice",
        "score": 2,
        "stem": text(stem),
        "options": [
            {"label": "A", "content": text("alpha")},
            {"label": "B", "content": text("beta")},
        ],
        "answer": answer,
        "analysis": text("Verified editorial analysis."),
        "difficulty": "basic",
    }


def batch_fixture():
    return {
        "schema_version": 1,
        "batch_id": "english-editorial-v01",
        "source_snapshot_id": "source-test",
        "subject": "english",
        "chapter": {"key": "grammar", "title": "语法专项"},
        "section": {"key": "verb", "title": "动词与时态"},
        "questions": [
            choice_question("EN_EDITORIAL_001", "Question one."),
            choice_question("EN_EDITORIAL_002", "Question two.", answer="B"),
        ],
        "occurrences": [
            {
                "id": "occ-1",
                "question_id": "EN_EDITORIAL_001",
                "source_id": "source-a",
                "locator": "page 1 / question 1",
                "status": "verified",
            },
            {
                "id": "occ-2",
                "question_id": "EN_EDITORIAL_002",
                "source_id": "source-a",
                "locator": "page 1 / question 2",
                "status": "verified",
            },
        ],
    }


def test_editorial_batch_renders_same_order_for_student_and_teacher(tmp_path):
    batch = batch_fixture()

    summary = prepare_editorial_batch(batch, tmp_path)

    assert summary["question_groups"] == 2
    assert summary["verified_occurrences"] == 2
    assert summary["status"] == "prepared_editorial_batch_visual_review_required"

    student = json.loads(
        (tmp_path / "english-editorial-v01-student" / "book.json").read_text(
            encoding="utf-8"
        )
    )
    teacher = json.loads(
        (tmp_path / "english-editorial-v01-teacher" / "book.json").read_text(
            encoding="utf-8"
        )
    )

    student_ids = student["chapters"][0]["sections"][0]["question_ids"]
    teacher_ids = teacher["chapters"][0]["sections"][0]["question_ids"]
    assert student_ids == ["EN_EDITORIAL_001", "EN_EDITORIAL_002"]
    assert teacher_ids == student_ids

    student_tex = (
        tmp_path / "english-editorial-v01-student" / "main.tex"
    ).read_text(encoding="utf-8")
    teacher_tex = (
        tmp_path / "english-editorial-v01-teacher" / "main.tex"
    ).read_text(encoding="utf-8")

    assert "\\teacheranswer{" not in student_tex
    assert "\\teacheranalysis{" not in student_tex
    assert "\\teacheranswer{" in teacher_tex
    assert "\\teacheranalysis{" in teacher_tex

    private_questions = json.loads(
        (
            tmp_path
            / "english-editorial-v01-student"
            / "questions.private.json"
        ).read_text(encoding="utf-8")
    )
    assert private_questions[0]["chapter_key"] == "grammar"
    assert private_questions[0]["section_key"] == "verb"


def test_editorial_batch_requires_verified_occurrence_for_every_question():
    batch = batch_fixture()
    batch["occurrences"] = batch["occurrences"][:1]

    with pytest.raises(ValueError, match="missing verified source occurrence"):
        normalize_editorial_batch(batch)


def test_editorial_batch_rejects_conflicting_assignment():
    batch = batch_fixture()
    batch["questions"][0]["chapter_key"] = "wrong"

    with pytest.raises(ValueError, match="conflicts with batch"):
        normalize_editorial_batch(batch)

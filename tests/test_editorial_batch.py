import json
from pathlib import Path
import tempfile
import unittest

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


class EditorialBatchTests(unittest.TestCase):
    def test_renders_same_order_for_student_and_teacher(self):
        batch = batch_fixture()

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            summary = prepare_editorial_batch(batch, out)

            self.assertEqual(summary["question_groups"], 2)
            self.assertEqual(summary["verified_occurrences"], 2)
            self.assertEqual(
                summary["status"],
                "prepared_editorial_batch_visual_review_required",
            )

            student = json.loads(
                (
                    out
                    / "english-editorial-v01-student"
                    / "book.json"
                ).read_text(encoding="utf-8")
            )
            teacher = json.loads(
                (
                    out
                    / "english-editorial-v01-teacher"
                    / "book.json"
                ).read_text(encoding="utf-8")
            )

            student_ids = student["chapters"][0]["sections"][0]["question_ids"]
            teacher_ids = teacher["chapters"][0]["sections"][0]["question_ids"]
            self.assertEqual(
                student_ids,
                ["EN_EDITORIAL_001", "EN_EDITORIAL_002"],
            )
            self.assertEqual(teacher_ids, student_ids)

            student_tex = (
                out
                / "english-editorial-v01-student"
                / "main.tex"
            ).read_text(encoding="utf-8")
            teacher_tex = (
                out
                / "english-editorial-v01-teacher"
                / "main.tex"
            ).read_text(encoding="utf-8")

            self.assertNotIn("\\teacheranswer{", student_tex)
            self.assertNotIn("\\teacheranalysis{", student_tex)
            self.assertIn("\\teacheranswer{", teacher_tex)
            self.assertIn("\\teacheranalysis{", teacher_tex)

            private_questions = json.loads(
                (
                    out
                    / "english-editorial-v01-student"
                    / "questions.private.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(private_questions[0]["chapter_key"], "grammar")
            self.assertEqual(private_questions[0]["section_key"], "verb")

    def test_requires_verified_occurrence_for_every_question(self):
        batch = batch_fixture()
        batch["occurrences"] = batch["occurrences"][:1]

        with self.assertRaisesRegex(
            ValueError,
            "missing verified source occurrence",
        ):
            normalize_editorial_batch(batch)

    def test_rejects_conflicting_assignment(self):
        batch = batch_fixture()
        batch["questions"][0]["chapter_key"] = "wrong"

        with self.assertRaisesRegex(ValueError, "conflicts with batch"):
            normalize_editorial_batch(batch)


if __name__ == "__main__":
    unittest.main()

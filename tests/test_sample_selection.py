import json
from pathlib import Path
import unittest

import jsonschema

from engine.pipeline.sample_selection import (
    build_sample_book_manifests,
    select_sample_questions,
)

ROOT = Path(__file__).resolve().parents[1]


def question(qid, stem="A fictional question.", *, analysis=True, section="verb"):
    q = {
        "id": qid,
        "subject": "english",
        "kind": "single_choice",
        "score": 2,
        "stem": [{"type": "text", "text": stem}],
        "options": [
            {"label": "A", "content": [{"type": "text", "text": "one"}]},
            {"label": "B", "content": [{"type": "text", "text": "two"}]},
            {"label": "C", "content": [{"type": "text", "text": "three"}]},
            {"label": "D", "content": [{"type": "text", "text": "four"}]},
        ],
        "answer": "B",
        "chapter_key": "grammar",
        "section_key": section,
        "difficulty": "standard",
        "layout": {"choice_mode": "auto", "keep_together": True},
    }
    if analysis:
        q["analysis"] = [{"type": "text", "text": "A reviewed fictional analysis."}]
    return q


def curriculum():
    return {
        "english": [
            {
                "key": "grammar",
                "title": "语法",
                "sections": [
                    {"key": "verb", "title": "动词"},
                    {"key": "noun", "title": "名词"},
                ],
            }
        ]
    }


class SampleSelectionTests(unittest.TestCase):
    def setUp(self):
        self.schema = json.loads(
            (ROOT / "schema/sample-selection.schema.json").read_text(encoding="utf-8")
        )

    def test_requires_teacher_analysis_by_default(self):
        draft = {
            "subject": "english",
            "questions": [
                question("ENG_A", analysis=True),
                question("ENG_B", analysis=False),
            ],
        }
        result = select_sample_questions(draft, curriculum())
        jsonschema.validate(result, self.schema)
        self.assertEqual(result["selected_question_ids"], ["ENG_A"])
        self.assertEqual(
            result["excluded"][0],
            {"question_id": "ENG_B", "reason": "missing_teacher_analysis"},
        )

    def test_reviewed_open_response_writing_does_not_need_fake_answer(self):
        writing = {
            "id": "ENG_WRITE",
            "subject": "english",
            "kind": "composition",
            "answer_mode": "open_response",
            "score": 10,
            "stem": [{"type": "text", "text": "Write a fictional letter."}],
            "analysis": [{"type": "text", "text": "A reviewed writing guide."}],
            "chapter_key": "grammar",
            "section_key": "verb",
            "difficulty": "standard",
        }
        draft = {"subject": "english", "questions": [writing]}
        result = select_sample_questions(draft, curriculum())
        jsonschema.validate(result, self.schema)
        self.assertEqual(result["selected_question_ids"], ["ENG_WRITE"])
        self.assertEqual(result["excluded"], [])

    def test_open_response_writing_still_requires_teacher_analysis(self):
        writing = {
            "id": "ENG_WRITE",
            "subject": "english",
            "kind": "composition",
            "answer_mode": "open_response",
            "score": 10,
            "stem": [{"type": "text", "text": "Write a fictional letter."}],
            "chapter_key": "grammar",
            "section_key": "verb",
            "difficulty": "standard",
        }
        result = select_sample_questions(
            {"subject": "english", "questions": [writing]},
            curriculum(),
        )
        self.assertEqual(result["selected_question_ids"], [])
        self.assertEqual(
            result["excluded"][0],
            {"question_id": "ENG_WRITE", "reason": "missing_teacher_analysis"},
        )

    def test_requested_unknown_id_is_explicitly_excluded(self):
        draft = {"subject": "english", "questions": [question("ENG_A")]}
        result = select_sample_questions(
            draft,
            curriculum(),
            requested_ids=["ENG_A", "ENG_MISSING"],
        )
        self.assertEqual(result["selected_question_ids"], ["ENG_A"])
        self.assertTrue(any(
            x["question_id"] == "ENG_MISSING" and x["reason"] == "requested_id_not_found"
            for x in result["excluded"]
        ))

    def test_invalid_curriculum_assignment_is_excluded(self):
        draft = {
            "subject": "english",
            "questions": [question("ENG_A", section="unknown")],
        }
        result = select_sample_questions(draft, curriculum())
        self.assertEqual(result["summary"]["selected"], 0)
        self.assertEqual(
            result["excluded"][0]["reason"], "invalid_curriculum_assignment"
        )

    def test_exact_duplicates_are_removed_from_sample(self):
        draft = {
            "subject": "english",
            "questions": [
                question("ENG_A", stem="Same fictional content."),
                question("ENG_B", stem="Same fictional content."),
            ],
        }
        result = select_sample_questions(draft, curriculum())
        self.assertEqual(result["summary"]["selected"], 0)
        duplicate_exclusions = [
            x for x in result["excluded"]
            if x["reason"] == "unresolved_exact_duplicate_in_sample"
        ]
        self.assertEqual(
            {x["question_id"] for x in duplicate_exclusions},
            {"ENG_A", "ENG_B"},
        )

    def test_student_and_teacher_manifests_share_same_question_set(self):
        draft = {
            "subject": "english",
            "questions": [
                question("ENG_B", stem="Second fictional question."),
                question("ENG_A", stem="First fictional question."),
            ],
        }
        selection = select_sample_questions(draft, curriculum())
        books = build_sample_book_manifests(selection, draft, curriculum())
        self.assertEqual(len(books), 2)
        self.assertEqual(
            {book["edition"] for book in books},
            {"student", "teacher"},
        )
        placements = []
        for book in books:
            ids = [
                qid
                for chapter in book["chapters"]
                for section in chapter["sections"]
                for qid in section["question_ids"]
            ]
            placements.append(ids)
            self.assertTrue(book["table_of_contents"])
            self.assertEqual(book["paper"], "A4")
        self.assertEqual(placements[0], placements[1])
        self.assertEqual(set(placements[0]), {"ENG_A", "ENG_B"})

    def test_empty_selection_cannot_build_books(self):
        draft = {"subject": "english", "questions": []}
        selection = select_sample_questions(draft, curriculum())
        with self.assertRaisesRegex(ValueError, "selection is empty"):
            build_sample_book_manifests(selection, draft, curriculum())


if __name__ == "__main__":
    unittest.main()

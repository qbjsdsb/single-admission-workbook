import json
from pathlib import Path
import tempfile
import unittest

from engine.pipeline.sample_render import prepare_private_sample
from engine.render.latex import escape_text, render_question


def cloze_group():
    return {
        "id": "ENG_FIXTURE_GROUP",
        "subject": "english",
        "kind": "cloze_group",
        "score": 4,
        "stem": [{"type": "text", "text": "A fictional passage for private-sample rendering."}],
        "answer": ["A", "B"],
        "children": [
            {
                "id": "ENG_FIXTURE_1",
                "kind": "single_choice",
                "score": 2,
                "stem": [{"type": "text", "text": "Choose the first answer."}],
                "options": [
                    {"label": "A", "content": [{"type": "text", "text": "one"}]},
                    {"label": "B", "content": [{"type": "text", "text": "two"}]},
                    {"label": "C", "content": [{"type": "text", "text": "three"}]},
                    {"label": "D", "content": [{"type": "text", "text": "four"}]},
                ],
                "answer": "A",
                "analysis": [{"type": "text", "text": "Reviewed fictional explanation one."}],
                "layout": {"choice_mode": "auto", "keep_together": True},
            },
            {
                "id": "ENG_FIXTURE_2",
                "kind": "single_choice",
                "score": 2,
                "stem": [{"type": "text", "text": "Choose the second answer."}],
                "options": [
                    {"label": "A", "content": [{"type": "text", "text": "one"}]},
                    {"label": "B", "content": [{"type": "text", "text": "two"}]},
                    {"label": "C", "content": [{"type": "text", "text": "three"}]},
                    {"label": "D", "content": [{"type": "text", "text": "four"}]},
                ],
                "answer": "B",
                "analysis": [{"type": "text", "text": "Reviewed fictional explanation two."}],
                "layout": {"choice_mode": "auto", "keep_together": True},
            },
        ],
        "chapter_key": "cloze",
        "section_key": "training",
        "difficulty": "standard",
    }


class RendererHardeningTests(unittest.TestCase):
    def test_legacy_spaces_symbols_and_long_underscore_runs_are_print_safe(self):
        rendered = escape_text(
            "April\u00a05 ▲ ★ \uf06c ʊ ɪ " + "_" * 240
        )
        self.assertNotIn("\u00a0", rendered)
        self.assertIn(r"$\blacktriangle$", rendered)
        self.assertIn(r"$\star$", rendered)
        self.assertIn(r"\textbullet{}", rendered)
        self.assertIn(r"{\wblatin ʊ}", rendered)
        self.assertIn(r"{\wblatin ɪ}", rendered)
        self.assertNotIn(r"\_" * 20, rendered)
        self.assertIn(r"\blank{45mm}", rendered)

    def test_student_open_response_gets_stable_writing_space(self):
        question = {
            "id": "ENG-WRITE",
            "subject": "english",
            "kind": "composition",
            "answer_mode": "open_response",
            "score": 10,
            "stem": [{"type": "text", "text": "Write a fictional letter. " + "_" * 300}],
            "analysis": [{"type": "text", "text": "A reviewed fictional writing guide."}],
        }
        student = render_question(question, 1, "student")
        teacher = render_question(question, 1, "teacher")
        self.assertIn(r"\answerlines{8}", student)
        self.assertNotIn(r"\answerlines{8}", teacher)
        self.assertIn(r"\blank{45mm}", student)


class PrivateSampleRenderTests(unittest.TestCase):
    def test_prepares_same_student_teacher_selection_and_no_student_answer_leak(self):
        draft = {
            "subject": "english",
            "questions": [cloze_group()],
        }
        curriculum = {
            "english": [{
                "key": "cloze",
                "title": "完形填空",
                "sections": [{"key": "training", "title": "专项训练"}],
            }]
        }

        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            summary = prepare_private_sample(draft, curriculum, out)
            self.assertEqual(summary["selected_question_groups"], 1)
            self.assertEqual({x["edition"] for x in summary["editions"]}, {"student", "teacher"})

            selection = json.loads((out / "selection.json").read_text(encoding="utf-8"))
            self.assertEqual(selection["selected_question_ids"], ["ENG_FIXTURE_GROUP"])

            student = out / "english-sample-student" / "main.tex"
            teacher = out / "english-sample-teacher" / "main.tex"
            student_tex = student.read_text(encoding="utf-8")
            teacher_tex = teacher.read_text(encoding="utf-8")

            self.assertEqual(student_tex.count("A fictional passage for private-sample rendering."), 1)
            self.assertNotIn("\\teacheranswer{", student_tex)
            self.assertNotIn("Reviewed fictional explanation one.", student_tex)
            self.assertIn("\\teacheranswer{A}", teacher_tex)
            self.assertIn("\\teacheranswer{B}", teacher_tex)
            self.assertIn("Reviewed fictional explanation one.", teacher_tex)
            self.assertIn("Reviewed fictional explanation two.", teacher_tex)

            for edition in ("student", "teacher"):
                folder = out / f"english-sample-{edition}"
                book = json.loads((folder / "book.json").read_text(encoding="utf-8"))
                ids = [
                    qid
                    for chapter in book["chapters"]
                    for section in chapter["sections"]
                    for qid in section["question_ids"]
                ]
                self.assertEqual(ids, ["ENG_FIXTURE_GROUP"])
                self.assertTrue((folder / "questions.private.json").exists())


if __name__ == "__main__":
    unittest.main()

import unittest

from engine.render.latex import render_question


def choice_question():
    return {
        "subject": "english",
        "kind": "single_choice",
        "score": 2,
        "stem": [{"type": "text", "text": "Choose the best fictional answer."}],
        "options": [
            {"label": "A", "content": [{"type": "text", "text": "one"}]},
            {"label": "B", "content": [{"type": "text", "text": "two"}]},
            {"label": "C", "content": [{"type": "text", "text": "three"}]},
            {"label": "D", "content": [{"type": "text", "text": "four"}]},
        ],
        "answer": "B",
        "analysis": [{"type": "text", "text": "Reviewed fictional analysis."}],
        "layout": {"choice_mode": "auto", "keep_together": True},
    }


class ChoicePageBreakTests(unittest.TestCase):
    def test_student_reserves_prompt_and_options_as_one_visual_block(self):
        tex = render_question(choice_question(), 7, "student")
        self.assertTrue(tex.startswith(r"\Needspace{6\baselineskip}"))
        self.assertLess(tex.index(r"\Needspace{6\baselineskip}"), tex.index(r"\q{7}{2}"))
        self.assertLess(tex.index(r"\q{7}{2}"), tex.index(r"\optfour{"))

    def test_teacher_reserves_answer_line_too(self):
        tex = render_question(choice_question(), 7, "teacher")
        self.assertTrue(tex.startswith(r"\Needspace{7\baselineskip}"))
        self.assertIn(r"\teacheranswer{B}", tex)


if __name__ == "__main__":
    unittest.main()

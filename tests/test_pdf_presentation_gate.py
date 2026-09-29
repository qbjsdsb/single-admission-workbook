import unittest

from scripts.check_pdf_navigation import (
    SCORE_RE,
    STUDENT_FOOTER_QUOTES,
    TEACHER_FOOTER_QUOTES,
)


class PdfPresentationGateTests(unittest.TestCase):
    def test_score_gate_accepts_full_width_textbook_parentheses(self):
        self.assertIsNotNone(SCORE_RE.search("1. （2 分） A fictional prompt"))
        self.assertIsNotNone(SCORE_RE.search("2.（2.5分）Another prompt"))
        self.assertIsNone(SCORE_RE.search("3. 2分 Missing parentheses"))

    def test_student_and_teacher_footer_pools_are_nonempty_and_distinct(self):
        self.assertGreaterEqual(len(STUDENT_FOOTER_QUOTES), 8)
        self.assertGreaterEqual(len(TEACHER_FOOTER_QUOTES), 8)
        self.assertFalse(set(STUDENT_FOOTER_QUOTES) & set(TEACHER_FOOTER_QUOTES))


if __name__ == "__main__":
    unittest.main()

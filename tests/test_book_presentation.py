import copy
import json
from pathlib import Path
import unittest

from engine.pipeline.books import plan_books
from engine.render.latex import format_score, render_book

ROOT = Path(__file__).resolve().parents[1]


class BookPresentationTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(
            (ROOT / "examples/eight-books/dataset.json").read_text(encoding="utf-8")
        )
        self.template = (ROOT / "templates/latex/workbook.tex").read_text(encoding="utf-8")

    def _english_books(self):
        books, bank = plan_books(
            self.data["questions"],
            self.data["ledger"],
            self.data["curriculum"],
        )
        english = [book for book in books if book["subject"] == "english"]
        return {book["edition"]: book for book in english}, bank

    def test_chapter_and_section_titles_are_rendered_in_body_and_toc(self):
        books, bank = self._english_books()
        tex = render_book(
            template=self.template,
            book=books["student"],
            questions=bank,
        )
        self.assertIn(r"\chapterhead{第1章}{词汇与语法}", tex)
        self.assertIn(r"\sectionhead{第1节}{动词时态}", tex)
        self.assertIn(r"\addcontentsline{toc}{section}{#1\quad #2}", tex)
        self.assertIn(r"\addcontentsline{toc}{subsection}{#1\quad #2}", tex)

    def test_student_and_teacher_have_distinct_visible_footer_quotes(self):
        books, bank = self._english_books()
        student = render_book(
            template=self.template,
            book=books["student"],
            questions=bank,
        )
        teacher = render_book(
            template=self.template,
            book=books["teacher"],
            questions=bank,
        )
        self.assertIn(r"\newcommand{\footerquote}{\studentfooterquote}", student)
        self.assertIn("把错题变成下一次的得分点", student)
        self.assertIn(r"\newcommand{\footerquote}{\teacherfooterquote}", teacher)
        self.assertIn("讲清一道题，比讲完十道题更重要", teacher)
        self.assertIn(r"\fancypagestyle{plain}", student)

    def test_question_score_is_always_wrapped_by_full_width_parentheses(self):
        books, bank = self._english_books()
        tex = render_book(
            template=self.template,
            book=books["student"],
            questions=bank,
        )
        self.assertIn("（#2分）", tex)
        self.assertIn(r"\q{1}{4}{", tex)
        self.assertEqual(format_score(3), "3")
        self.assertEqual(format_score(2.5), "2.5")

    def test_blank_chapter_title_blocks_build(self):
        data = copy.deepcopy(self.data)
        data["curriculum"]["english"][0]["title"] = "   "
        with self.assertRaisesRegex(ValueError, "missing visible title"):
            plan_books(data["questions"], data["ledger"], data["curriculum"])

    def test_blank_section_title_blocks_build(self):
        data = copy.deepcopy(self.data)
        data["curriculum"]["english"][0]["sections"][0]["title"] = ""
        with self.assertRaisesRegex(ValueError, "missing visible title"):
            plan_books(data["questions"], data["ledger"], data["curriculum"])


if __name__ == "__main__":
    unittest.main()

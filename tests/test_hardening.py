import copy
import json
from pathlib import Path
import unittest

from engine.ingest.pairing import pair_question_records
from engine.parse.docx_adapter import adapt_paragraph_block, UnsupportedRichContent
from engine.parse.options import parse_options
from engine.pipeline.books import plan_books
from engine.quality.build_fingerprint import combined_compile_id
from engine.quality.evidence import evaluate_answer_evidence

ROOT = Path(__file__).resolve().parents[1]


class HardeningTests(unittest.TestCase):
    def test_compile_cache_depends_on_environment(self):
        source = "abc123"
        self.assertNotEqual(
            combined_compile_id(source, "env-one"),
            combined_compile_id(source, "env-two"),
        )
        self.assertEqual(
            combined_compile_id(source, "env-one"),
            combined_compile_id(source, "env-one"),
        )

    def test_answer_conflict_blocks_strict_release(self):
        data = json.loads((ROOT / "examples/eight-books/dataset.json").read_text())
        data["ledger"]["answer_evidence"].append(
            {
                "question_id": "DEMO-1",
                "source_id": "S-CONFLICT",
                "value": "C",
                "status": "verified",
            }
        )
        with self.assertRaisesRegex(ValueError, "conflicting answer evidence"):
            plan_books(data["questions"], data["ledger"], data["curriculum"])

    def test_answer_cosmetic_punctuation_does_not_conflict(self):
        evidence = [
            {"question_id": "Q1", "source_id": "A", "value": "B", "status": "verified"},
            {"question_id": "Q1", "source_id": "B", "value": " B。 ", "status": "verified"},
        ]
        self.assertEqual(evaluate_answer_evidence("Q1", evidence).status, "agreed")

    def test_option_parser_common_forms(self):
        one_line = parse_options(["题干", "A. 甲 B. 乙 C. 丙 D. 丁"])
        self.assertEqual(one_line.status, "ok")
        self.assertEqual([x[0] for x in one_line.options], list("ABCD"))

        separate = parse_options(["题干", "A. 甲", "B. 乙", "C. 丙", "D. 丁"])
        self.assertEqual(separate.status, "ok")

    def test_option_parser_fails_closed_on_wrapped_option(self):
        result = parse_options(["题干", "A. 第一行", "没有选项标记的续行", "B. 乙"])
        self.assertEqual(result.status, "ambiguous_continuation")

    def test_pairing_survives_shifted_question_numbers(self):
        student = [
            {
                "id": "S1",
                "number": 12,
                "section_key": "single_choice",
                "stem": "某道虚构题干用于测试配对。",
                "options": ["甲", "乙", "丙", "丁"],
            }
        ]
        companion = [
            {
                "id": "T1",
                "number": 13,
                "section_key": "single_choice",
                "stem": "某道虚构题干用于测试配对。",
                "options": ["甲", "乙", "丙", "丁"],
            }
        ]
        result = pair_question_records(student, companion)
        self.assertEqual(result[0].companion_id, "T1")
        self.assertEqual(result[0].confidence, "exact")

    def test_pairing_marks_near_equal_candidates_ambiguous(self):
        student = [
            {
                "id": "S1",
                "number": 1,
                "section_key": "single_choice",
                "stem": "这是一道相同的虚构题干。",
                "options": ["甲", "乙", "丙", "丁"],
            }
        ]
        companion = [
            {
                "id": "T1",
                "number": 8,
                "section_key": "single_choice",
                "stem": "这是一道相同的虚构题干。",
                "options": ["甲", "乙", "丙", "丁"],
            },
            {
                "id": "T2",
                "number": 9,
                "section_key": "single_choice",
                "stem": "这是一道相同的虚构题干。",
                "options": ["甲", "乙", "丙", "丁"],
            },
        ]
        result = pair_question_records(student, companion)
        self.assertEqual(result[0].confidence, "ambiguous")
        self.assertIsNone(result[0].companion_id)

    def test_docx_adapter_preserves_emphasis_and_underline(self):
        block = {
            "locator": "word/document.xml/body/0",
            "kind": "p",
            "runs": [
                {"text": "春", "properties": {"em": "dot", "u": "single"}},
                {"text": "风", "properties": {}},
            ],
            "math_omml": [],
            "image_relationships": [],
        }
        adapted = adapt_paragraph_block(block)
        first = adapted.nodes[0]
        self.assertEqual(first["type"], "emphasis_dot")
        self.assertEqual(first["children"][0]["type"], "underline")
        self.assertEqual(first["children"][0]["children"][0]["text"], "春")

    def test_docx_adapter_blocks_unverified_math_conversion(self):
        block = {
            "locator": "word/document.xml/body/0",
            "kind": "p",
            "runs": [{"text": "x=", "properties": {}}],
            "math_omml": ["<m:oMath/>"],
            "image_relationships": [],
        }
        with self.assertRaisesRegex(UnsupportedRichContent, "OMML conversion not verified"):
            adapt_paragraph_block(block)


if __name__ == "__main__":
    unittest.main()

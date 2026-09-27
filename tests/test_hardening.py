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
from engine.quality.dedup import exact_duplicate_clusters, near_duplicate_candidates

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


    def test_exact_duplicate_questions_block_release(self):
        data = json.loads((ROOT / "examples/eight-books/dataset.json").read_text())
        duplicate = copy.deepcopy(data["questions"][0])
        duplicate["id"] = "DEMO-1-COPY"
        data["questions"].append(duplicate)
        data["ledger"]["sources"].append(
            {"id": "S-COPY", "status": "verified", "expected_questions": 1}
        )
        data["ledger"]["expected_source_ids"].append("S-COPY")
        data["ledger"]["occurrences"].append(
            {
                "id": "O-COPY",
                "source_id": "S-COPY",
                "question_id": "DEMO-1-COPY",
                "locator": "fictional duplicate fixture",
                "status": "verified",
            }
        )
        data["ledger"]["answer_evidence"].append(
            {
                "question_id": "DEMO-1-COPY",
                "source_id": "S-COPY",
                "value": "A",
                "status": "verified",
            }
        )
        with self.assertRaisesRegex(ValueError, "unresolved exact duplicate content"):
            plan_books(data["questions"], data["ledger"], data["curriculum"])

    def test_near_duplicates_are_advisory_not_auto_merged(self):
        left = {
            "id": "Q-A",
            "subject": "chinese",
            "kind": "single_choice",
            "stem": [{"type": "text", "text": "下面这道虚构题用于检测近似题。"}],
            "options": [
                {"label": "A", "content": [{"type": "text", "text": "甲"}]},
                {"label": "B", "content": [{"type": "text", "text": "乙"}]}
            ]
        }
        right = copy.deepcopy(left)
        right["id"] = "Q-B"
        right["stem"][0]["text"] = "下面这道虚构题用于检测近似题！"
        self.assertEqual(exact_duplicate_clusters([left, right]), [])
        near = near_duplicate_candidates([left, right], threshold=0.90)
        self.assertEqual(len(near), 1)
        self.assertEqual({near[0].left_id, near[0].right_id}, {"Q-A", "Q-B"})

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

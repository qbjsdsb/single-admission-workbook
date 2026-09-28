import json
from pathlib import Path
import unittest

import jsonschema

from engine.document.docx_table import normalize_table_block
from engine.parse.candidate_bank import extract_candidate_bank
from engine.parse.options import parse_options
from engine.pipeline.scoring import (
    auto_apply_first_volume_residual_resolution,
    build_score_evidence,
)

ROOT = Path(__file__).resolve().parents[1]


def paragraph(index, text):
    return {
        "type": "paragraph",
        "locator": f"word/document.xml/body/{index}",
        "inlines": [{"type": "text", "text": text}],
    }


class EnglishRealRegressionTests(unittest.TestCase):
    def test_legacy_l_as_one_recovers_teen_question_number_with_provenance(self):
        texts = [
            "1. A fictional prompt A. one B. two C. three D. four",
            "2. A fictional prompt A. one B. two C. three D. four",
            "3. A fictional prompt A. one B. two C. three D. four",
            "4. A fictional prompt A. one B. two C. three D. four",
            "5. A fictional prompt A. one B. two C. three D. four",
            "6. A fictional prompt A. one B. two C. three D. four",
            "7. A fictional prompt A. one B. two C. three D. four",
            "8. A fictional prompt A. one B. two C. three D. four",
            "9. A fictional prompt A. one B. two C. three D. four",
            "10. A fictional prompt A. one B. two C. three D. four",
            "11. A fictional prompt A. one B. two C. three D. four",
            "12. A fictional prompt A. one B. two C. three D. four",
            "13. A fictional prompt A. one B. two C. three D. four",
            "14. A fictional prompt A. one B. two C. three D. four",
            "15. A fictional prompt A. one B. two C. three D. four",
            "16. A fictional prompt A. one B. two C. three D. four",
            "17. A fictional prompt A. one B. two C. three D. four",
            "l8. A fictional prompt A. one B. two C. three D. four",
            "19. A fictional prompt A. one B. two C. three D. four",
            "20. A fictional prompt A. one B. two C. three D. four",
            "II.完形填空（共1小题，每小题2分，满分2分）",
            "A fictional shared passage.",
            "21. A. one B. two C. three D. four",
        ]
        document = {
            "version": 1,
            "source_format": "docx",
            "blocks": [paragraph(i, text) for i, text in enumerate(texts)],
            "warnings": [],
        }
        bank = extract_candidate_bank(
            document,
            subject="english",
            source_id="ENG-LEGACY-L8",
        )
        choices = [
            item
            for item in bank["candidates"]
            if item["section_key"] == "single_choice"
        ]
        self.assertEqual(
            [item["source_number"] for item in choices],
            list(range(1, 21)),
        )
        self.assertTrue(all(item["status"] == "parsed" for item in choices))
        q18 = next(item for item in choices if item["source_number"] == 18)
        self.assertIn(
            "source_number_glyph_recovered_l_as_1",
            q18["review_reasons"],
        )
        self.assertTrue(all(
            "section_heading_missing_sequence_bound_1_to_20_before_cloze"
            in item["review_reasons"]
            for item in choices
        ))

    def test_duplicate_b_in_abbd_is_recovered_but_audited(self):
        result = parse_options([
            "A. first choice B. second choice B. third choice D. fourth choice"
        ])
        self.assertEqual(result.status, "ok")
        self.assertEqual(
            result.options,
            (
                ("A", "first choice"),
                ("B", "second choice"),
                ("C", "third choice"),
                ("D", "fourth choice"),
            ),
        )
        self.assertEqual(
            result.recoveries,
            ("duplicate_b_in_abbd_relabelled_c",),
        )

    def test_inline_table_date_punctuation_drawing_is_recovered_only_in_context(self):
        xml = """<w:tbl xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:tr><w:tc><w:p>
            <w:r><w:t>April 5</w:t></w:r>
            <w:r><w:drawing/></w:r>
            <w:r><w:t xml:space="preserve"> 2025</w:t></w:r>
          </w:p></w:tc></w:tr>
        </w:tbl>"""
        table = normalize_table_block({
            "type": "table",
            "locator": "word/document.xml/body/4",
            "rows": [],
            "unsupported_features": ["drawing"],
            "raw_xml": xml,
        })
        self.assertEqual(table["rows"][0]["cells"][0]["text"], "April 5, 2025")
        self.assertEqual(table["unsupported_features"], [])

    def test_unrecognized_inline_table_drawing_remains_blocked(self):
        xml = """<w:tbl xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:tr><w:tc><w:p>
            <w:r><w:t>See </w:t></w:r>
            <w:r><w:drawing/></w:r>
            <w:r><w:t> diagram</w:t></w:r>
          </w:p></w:tc></w:tr>
        </w:tbl>"""
        table = normalize_table_block({
            "type": "table",
            "locator": "word/document.xml/body/4",
            "rows": [],
            "unsupported_features": ["drawing"],
            "raw_xml": xml,
        })
        self.assertIn("drawing", table["unsupported_features"])

    def test_explicit_first_volume_total_can_fill_one_inferred_score_gap(self):
        bank = {
            "source_id": "SRC",
            "subject": "english",
            "sections": [
                {
                    "section_key": "single_choice",
                    "heading": "[inferred]",
                    "heading_locator": "src/q1",
                    "candidate_count": 20,
                    "inferred": True,
                },
                {
                    "section_key": "cloze",
                    "heading": "II.完形填空（共10小题，每小题2分，满分20分）",
                    "heading_locator": "src/cloze",
                    "candidate_count": 10,
                    "inferred": False,
                },
                {
                    "section_key": "reading",
                    "heading": "III.阅读理解（共15小题，每小题4分，满分60分）",
                    "heading_locator": "src/reading",
                    "candidate_count": 15,
                    "inferred": False,
                },
            ],
        }
        source_text = {
            "src/q1": "[inferred]",
            "src/cloze": bank["sections"][1]["heading"],
            "src/reading": bank["sections"][2]["heading"],
            "src/volume": "第一卷（三大题，共120分）",
        }
        score = build_score_evidence(bank)
        resolved = auto_apply_first_volume_residual_resolution(
            bank,
            score,
            source_text_by_locator=source_text,
        )
        schema = json.loads(
            (ROOT / "schema/score-evidence.schema.json").read_text(encoding="utf-8")
        )
        jsonschema.validate(resolved, schema)
        target = next(
            item
            for item in resolved["sections"]
            if item["section_key"] == "single_choice"
        )
        self.assertEqual(target["status"], "usable")
        self.assertEqual(target["full_score"], 40.0)
        self.assertEqual(target["per_question_score"], 2.0)
        self.assertEqual(
            target["residual_resolution"]["method"],
            "automatic_explicit_volume_total_residual",
        )
        self.assertEqual(
            target["residual_resolution"]["rule_version"],
            "first_volume_residual_v1",
        )
        self.assertNotIn("reviewer", target["residual_resolution"])


if __name__ == "__main__":
    unittest.main()

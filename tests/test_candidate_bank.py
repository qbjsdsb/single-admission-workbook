import json
from pathlib import Path
import unittest

import jsonschema

from engine.parse.candidate_bank import extract_candidate_bank

ROOT = Path(__file__).resolve().parents[1]


def paragraph(index, text, extra_inline=None):
    inlines = [{"type": "text", "text": text}]
    if extra_inline:
        inlines.append(extra_inline)
    return {
        "type": "paragraph",
        "locator": f"word/document.xml/body/{index}",
        "inlines": inlines,
    }


class CandidateBankTests(unittest.TestCase):
    def setUp(self):
        self.schema = json.loads(
            (ROOT / "schema/candidate-bank.schema.json").read_text(encoding="utf-8")
        )

    def test_english_section_first_grouped_fast_lane(self):
        texts = [
            "1. This is an instruction and must not become a question.",
            "I.单项选择",
            "1. A fictional stem A. One B. Two C. Three D. Four",
            "2. Another fictional stem.",
            "A. Alpha B. Beta C. Gamma D. Delta",
            "II.完形填空",
            "A fictional cloze passage with shared material.",
            "21. A. red B. blue C. green D. black",
            "22. A. east B. west C. north D. south",
            "III.阅读理解",
            "A",
            "A fictional reading passage A.",
            "31. What is passage A about? A. One B. Two C. Three D. Four",
            "B",
            "A fictional reading passage B.",
            "32. What is passage B about? A. Five B. Six C. Seven D. Eight",
            "V.书面表达",
            "Write a fictional email of about 100 words."
        ]
        document = {
            "version": 1,
            "source_format": "docx",
            "blocks": [paragraph(i, text) for i, text in enumerate(texts)],
            "warnings": [],
        }
        bank = extract_candidate_bank(document, subject="english", source_id="ENG-FIX")
        jsonschema.validate(bank, self.schema)

        self.assertEqual(bank["summary"]["candidate_count"], 7)
        self.assertEqual(bank["summary"]["group_count"], 3)
        self.assertNotIn(
            1,
            [
                q["source_number"]
                for q in bank["candidates"]
                if q["section_key"] not in {"single_choice"}
            ],
        )

        q1 = next(q for q in bank["candidates"] if q["candidate_id"] == "ENG-FIX:q:1")
        self.assertEqual(q1["stem_text"], "A fictional stem")
        self.assertEqual([o["label"] for o in q1["options"]], list("ABCD"))
        self.assertEqual(q1["status"], "parsed")

        cloze = next(g for g in bank["groups"] if g["kind"] == "cloze_group")
        self.assertIn("shared material", cloze["shared_material_text"])
        self.assertEqual(len(cloze["child_candidate_ids"]), 2)

        reading = [g for g in bank["groups"] if g["kind"] == "reading_group"]
        self.assertEqual([g["label"] for g in reading], ["A", "B"])
        self.assertEqual([len(g["child_candidate_ids"]) for g in reading], [1, 1])

        writing = next(q for q in bank["candidates"] if q["kind"] == "composition")
        self.assertIsNone(writing["source_number"])
        self.assertIn("fictional email", writing["stem_text"])

    def test_politics_simple_sections_and_locators(self):
        texts = [
            "一、单项选择题",
            "1. 虚构题干。",
            "A. 甲",
            "B. 乙",
            "C. 丙",
            "D. 丁",
            "二、填空题",
            "26. 虚构填空：______。",
            "三、材料题",
            "31. 阅读虚构材料并回答。",
            "材料：这是虚构材料。",
            "问题：写出两点。"
        ]
        document = {
            "version": 1,
            "source_format": "docx",
            "blocks": [paragraph(i, text) for i, text in enumerate(texts)],
            "warnings": [],
        }
        bank = extract_candidate_bank(document, subject="politics", source_id="POL-FIX")
        jsonschema.validate(bank, self.schema)

        self.assertEqual(bank["summary"]["candidate_count"], 3)
        choice = next(q for q in bank["candidates"] if q["source_number"] == 1)
        self.assertEqual(choice["status"], "parsed")
        self.assertEqual(len(choice["options"]), 4)
        self.assertTrue(all(locator.startswith("word/document.xml/body/") for locator in choice["locators"]))

        material = next(q for q in bank["candidates"] if q["source_number"] == 31)
        self.assertIn("这是虚构材料", material["stem_text"])
        self.assertEqual(material["kind"], "material_question")

    def test_rich_content_becomes_explicit_blocker_not_plain_text(self):
        document = {
            "version": 1,
            "source_format": "docx",
            "blocks": [
                paragraph(0, "一、单项选择题"),
                paragraph(
                    1,
                    "1. 带图的虚构题。",
                    {
                        "type": "image_ref",
                        "relationship_id": "rId1",
                        "locator": "word/document.xml/body/1/drawing/0",
                        "status": "captured_not_normalized",
                        "source": "drawingml",
                    },
                ),
                paragraph(2, "A. 甲 B. 乙 C. 丙 D. 丁"),
            ],
            "warnings": ["image_relationship_not_normalized"],
        }
        bank = extract_candidate_bank(document, subject="politics", source_id="POL-RICH")
        self.assertEqual(bank["summary"]["blocker_count"], 1)
        self.assertIn("unsupported_inline:image_ref", bank["blockers"][0]["reasons"])
        # The rich paragraph is not silently flattened into a publishable stem.
        self.assertEqual(bank["summary"]["candidate_count"], 0)

    def test_ambiguous_options_are_reviewable_not_guessed(self):
        texts = [
            "一、单项选择题",
            "1. 虚构题干。",
            "A. 很长选项第一行",
            "没有选项标记的续行",
            "B. 乙",
            "C. 丙",
            "D. 丁"
        ]
        document = {
            "version": 1,
            "source_format": "docx",
            "blocks": [paragraph(i, text) for i, text in enumerate(texts)],
            "warnings": [],
        }
        bank = extract_candidate_bank(document, subject="politics", source_id="POL-AMB")
        q = bank["candidates"][0]
        self.assertEqual(q["status"], "needs_review")
        self.assertIn("option_parse_ambiguous_continuation", q["review_reasons"])


if __name__ == "__main__":
    unittest.main()

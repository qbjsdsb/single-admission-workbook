import json
from pathlib import Path
import unittest

import jsonschema

from engine.parse.evidence_bank import extract_evidence_bank

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


class EvidenceBankTests(unittest.TestCase):
    def setUp(self):
        self.schema = json.loads(
            (ROOT / "schema/evidence-bank.schema.json").read_text(encoding="utf-8")
        )

    def test_english_prompt_answer_analysis_records(self):
        texts = [
            "I. 单项选择（共2小题）",
            "1. How much is the fictional desk?",
            "A. costsB. paysC. spendsD. takes",
            "答案：Ａ",
            "解析：A fictional explanation for question one.",
            "2. A second fictional prompt.",
            "A. one B. two C. three D. four",
            "答案：D",
            "解析：A fictional explanation for question two."
        ]
        document = {
            "version": 1,
            "source_format": "docx",
            "blocks": [paragraph(i, text) for i, text in enumerate(texts)],
            "warnings": [],
        }
        bank = extract_evidence_bank(
            document, subject="english", source_id="ENG-TEACHER"
        )
        jsonschema.validate(bank, self.schema)

        self.assertEqual(bank["summary"]["question_record_count"], 2)
        self.assertEqual(len(bank["evidence"]), 4)
        q1 = next(q for q in bank["question_records"] if q["number"] == 1)
        self.assertEqual(q1["stem"], "How much is the fictional desk?")
        self.assertEqual([o["text"] for o in q1["options"]],
                         ["costs", "pays", "spends", "takes"])

        answer = next(
            e for e in bank["evidence"]
            if e["source_number"] == 1 and e["field"] == "answer"
        )
        self.assertEqual(answer["value"], "A")
        analysis = next(
            e for e in bank["evidence"]
            if e["source_number"] == 1 and e["field"] == "analysis"
        )
        self.assertIn("fictional explanation", analysis["value"])

    def test_bracketed_teacher_format_and_grouped_answer_details(self):
        texts = [
            "Ⅰ. 单项选择",
            "1. A fictional prompt.",
            "A. createB. avoidC. inviteD. cancel",
            "【答案】A",
            "【解析】",
            "【详解】A fictional detailed explanation.",
            "II. 完形填空",
            "A fictional shared passage.",
            "21. A. oneB. twoC. threeD. four",
            "22. A. redB. blueC. greenD. black",
            "【答案】21. B    22. D",
            "【解析】",
            "【21题详解】",
            "A fictional explanation for item 21.",
            "【22题详解】A fictional explanation for item 22."
        ]
        document = {
            "version": 1,
            "source_format": "docx",
            "blocks": [paragraph(i, text) for i, text in enumerate(texts)],
            "warnings": [],
        }
        bank = extract_evidence_bank(
            document, subject="english", source_id="ENG-BRACKET"
        )
        jsonschema.validate(bank, self.schema)

        self.assertTrue(any(
            e["source_number"] == 1 and e["field"] == "answer" and e["value"] == "A"
            for e in bank["evidence"]
        ))
        self.assertTrue(any(
            e["source_number"] == 1 and e["field"] == "analysis"
            and "detailed explanation" in e["value"]
            for e in bank["evidence"]
        ))
        grouped_answers = {
            (e["source_number"], e["value"])
            for e in bank["evidence"]
            if e["field"] == "answer" and e["source_number"] in {21, 22}
        }
        self.assertEqual(grouped_answers, {(21, "B"), (22, "D")})
        self.assertTrue(any(
            e["source_number"] == 21 and e["field"] == "analysis"
            and "item 21" in e["value"]
            for e in bank["evidence"]
        ))
        self.assertTrue(any(
            e["source_number"] == 22 and e["field"] == "analysis"
            and "item 22" in e["value"]
            for e in bank["evidence"]
        ))

    def test_politics_summary_detailed_fill_and_long_answers(self):
        texts = [
            "一、单选题",
            "答案汇总",
            "1.A 2.B 3.C",
            "1. 答案：A",
            "题干核心：虚构核心。",
            "解析：虚构解析。",
            "2. 答案B",
            "解析：第二个虚构解析。",
            "二、填空题",
            "26.张家口 27.两极 28.杨洪",
            "三、问答题",
            "31.第一点；第二点。",
            "32.这是第二个长答案。"
        ]
        document = {
            "version": 1,
            "source_format": "docx",
            "blocks": [paragraph(i, text) for i, text in enumerate(texts)],
            "warnings": [],
        }
        bank = extract_evidence_bank(
            document, subject="politics", source_id="POL-ANSWER"
        )
        jsonschema.validate(bank, self.schema)

        # Answer-only politics rows must not manufacture prompt identity.
        self.assertEqual(bank["summary"]["question_record_count"], 0)

        q1_answers = [
            e for e in bank["evidence"]
            if e["source_number"] == 1 and e["field"] == "answer"
        ]
        self.assertEqual({e["value"] for e in q1_answers}, {"A"})
        self.assertEqual(
            {e["extraction_mode"] for e in q1_answers},
            {"compact_summary", "explicit_numbered"},
        )

        self.assertTrue(any(
            e["source_number"] == 26 and e["value"] == "张家口"
            for e in bank["evidence"]
        ))
        self.assertTrue(any(
            e["source_number"] == 31
            and e["field"] == "answer"
            and "第一点" in e["value"]
            for e in bank["evidence"]
        ))
        self.assertTrue(any(
            e["source_number"] == 1
            and e["field"] == "teacher_notes"
            and "虚构核心" in e["value"]
            for e in bank["evidence"]
        ))

    def test_conflicting_source_values_are_preserved_not_overwritten(self):
        texts = [
            "一、单选题",
            "答案汇总",
            "1.A 2.B",
            "1. 答案：C"
        ]
        document = {
            "version": 1,
            "source_format": "docx",
            "blocks": [paragraph(i, text) for i, text in enumerate(texts)],
            "warnings": [],
        }
        bank = extract_evidence_bank(
            document, subject="politics", source_id="POL-CONFLICT"
        )
        answers = {
            e["value"]
            for e in bank["evidence"]
            if e["source_number"] == 1 and e["field"] == "answer"
        }
        self.assertEqual(answers, {"A", "C"})

    def test_rich_nodes_are_reported_as_blockers_but_text_evidence_survives(self):
        document = {
            "version": 1,
            "source_format": "docx",
            "blocks": [
                paragraph(0, "I. 单项选择"),
                paragraph(
                    1,
                    "1. A fictional prompt.",
                    {
                        "type": "image_ref",
                        "relationship_id": "rId1",
                        "locator": "word/document.xml/body/1/drawing/0",
                        "status": "captured_not_normalized",
                        "source": "drawingml",
                    },
                ),
                paragraph(2, "A. one B. two C. three D. four"),
                paragraph(3, "答案：B"),
                paragraph(4, "解析：虚构解析。")
            ],
            "warnings": ["image_relationship_not_normalized"],
        }
        bank = extract_evidence_bank(
            document, subject="english", source_id="ENG-RICH"
        )
        self.assertEqual(bank["summary"]["blocker_count"], 1)
        self.assertEqual(bank["summary"]["question_record_count"], 1)
        self.assertTrue(any(
            "unsupported_inline:image_ref" in reason
            for reason in bank["blockers"][0]["reasons"]
        ))
        self.assertTrue(any(
            e["source_number"] == 1 and e["field"] == "answer" and e["value"] == "B"
            for e in bank["evidence"]
        ))


if __name__ == "__main__":
    unittest.main()

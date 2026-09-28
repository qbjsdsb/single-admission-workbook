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

    def test_real_english_range_summary_and_topic_analysis_format(self):
        texts = [
            "I. 单项选择",
            "1. A fictional prompt.",
            "A. one B. two C. three D. four",
            "答案：D",
            "考点与解析：A fictional topic-based explanation.",
            "VII. 完形填空",
            "21-25 DACDB        26-30 BCBDA",
            "VIII. 阅读理解",
            "31-34 CABD        35-38 BCBA",
            "39-42 CBDA        43-45 ADD",
            "IX. 单词拼写",
            "46. village        47. sharp",
            "48. season         49. answer",
        ]
        document = {
            "version": 1,
            "source_format": "docx",
            "blocks": [paragraph(i, text) for i, text in enumerate(texts)],
            "warnings": [],
        }
        bank = extract_evidence_bank(
            document, subject="english", source_id="ENG-RANGE"
        )
        jsonschema.validate(bank, self.schema)

        answers = {
            (e["source_number"], e["value"])
            for e in bank["evidence"]
            if e["field"] == "answer"
        }
        self.assertIn((1, "D"), answers)
        self.assertIn((21, "D"), answers)
        self.assertIn((25, "B"), answers)
        self.assertIn((26, "B"), answers)
        self.assertIn((30, "A"), answers)
        self.assertIn((31, "C"), answers)
        self.assertIn((45, "D"), answers)
        self.assertIn((46, "village"), answers)
        self.assertIn((49, "answer"), answers)

        analysis = next(
            e for e in bank["evidence"]
            if e["source_number"] == 1 and e["field"] == "analysis"
        )
        self.assertIn("topic-based explanation", analysis["value"])

    def test_answer_range_after_answer_label_maps_each_child_question(self):
        texts = [
            "I. 单项选择",
            "20. A fictional final question.",
            "A. one B. two C. three D. four",
            "答案：B",
            "II. 完形填空",
            "答案：21-25 BACCD 26-30 BDABD",
        ]
        document = {
            "version": 1,
            "source_format": "docx",
            "blocks": [paragraph(i, text) for i, text in enumerate(texts)],
            "warnings": [],
        }
        bank = extract_evidence_bank(
            document, subject="english", source_id="ENG-RANGE-LABEL"
        )
        answers = [e for e in bank["evidence"] if e["field"] == "answer"]
        q20 = [e["value"] for e in answers if e["source_number"] == 20]
        self.assertEqual(q20, ["B"])
        answer_pairs = {(e["source_number"], e["value"]) for e in answers}
        self.assertIn((21, "B"), answer_pairs)
        self.assertIn((30, "D"), answer_pairs)

    def test_question_with_price_is_not_treated_as_compact_answer_list(self):
        texts = [
            "I. 单项选择",
            "14. A fictional prompt.",
            "A. one B. two C. three D. four",
            "答案：C",
            "15. The green watch costs $199 and the red watch costs $195.",
            "A. opinion B. change C. decision D. difference",
            "答案：D",
        ]
        document = {
            "version": 1,
            "source_format": "docx",
            "blocks": [paragraph(i, text) for i, text in enumerate(texts)],
            "warnings": [],
        }
        bank = extract_evidence_bank(
            document, subject="english", source_id="ENG-PRICE-PROMPT"
        )
        answers = {
            e["source_number"]: e["value"]
            for e in bank["evidence"]
            if e["field"] == "answer"
        }
        self.assertEqual(answers[14], "C")
        self.assertEqual(answers[15], "D")
        self.assertNotIn(195, answers)

    def test_missing_english_first_heading_is_inferred_for_evidence(self):
        texts = [
            "考试说明",
            "1. 注意事项一。",
            "2. 注意事项二。",
            "1. Fictional prompt one.",
            "A. one B. two C. three D. four",
            "【答案】A",
            "【解析】",
            "【详解】Fictional explanation one.",
            "2. Fictional prompt two.",
            "A. one B. two C. three D. four",
            "【答案】B",
            "【解析】",
            "【详解】Fictional explanation two.",
            "3. Fictional prompt three.",
            "A. one B. two C. three D. four",
            "【答案】C",
            "4. Fictional prompt four.",
            "A. one B. two C. three D. four",
            "【答案】D",
            "5. Fictional prompt five.",
            "A. one B. two C. three D. four",
            "【答案】A",
            "II.完形填空",
            "21-25 ABCDA"
        ]
        document = {
            "version": 1,
            "source_format": "docx",
            "blocks": [paragraph(i, text) for i, text in enumerate(texts)],
            "warnings": [],
        }
        bank = extract_evidence_bank(
            document, subject="english", source_id="ENG-MISSING-HEAD"
        )
        jsonschema.validate(bank, self.schema)
        q1 = [
            e for e in bank["evidence"]
            if e["source_number"] == 1 and e["field"] == "answer"
        ]
        self.assertEqual({e["value"] for e in q1}, {"A"})
        self.assertTrue(all(e["section_key"] == "single_choice" for e in q1))
        self.assertTrue(any(
            e["source_number"] == 2
            and e["field"] == "analysis"
            and e["section_key"] == "single_choice"
            for e in bank["evidence"]
        ))

    def test_missing_open_bracket_in_numbered_detail_heading_is_recovered(self):
        texts = [
            "II. 完形填空",
            "21. A fictional question.",
            "A. one B. two C. three D. four",
            "【答案】A",
            "【解析】",
            "21题详解】",
            "A reviewed fictional detailed explanation.",
        ]
        document = {
            "version": 1,
            "source_format": "docx",
            "blocks": [paragraph(i, text) for i, text in enumerate(texts)],
            "warnings": [],
        }
        bank = extract_evidence_bank(
            document, subject="english", source_id="ENG-MALFORMED-DETAIL"
        )
        jsonschema.validate(bank, self.schema)
        analyses = [
            e for e in bank["evidence"]
            if e["source_number"] == 21 and e["field"] == "analysis"
        ]
        self.assertEqual(len(analyses), 1)
        self.assertEqual(
            analyses[0]["value"],
            "A reviewed fictional detailed explanation.",
        )

    def test_bare_numbered_detail_without_closing_bracket_is_not_guessed(self):
        texts = [
            "II. 完形填空",
            "21. A fictional question.",
            "A. one B. two C. three D. four",
            "【答案】A",
            "21题详解",
            "Untrusted free text.",
        ]
        document = {
            "version": 1,
            "source_format": "docx",
            "blocks": [paragraph(i, text) for i, text in enumerate(texts)],
            "warnings": [],
        }
        bank = extract_evidence_bank(
            document, subject="english", source_id="ENG-UNSAFE-DETAIL"
        )
        self.assertFalse(any(
            e["source_number"] == 21 and e["field"] == "analysis"
            for e in bank["evidence"]
        ))

    def test_decimal_in_question_text_is_not_compact_answer_summary(self):
        texts = [
            "I. 单项选择",
            "3. A fictional question.",
            "A. one B. two C. three D. four",
            "【答案】B",
            "4. A fictional population will reach 1.7 billion in a few years.",
            "A. while B. since C. when D. although",
            "【答案】A",
        ]
        document = {
            "version": 1,
            "source_format": "docx",
            "blocks": [paragraph(i, text) for i, text in enumerate(texts)],
            "warnings": [],
        }
        bank = extract_evidence_bank(
            document, subject="english", source_id="ENG-DECIMAL"
        )
        answers = {
            e["source_number"]: e["value"]
            for e in bank["evidence"]
            if e["field"] == "answer"
        }
        self.assertEqual(answers[3], "B")
        self.assertEqual(answers[4], "A")
        self.assertNotIn(1, answers)

    def test_rich_nodes_are_reported_as_blockers_but_text_evidence_survives(self):
        rich_paragraph = paragraph(
            1,
            "1. A fictional prompt.",
            {
                "type": "image_ref",
                "relationship_id": "rId1",
                "locator": "word/document.xml/body/1/drawing/0",
                "status": "captured_not_normalized",
                "source": "drawingml",
            },
        )
        rich_paragraph["inlines"].append({
            "type": "image_ref",
            "relationship_id": "rId2",
            "locator": "word/document.xml/body/1/drawing/1",
            "status": "captured_not_normalized",
            "source": "drawingml",
        })
        document = {
            "version": 1,
            "source_format": "docx",
            "blocks": [
                paragraph(0, "I. 单项选择"),
                rich_paragraph,
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
        self.assertEqual(bank["blockers"][0]["reasons"], ["unsupported_inline:image_ref"])
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

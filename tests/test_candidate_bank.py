import json
from pathlib import Path
import unittest

import jsonschema

from engine.parse.candidate_bank import extract_candidate_bank
from engine.parse.exam_split import detect_section
from engine.pipeline.scoring import build_score_evidence

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

        q1 = next(
            q for q in bank["candidates"]
            if q["source_number"] == 1 and q["section_key"] == "single_choice"
        )
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

    def test_table_in_group_material_is_retained_as_structured_rich_content(self):
        table = {
            "type": "table",
            "locator": "word/document.xml/body/3",
            "rows": [{"cells": [
                {"paragraphs": ["Time"], "text": "Time", "grid_span": 1, "vertical_merge": None},
                {"paragraphs": ["Activity"], "text": "Activity", "grid_span": 1, "vertical_merge": None},
            ]}, {"cells": [
                {"paragraphs": ["Saturday"], "text": "Saturday", "grid_span": 1, "vertical_merge": None},
                {"paragraphs": ["Read"], "text": "Read", "grid_span": 1, "vertical_merge": None},
            ]}],
            "unsupported_features": [],
            "raw_xml": "<w:tbl/>",
        }
        document = {
            "version": 1,
            "source_format": "docx",
            "blocks": [
                paragraph(0, "III.阅读理解"), paragraph(1, "A"),
                paragraph(2, "A fictional passage."), table,
                paragraph(4, "31. Which activity is listed? A. Read B. Run C. Swim D. Dance"),
            ],
            "warnings": [],
        }
        bank = extract_candidate_bank(document, subject="english", source_id="ENG-TABLE")
        jsonschema.validate(bank, self.schema)
        group = bank["groups"][0]
        self.assertIn("Saturday | Read", group["shared_material_text"])
        self.assertEqual(group["shared_material_rich"][0]["type"], "text")
        table_node = next(x for x in group["shared_material_rich"] if x["type"] == "table")
        self.assertEqual(table_node["rows"][1]["cells"][0]["text"], "Saturday")

    def test_glued_english_options_and_arabic_section_heading(self):
        texts = [
            "1. 单项选择（共1小题）",
            "1. —How much is the desk?",
            "A. costsB. paysC. spendsD. takes",
            "II.完形填空（共1小题）",
            "Shared fictional passage.",
            "21. A. oneB. twoC. threeD. four"
        ]
        document = {
            "version": 1,
            "source_format": "docx",
            "blocks": [paragraph(i, text) for i, text in enumerate(texts)],
            "warnings": [],
        }
        bank = extract_candidate_bank(document, subject="english", source_id="ENG-GLUED")
        q1 = next(q for q in bank["candidates"] if q["source_number"] == 1)
        self.assertEqual(q1["status"], "parsed")
        self.assertEqual([o["text"] for o in q1["options"]], ["costs", "pays", "spends", "takes"])
        self.assertEqual(bank["sections"][0]["section_key"], "single_choice")
        self.assertFalse(bank["sections"][0]["inferred"])

    def test_cloze_instruction_without_heading_starts_grouped_section(self):
        texts = [
            "I. 单项选择（共1小题）",
            "1. A fictional single-choice prompt.",
            "A. one B. two C. three D. four",
            "II. 阅读下面的短文，掌握其大意，然后从21至22各题所给的A、B、C、D选项中选出最佳答案。",
            "A shared fictional cloze passage.",
            "21. A. one B. two C. three D. four",
            "22. A. east B. west C. north D. south",
        ]
        document = {
            "version": 1,
            "source_format": "docx",
            "blocks": [paragraph(i, text) for i, text in enumerate(texts)],
            "warnings": [],
        }
        bank = extract_candidate_bank(
            document, subject="english", source_id="ENG-CLOZE-INSTRUCTION"
        )
        self.assertEqual(
            [section["section_key"] for section in bank["sections"]],
            ["single_choice", "cloze"],
        )
        group = next(item for item in bank["groups"] if item["kind"] == "cloze_group")
        self.assertIn("shared fictional cloze passage", group["shared_material_text"])
        self.assertEqual(len(group["child_candidate_ids"]), 2)

    def test_cloze_instruction_does_not_replace_scored_section_heading(self):
        texts = [
            "I. 单项选择（共1小题；每小题2分，满分2分）",
            "1. A fictional single-choice prompt. A. one B. two C. three D. four",
            "II. 完形填空（共2小题；每小题2分，满分4分）",
            "阅读下面的短文，掌握其大意，然后从21至22各题所给选项中选出最佳答案。",
            "A shared fictional cloze passage.",
            "21. A. one B. two C. three D. four",
            "22. A. east B. west C. north D. south",
        ]
        document = {
            "version": 1,
            "source_format": "docx",
            "blocks": [paragraph(i, text) for i, text in enumerate(texts)],
            "warnings": [],
        }
        bank = extract_candidate_bank(
            document, subject="english", source_id="ENG-CLOZE-SCORED-HEADING"
        )
        cloze = next(section for section in bank["sections"] if section["section_key"] == "cloze")
        self.assertIn("共2小题", cloze["heading"])
        score = build_score_evidence(bank)
        cloze_score = next(section for section in score["sections"] if section["section_key"] == "cloze")
        self.assertEqual(cloze_score["status"], "usable")
        self.assertEqual(cloze_score["per_question_score"], 2.0)
        group = next(item for item in bank["groups"] if item["kind"] == "cloze_group")
        self.assertIn("然后从21至22", group["shared_material_text"])

    def test_leading_numbered_choice_instruction_is_ledgered_not_a_question(self):
        texts = [
            "I. 单项选择（共2小题）",
            "2. 从A、B、C、D四个选项中选出可以填入空白处的最佳答案。",
            "1. Where is the fictional student going? A. Home B. School C. Work D. Park",
            "2. What does the fictional student need? A. A pen B. A book C. A bag D. A map",
        ]
        document = {
            "version": 1,
            "source_format": "docx",
            "blocks": [paragraph(i, text) for i, text in enumerate(texts)],
            "warnings": [],
        }
        bank = extract_candidate_bank(
            document, subject="english", source_id="ENG-INSTRUCTION-LEDGER"
        )
        jsonschema.validate(bank, self.schema)

        self.assertEqual(
            [q["source_number"] for q in bank["candidates"]], [1, 2]
        )
        self.assertEqual(bank["summary"]["candidate_count"], 2)
        self.assertEqual(bank["summary"]["non_question_occurrence_count"], 1)
        occurrence = bank["non_question_occurrences"][0]
        self.assertEqual(occurrence["source_number"], 2)
        self.assertEqual(occurrence["locator"], "word/document.xml/body/1")
        self.assertEqual(
            occurrence["reason_code"], "leading_english_choice_instruction"
        )
        self.assertEqual(len(occurrence["text_sha256"]), 64)

    def test_legacy_choice_heading_missing_first_glyph_is_not_inferred(self):
        texts = [
            "1.项选择（共2小题；每小题2分，满分4分）",
            "从A、B、C、D四个选项中选出可以填入空白处的最佳答案。",
            "1. Where is the fictional student going? A. Home B. School C. Work D. Park",
            "2. What does the fictional student need? A. A pen B. A book C. A bag D. A map",
        ]
        document = {
            "version": 1,
            "source_format": "docx",
            "blocks": [paragraph(i, text) for i, text in enumerate(texts)],
            "warnings": [],
        }
        bank = extract_candidate_bank(
            document, subject="english", source_id="ENG-LEGACY-HEADING"
        )
        jsonschema.validate(bank, self.schema)

        self.assertEqual(bank["sections"][0]["section_key"], "single_choice")
        self.assertFalse(bank["sections"][0]["inferred"])
        self.assertEqual([q["status"] for q in bank["candidates"]], ["parsed", "parsed"])
        self.assertEqual(bank["summary"]["non_question_occurrence_count"], 0)
        self.assertEqual(
            detect_section("english", "1.单项填空（共20小题，每题2分，满分40分）"),
            ("single_choice", "single_choice"),
        )

    def test_legacy_accented_reading_label_is_normalized_with_provenance(self):
        texts = [
            "III. 阅读理解",
            "Á",
            "A fictional first passage.",
            "31. What is the first fictional passage about? A. One B. Two C. Three D. Four",
            "32. Which detail appears in the first fictional passage? A. Red B. Blue C. Green D. Gold",
            "33. What can be inferred from the first fictional passage? A. North B. South C. East D. West",
            "B",
            "A fictional second passage.",
            "34. What is the second fictional passage about? A. One B. Two C. Three D. Four",
        ]
        document = {
            "version": 1,
            "source_format": "docx",
            "blocks": [paragraph(i, text) for i, text in enumerate(texts)],
            "warnings": [],
        }
        bank = extract_candidate_bank(
            document, subject="english", source_id="ENG-LEGACY-LABEL"
        )
        jsonschema.validate(bank, self.schema)

        groups = [g for g in bank["groups"] if g["kind"] == "reading_group"]
        self.assertEqual([g["label"] for g in groups], ["A", "B"])
        self.assertEqual([len(g["child_candidate_ids"]) for g in groups], [3, 1])
        self.assertEqual(groups[0]["source_label"], "Á")
        self.assertEqual(groups[0]["label_locator"], "word/document.xml/body/1")
        self.assertEqual(
            groups[0]["label_normalization"],
            "legacy_english_reading_font_mapping",
        )
        self.assertEqual(
            [q["source_number"] for q in bank["candidates"]], [31, 32, 33, 34]
        )

    def test_legacy_roman_three_reading_heading_starts_new_section(self):
        texts = [
            "II. 完形填空",
            "A shared fictional cloze passage.",
            "21. A. one B. two C. three D. four",
            "22. A. east B. west C. north D. south",
            "11I、阅读理解（共2小题；每小题4分）",
            "阅读下列短文，然后从各题所给的选项中选出一个答案。",
            "A",
            "A fictional reading passage.",
            "31. What is the passage about? A. One B. Two C. Three D. Four",
            "32. What is the main point? A. Five B. Six C. Seven D. Eight",
        ]
        document = {
            "version": 1,
            "source_format": "docx",
            "blocks": [paragraph(i, text) for i, text in enumerate(texts)],
            "warnings": [],
        }
        bank = extract_candidate_bank(document, subject="english", source_id="ENG-ROMAN-III")
        self.assertEqual(
            [section["section_key"] for section in bank["sections"]],
            ["cloze", "reading"],
        )
        self.assertEqual(
            [candidate["source_number"] for candidate in bank["candidates"]],
            [21, 22, 31, 32],
        )
        reading_groups = [group for group in bank["groups"] if group["kind"] == "reading_group"]
        self.assertEqual([group["label"] for group in reading_groups], ["A"])
        self.assertEqual(len(reading_groups[0]["child_candidate_ids"]), 2)
        self.assertEqual(
            detect_section("english", "III,阅读理解（共15小题）"),
            ("reading", "reading_group"),
        )
        self.assertEqual(
            detect_section("english", "II.完型填空（共10题）"),
            ("cloze", "cloze_group"),
        )

    def test_missing_first_heading_recovers_long_run_but_marks_review(self):
        texts = [
            "考试说明",
            "1. 注意事项一。",
            "2. 注意事项二。",
            "1. Fictional q1 A. aB. bC. cD. d",
            "2. Fictional q2 A. aB. bC. cD. d",
            "3. Fictional q3 A. aB. bC. cD. d",
            "4. Fictional q4 A. aB. bC. cD. d",
            "5. Fictional q5 A. aB. bC. cD. d",
            "II.完形填空",
            "Shared passage.",
            "21. A. oneB. twoC. threeD. four"
        ]
        document = {
            "version": 1,
            "source_format": "docx",
            "blocks": [paragraph(i, text) for i, text in enumerate(texts)],
            "warnings": [],
        }
        bank = extract_candidate_bank(document, subject="english", source_id="ENG-NOHEAD")
        inferred = [
            q for q in bank["candidates"]
            if q["section_key"] == "single_choice"
        ]
        self.assertEqual([q["source_number"] for q in inferred], [1, 2, 3, 4, 5])
        self.assertTrue(all(q["status"] == "needs_review" for q in inferred))
        self.assertTrue(all(
            "section_heading_missing_inferred_single_choice" in q["review_reasons"]
            for q in inferred
        ))
        self.assertTrue(bank["sections"][0]["inferred"])

    def test_standalone_reading_analysis_tail_is_not_question_content(self):
        texts = [
            "III. 阅读理解",
            "A",
            "A fictional passage.",
            "31. What is the fictional passage about?",
            "A. one",
            "B. two",
            "C. three",
            "D. four",
            "解析：选B。A fictional explanation.",
            "32. What detail appears in the fictional passage?",
            "A. red",
            "B. blue",
            "C. green",
            "D. gold",
            "32.B【解析】A second fictional explanation.",
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
            source_id="ENG-STANDALONE-READING",
        )
        jsonschema.validate(bank, self.schema)
        self.assertEqual(
            [q["source_number"] for q in bank["candidates"]],
            [31, 32],
        )
        self.assertTrue(all(q["status"] == "parsed" for q in bank["candidates"]))
        self.assertTrue(all(len(q["options"]) == 4 for q in bank["candidates"]))
        self.assertFalse(any(
            "explanation" in q["stem_text"]
            for q in bank["candidates"]
        ))

    def test_inline_numbered_answer_analysis_is_not_a_fake_question(self):
        texts = [
            "I. 单项选择",
            "1. A fictional prompt. A. one B. two C. three D. four",
            "2. Another fictional prompt. A. one B. two C. three D. four",
            "1.B【解析】A fictional explanation.",
            "2.C.考查 fictional grammar.",
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
            source_id="ENG-MIXED-ANSWER-APPENDIX",
        )
        self.assertEqual(
            [q["source_number"] for q in bank["candidates"]],
            [1, 2],
        )

    def test_pdf_self_test_block_splits_numbered_choice_questions(self):
        document = {
            "version": 1,
            "source_format": "pdf",
            "blocks": [
                paragraph(
                    0,
                    "【自主检测】\n"
                    "1. A fictional grammar question.\n"
                    "A. one\nB. two\nC. three\nD. four\n"
                    "2. Another fictional grammar question.\n"
                    "A. red\nB. blue\nC. green\nD. gold",
                ),
                paragraph(1, "答案:\n1-2 A B"),
            ],
            "warnings": [],
        }
        bank = extract_candidate_bank(
            document,
            subject="english",
            source_id="ENG-SELF-TEST",
        )
        jsonschema.validate(bank, self.schema)
        self.assertEqual(
            [item["source_number"] for item in bank["candidates"]],
            [1, 2],
        )
        self.assertTrue(all(
            item["section_key"] == "single_choice_self_test_base"
            for item in bank["candidates"]
        ))
        self.assertTrue(all(
            item["status"] == "parsed" and len(item["options"]) == 4
            for item in bank["candidates"]
        ))
        self.assertTrue(all(
            "#line-" in locator
            for item in bank["candidates"]
            for locator in item["locators"]
        ))

    def test_numbered_self_tests_have_distinct_section_scopes(self):
        document = {
            "version": 1,
            "source_format": "pdf",
            "blocks": [
                paragraph(
                    0,
                    "【自主检测1】\n"
                    "1. A fictional question. A. one B. two C. three D. four\n"
                    "答案: A",
                ),
                paragraph(
                    1,
                    "【自主检测2】\n"
                    "1. A second fictional question. A. one B. two C. three D. four\n"
                    "答案: B",
                ),
            ],
            "warnings": [],
        }
        bank = extract_candidate_bank(
            document,
            subject="english",
            source_id="ENG-SELF-TEST-MULTI",
        )
        self.assertEqual(
            [item["section_key"] for item in bank["candidates"]],
            ["single_choice_self_test_1", "single_choice_self_test_2"],
        )

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

    def test_word_spelling_phrase_inside_question_is_not_a_new_section(self):
        texts = [
            "IV.单词拼写(共2小题)",
            "46. The police called it an ______ (意外事故). (根据汉语提示单词拼写)",
            "47. Please ______ the correct word. (根据汉语提示单词拼写)",
            "V.书面表达(满分10分)",
            "Write a fictional note."
        ]
        document = {
            "version": 1,
            "source_format": "docx",
            "blocks": [paragraph(i, text) for i, text in enumerate(texts)],
            "warnings": [],
        }
        bank = extract_candidate_bank(document, subject="english", source_id="ENG-SPELL")
        spelling = [q for q in bank["candidates"] if q["section_key"] == "word_spelling"]
        self.assertEqual([q["source_number"] for q in spelling], [46, 47])
        self.assertEqual(
            [s["section_key"] for s in bank["sections"]],
            ["word_spelling", "writing"],
        )

    def test_source_visual_refs_are_preserved_but_review_gated(self):
        rich_paragraph = paragraph(
            1,
            "1. 带图的虚构题。",
            {
                "type": "image_ref",
                "relationship_id": "rId1",
                "locator": "word/document.xml/body/1/drawing/0",
                "status": "captured_not_normalized",
                "source": "drawingml",
                "asset_sha256": "a" * 64,
                "asset_target": "media/figure-a.png",
                "asset_extension": ".png",
            },
        )
        rich_paragraph["inlines"].append({
            "type": "image_ref",
            "relationship_id": "rId2",
            "locator": "word/document.xml/body/1/drawing/1",
            "status": "captured_not_normalized",
            "source": "drawingml",
            "asset_sha256": "b" * 64,
            "asset_target": "media/figure-b.png",
            "asset_extension": ".png",
        })
        document = {
            "version": 1,
            "source_format": "docx",
            "blocks": [
                paragraph(0, "一、单项选择题"),
                rich_paragraph,
                paragraph(2, "A. 甲 B. 乙 C. 丙 D. 丁"),
            ],
            "warnings": ["image_relationship_not_normalized"],
        }
        bank = extract_candidate_bank(document, subject="politics", source_id="POL-RICH")
        jsonschema.validate(bank, self.schema)
        self.assertEqual(bank["summary"]["blocker_count"], 0)
        self.assertEqual(bank["summary"]["candidate_count"], 1)
        question = bank["candidates"][0]
        self.assertEqual(question["status"], "needs_review")
        self.assertIn(
            "source_visual_asset_requires_resolution",
            question["review_reasons"],
        )
        self.assertEqual(
            [ref["relationship_id"] for ref in question["asset_refs"]],
            ["rId1", "rId2"],
        )

    def test_politics_fill_blank_preserves_explicit_blank_node(self):
        document = {
            "version": 1,
            "source_format": "docx",
            "blocks": [
                paragraph(0, "二、填空题"),
                paragraph(1, "26. 2024年5月3日，\t探测器发射。"),
            ],
            "warnings": [],
        }
        bank = extract_candidate_bank(
            document,
            subject="politics",
            source_id="POL-BLANK",
        )
        jsonschema.validate(bank, self.schema)
        question = bank["candidates"][0]
        self.assertEqual(question["kind"], "fill_blank")
        self.assertEqual(question["stem_text"], "2024年5月3日，\t探测器发射。")
        self.assertTrue(any(
            node["type"] == "blank"
            for node in question["stem_rich"]
        ))

    def test_fill_blank_without_source_marker_does_not_invent_blank(self):
        document = {
            "version": 1,
            "source_format": "docx",
            "blocks": [
                paragraph(0, "二、填空题"),
                paragraph(1, "26. 这是一条已经丢失空格标记的虚构题目。"),
            ],
            "warnings": [],
        }
        bank = extract_candidate_bank(
            document,
            subject="politics",
            source_id="POL-NO-BLANK",
        )
        question = bank["candidates"][0]
        self.assertNotIn("stem_rich", question)

    def test_politics_fill_blank_preserves_explicit_blank_node(self):
        document = {
            "version": 1,
            "source_format": "docx",
            "blocks": [
                paragraph(0, "二、填空题"),
                paragraph(1, "26. 2024年5月3日，\t探测器发射。"),
            ],
            "warnings": [],
        }
        bank = extract_candidate_bank(
            document,
            subject="politics",
            source_id="POL-BLANK",
        )
        jsonschema.validate(bank, self.schema)
        question = bank["candidates"][0]
        self.assertEqual(question["kind"], "fill_blank")
        self.assertEqual(question["stem_text"], "2024年5月3日，\t探测器发射。")
        self.assertTrue(any(
            node["type"] == "blank"
            for node in question["stem_rich"]
        ))

    def test_fill_blank_without_source_marker_does_not_invent_blank(self):
        document = {
            "version": 1,
            "source_format": "docx",
            "blocks": [
                paragraph(0, "二、填空题"),
                paragraph(1, "26. 这是一条已经丢失空格标记的虚构题目。"),
            ],
            "warnings": [],
        }
        bank = extract_candidate_bank(
            document,
            subject="politics",
            source_id="POL-NO-BLANK",
        )
        question = bank["candidates"][0]
        self.assertNotIn("stem_rich", question)

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

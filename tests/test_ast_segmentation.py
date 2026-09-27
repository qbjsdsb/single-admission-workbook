import unittest

from engine.document.consume import DocumentNormalizationRequired, segmentation_view
from engine.parse.document_exam import split_document_questions


def p(locator, text, page=None):
    block = {
        "type": "paragraph",
        "locator": locator,
        "inlines": [{"type": "text", "text": text}],
    }
    if page is not None:
        block["page"] = page
    return block


class AstSegmentationTests(unittest.TestCase):
    def test_politics_questions_keep_locators(self):
        document = {
            "version": 1,
            "source_format": "docx",
            "warnings": [],
            "blocks": [
                p("b0", "一、单项选择题"),
                p("b1", "1. 第一题虚构题干。"),
                p("b2", "A. 甲 B. 乙 C. 丙 D. 丁"),
                p("b3", "2. 第二题虚构题干。"),
                p("b4", "A. 子 B. 丑 C. 寅 D. 卯"),
                p("b5", "二、填空题"),
                p("b6", "3. 虚构填空题________。"),
            ],
        }
        questions = split_document_questions(document, "politics")
        self.assertEqual([q.number for q in questions], [1, 2, 3])
        self.assertEqual(questions[0].section_key, "single_choice")
        self.assertEqual(questions[0].locators, ("b1", "b2"))
        self.assertEqual(questions[2].section_key, "fill_blank")
        self.assertEqual(questions[2].locators, ("b6",))

    def test_pdf_page_provenance_survives_segmentation(self):
        document = {
            "version": 1,
            "source_format": "pdf",
            "warnings": [],
            "blocks": [
                p("pdf/page/2/block/0", "一、单项选择题", 2),
                p("pdf/page/2/block/1", "1. 虚构题干。", 2),
                p("pdf/page/2/block/2", "A. 甲 B. 乙 C. 丙 D. 丁", 2),
            ],
        }
        questions = split_document_questions(document, "politics")
        self.assertEqual(questions[0].paragraphs[0].page, 2)
        self.assertEqual(questions[0].locators[0], "pdf/page/2/block/1")

    def test_english_group_preserves_shared_material_and_child_locators(self):
        document = {
            "version": 1,
            "source_format": "docx",
            "warnings": [],
            "blocks": [
                p("h", "II.完形填空"),
                p("m", "This is fictional shared material."),
                p("q1", "21. A. one B. two C. three D. four"),
                p("q2", "22. A. red B. blue C. green D. black"),
            ],
        }
        groups = split_document_questions(document, "english")
        self.assertEqual(len(groups), 1)
        group = groups[0]
        self.assertEqual(group.kind, "cloze_group")
        self.assertEqual([x.locator for x in group.shared_material], ["m"])
        self.assertEqual([q.number for q in group.questions], [21, 22])
        self.assertEqual(group.questions[0].locators, ("q1",))

    def test_unresolved_rich_content_blocks_segmentation(self):
        document = {
            "version": 1,
            "source_format": "docx",
            "warnings": ["math_omml_not_normalized"],
            "blocks": [
                p("h", "一、单项选择题"),
                {
                    "type": "paragraph",
                    "locator": "q1",
                    "inlines": [
                        {"type": "text", "text": "1. 含公式"},
                        {
                            "type": "math_omml",
                            "xml": "<m:oMath/>",
                            "locator": "q1/math/0",
                            "status": "captured_not_normalized",
                        },
                    ],
                },
            ],
        }
        view = segmentation_view(document)
        self.assertIn("q1/math/0:math_omml", view.blockers)
        with self.assertRaises(DocumentNormalizationRequired):
            split_document_questions(document, "politics")

    def test_ocr_required_block_is_not_silently_ignored(self):
        document = {
            "version": 1,
            "source_format": "pdf",
            "warnings": ["ocr_required"],
            "blocks": [
                p("pdf/page/1/block/0", "一、单项选择题", 1),
                {
                    "type": "unsupported",
                    "locator": "pdf/page/2",
                    "feature": "ocr_required",
                    "page": 2,
                },
            ],
        }
        with self.assertRaisesRegex(DocumentNormalizationRequired, "ocr_required"):
            split_document_questions(document, "politics")


if __name__ == "__main__":
    unittest.main()

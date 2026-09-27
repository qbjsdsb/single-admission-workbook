import unittest

from engine.pipeline.classification import build_safe_classification_proposals


class ClassificationProposalTests(unittest.TestCase):
    def test_only_direct_source_type_mappings_auto_assign(self):
        bank = {
            "source_id": "ENG",
            "subject": "english",
            "candidates": [
                {"candidate_id": "Q1", "section_key": "cloze"},
                {"candidate_id": "Q2", "section_key": "writing"},
                {"candidate_id": "Q3", "section_key": "reading"},
                {"candidate_id": "Q4", "section_key": "single_choice"},
                {"candidate_id": "Q5", "section_key": "word_spelling"},
            ],
        }
        manifest = build_safe_classification_proposals(bank)
        by_id = {x["candidate_id"]: x for x in manifest["decisions"]}

        self.assertEqual(by_id["Q1"]["decision"], "assign")
        self.assertEqual(by_id["Q1"]["chapter_key"], "cloze")
        self.assertEqual(by_id["Q1"]["section_key"], "cloze_training")

        self.assertEqual(by_id["Q2"]["decision"], "assign")
        self.assertEqual(by_id["Q2"]["chapter_key"], "writing")
        self.assertEqual(by_id["Q2"]["section_key"], "writing_training")

        self.assertEqual(by_id["Q3"]["decision"], "defer")
        self.assertEqual(by_id["Q3"]["note"], "reading_subskill_unknown")
        self.assertEqual(by_id["Q4"]["decision"], "defer")
        self.assertEqual(by_id["Q5"]["decision"], "defer")

    def test_politics_never_auto_classifies_without_approved_taxonomy(self):
        bank = {
            "source_id": "POL",
            "subject": "politics",
            "candidates": [
                {"candidate_id": "P1", "section_key": "single_choice"},
                {"candidate_id": "P2", "section_key": "material_answer"},
            ],
        }
        manifest = build_safe_classification_proposals(bank)
        self.assertTrue(all(x["decision"] == "defer" for x in manifest["decisions"]))
        self.assertTrue(all(x["note"] == "politics_taxonomy_not_approved" for x in manifest["decisions"]))


if __name__ == "__main__":
    unittest.main()

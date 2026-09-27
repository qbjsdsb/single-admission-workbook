import unittest

from engine.pipeline.classification import build_safe_classification_proposals


def enrichment(items):
    return {
        "schema_version": 1,
        "candidate_source_id": "ENG",
        "items": items,
    }


class ClassificationProposalTests(unittest.TestCase):
    def test_direct_source_sections_auto_assign_without_teacher_prose(self):
        bank = {
            "source_id": "ENG",
            "subject": "english",
            "candidates": [
                {"candidate_id": "Q1", "section_key": "cloze"},
                {"candidate_id": "Q2", "section_key": "writing"},
                {"candidate_id": "Q3", "section_key": "word_spelling"},
            ],
        }
        manifest = build_safe_classification_proposals(bank)
        by_id = {x["candidate_id"]: x for x in manifest["decisions"]}

        self.assertEqual(
            (by_id["Q1"]["chapter_key"], by_id["Q1"]["section_key"]),
            ("cloze", "cloze_training"),
        )
        self.assertEqual(
            (by_id["Q2"]["chapter_key"], by_id["Q2"]["section_key"]),
            ("writing", "writing_training"),
        )
        self.assertEqual(
            (by_id["Q3"]["chapter_key"], by_id["Q3"]["section_key"]),
            ("vocabulary_patterns", "word_spelling_training"),
        )

    def test_trusted_teacher_analysis_refines_grammar_and_reading(self):
        bank = {
            "source_id": "ENG",
            "subject": "english",
            "candidates": [
                {"candidate_id": "Q1", "section_key": "single_choice"},
                {"candidate_id": "Q2", "section_key": "single_choice"},
                {"candidate_id": "Q3", "section_key": "reading"},
                {"candidate_id": "Q4", "section_key": "reading"},
            ],
        }
        teacher = enrichment([
            {"candidate_id": "Q1", "analysis": "考查非谓语动词。虚构解析。"},
            {"candidate_id": "Q2", "analysis": "考查情景交际。虚构解析。"},
            {"candidate_id": "Q3", "analysis": "细节理解题。根据第二段可知。"},
            {"candidate_id": "Q4", "analysis": "词句猜测题。根据上下文可知。"},
        ])
        manifest = build_safe_classification_proposals(
            bank,
            teacher_enrichment=teacher,
        )
        by_id = {x["candidate_id"]: x for x in manifest["decisions"]}

        self.assertEqual(
            (by_id["Q1"]["chapter_key"], by_id["Q1"]["section_key"]),
            ("grammar", "verb"),
        )
        self.assertEqual(
            (by_id["Q2"]["chapter_key"], by_id["Q2"]["section_key"]),
            ("vocabulary_patterns", "key_sentences"),
        )
        self.assertEqual(
            (by_id["Q3"]["chapter_key"], by_id["Q3"]["section_key"]),
            ("reading", "detail"),
        )
        self.assertEqual(
            (by_id["Q4"]["chapter_key"], by_id["Q4"]["section_key"]),
            ("reading", "word_guessing"),
        )
        self.assertTrue(all(
            "trusted_teacher_analysis" in by_id[qid]["note"]
            for qid in ("Q1", "Q2", "Q3", "Q4")
        ))

    def test_older_direct_quote_reading_analysis_maps_only_to_detail(self):
        bank = {
            "source_id": "ENG",
            "subject": "english",
            "candidates": [{"candidate_id": "Q1", "section_key": "reading"}],
        }
        teacher = enrichment([
            {
                "candidate_id": "Q1",
                "analysis": "根据文章第二段的句子可知答案为B。",
            },
        ])
        manifest = build_safe_classification_proposals(
            bank,
            teacher_enrichment=teacher,
        )
        decision = manifest["decisions"][0]
        self.assertEqual(decision["section_key"], "detail")

    def test_unknown_semantics_use_broad_source_section_fallback(self):
        bank = {
            "source_id": "ENG",
            "subject": "english",
            "candidates": [
                {"candidate_id": "Q1", "section_key": "single_choice"},
                {"candidate_id": "Q2", "section_key": "reading"},
            ],
        }
        teacher = enrichment([
            {"candidate_id": "Q1", "analysis": "句意：虚构句子。"},
        ])
        manifest = build_safe_classification_proposals(
            bank,
            teacher_enrichment=teacher,
        )
        by_id = {x["candidate_id"]: x for x in manifest["decisions"]}

        self.assertEqual(
            (by_id["Q1"]["chapter_key"], by_id["Q1"]["section_key"]),
            ("grammar", "mixed_choice"),
        )
        self.assertEqual(
            (by_id["Q2"]["chapter_key"], by_id["Q2"]["section_key"]),
            ("reading", "reading_training"),
        )
        self.assertTrue(all(
            "no semantic subtype guessed" in by_id[qid]["note"]
            for qid in ("Q1", "Q2")
        ))

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
        self.assertTrue(all(
            x["note"] == "politics_taxonomy_not_approved"
            for x in manifest["decisions"]
        ))


if __name__ == "__main__":
    unittest.main()

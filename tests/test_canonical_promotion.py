import json
from pathlib import Path
import unittest

import jsonschema

from engine.pipeline.canonical_promotion import (
    build_book_ready_dataset,
    promote_to_canonical_draft,
)

ROOT = Path(__file__).resolve().parents[1]


def scored_bank():
    return {
        "schema_version": 1,
        "subject": "english",
        "candidate_source_id": "ENG-SOURCE",
        "assigned": [
            {
                "candidate_id": "ENG-SOURCE:q:1:abcd1234",
                "source_id": "ENG-SOURCE",
                "subject": "english",
                "source_number": 1,
                "section_key": "single_choice",
                "kind": "single_choice",
                "stem_text": "A fictional grammar prompt.",
                "options": [
                    {"label": "A", "text": "go"},
                    {"label": "B", "text": "goes"},
                    {"label": "C", "text": "going"},
                    {"label": "D", "text": "gone"},
                ],
                "group_id": None,
                "locators": ["word/document.xml/body/10"],
                "verified_answer": "B",
                "verification_method": "human_review",
                "verification_note": "",
                "override_reason": "",
                "machine_aggregate_status": "single_source_consistent",
                "machine_answer": "B",
                "score": 2.0,
                "score_source": "explicit",
            }
        ],
        "unresolved": [],
        "summary": {"assigned": 1, "unresolved": 0},
    }


def classification(decision="assign", section="verb"):
    item = {
        "candidate_id": "ENG-SOURCE:q:1:abcd1234",
        "decision": decision,
    }
    if decision == "assign":
        item.update({
            "chapter_key": "grammar",
            "section_key": section,
            "tags": ["动词"],
            "difficulty": "standard",
        })
    return {
        "schema_version": 1,
        "candidate_source_id": "ENG-SOURCE",
        "subject": "english",
        "decisions": [item],
    }


class CanonicalPromotionTests(unittest.TestCase):
    def setUp(self):
        self.question_schema = json.loads(
            (ROOT / "schema/question.schema.json").read_text(encoding="utf-8")
        )
        self.draft_schema = json.loads(
            (ROOT / "schema/canonical-draft.schema.json").read_text(encoding="utf-8")
        )
        self.classification_schema = json.loads(
            (ROOT / "schema/classification-manifest.schema.json").read_text(encoding="utf-8")
        )

    def test_verified_scored_classified_candidate_promotes_to_question_schema(self):
        manifest = classification()
        jsonschema.validate(manifest, self.classification_schema)
        draft = promote_to_canonical_draft(scored_bank(), manifest)
        jsonschema.validate(draft, self.draft_schema)
        self.assertEqual(draft["summary"], {"promoted": 1, "unresolved": 0})

        question = draft["questions"][0]
        jsonschema.validate(question, self.question_schema)
        self.assertRegex(question["id"], r"^ENG_[0-9A-F]{12}$")
        self.assertEqual(question["answer"], "B")
        self.assertEqual(question["score"], 2.0)
        self.assertEqual(question["chapter_key"], "grammar")
        self.assertEqual(question["section_key"], "verb")
        self.assertEqual(question["layout"]["choice_mode"], "auto")

    def test_missing_classification_never_promotes(self):
        manifest = {
            "schema_version": 1,
            "candidate_source_id": "ENG-SOURCE",
            "subject": "english",
            "decisions": [],
        }
        draft = promote_to_canonical_draft(scored_bank(), manifest)
        self.assertEqual(draft["summary"]["promoted"], 0)
        self.assertEqual(
            draft["unresolved"][0]["reason"], "missing_classification"
        )

    def test_deferred_classification_never_promotes(self):
        draft = promote_to_canonical_draft(
            scored_bank(), classification(decision="defer")
        )
        self.assertEqual(draft["summary"]["promoted"], 0)
        self.assertEqual(
            draft["unresolved"][0]["reason"], "classification_deferred"
        )

    def test_teacher_enrichment_adds_analysis_without_changing_answer(self):
        enrichment = {
            "schema_version": 1,
            "candidate_source_id": "ENG-SOURCE",
            "items": [{
                "candidate_id": "ENG-SOURCE:q:1:abcd1234",
                "analysis": "A fictional reviewed explanation.",
                "teacher_notes": "A fictional teaching note.",
            }],
        }
        draft = promote_to_canonical_draft(
            scored_bank(),
            classification(),
            teacher_enrichment=enrichment,
        )
        question = draft["questions"][0]
        self.assertEqual(question["answer"], "B")
        self.assertIn("reviewed explanation", question["analysis"][0]["text"])
        self.assertIn("teaching note", question["teacher_notes"][0]["text"])

    def test_structured_table_stem_survives_canonical_promotion(self):
        bank = scored_bank()
        bank["assigned"][0]["stem_rich"] = [
            {"type": "text", "text": "Plan:"},
            {"type": "table", "rows": [{"cells": [
                {"text": "Time", "grid_span": 1},
                {"text": "Activity", "grid_span": 1},
            ]}]},
        ]
        draft = promote_to_canonical_draft(bank, classification())
        question = draft["questions"][0]
        jsonschema.validate(question, self.question_schema)
        self.assertEqual(question["stem"][1]["type"], "table")

    def test_classification_manifest_must_match_source(self):
        manifest = classification()
        manifest["candidate_source_id"] = "OTHER"
        with self.assertRaisesRegex(ValueError, "classification manifest source mismatch"):
            promote_to_canonical_draft(scored_bank(), manifest)

    def test_book_ready_dataset_rejects_unknown_curriculum_keys(self):
        draft = promote_to_canonical_draft(scored_bank(), classification())
        curriculum = {
            "english": [
                {
                    "key": "grammar",
                    "title": "语法",
                    "sections": [{"key": "noun", "title": "名词"}],
                }
            ]
        }
        with self.assertRaisesRegex(ValueError, "classification not present in curriculum"):
            build_book_ready_dataset(draft, curriculum)

    def test_book_ready_dataset_accepts_known_curriculum_keys(self):
        draft = promote_to_canonical_draft(scored_bank(), classification())
        curriculum = {
            "english": [
                {
                    "key": "grammar",
                    "title": "语法",
                    "sections": [{"key": "verb", "title": "动词"}],
                }
            ]
        }
        dataset = build_book_ready_dataset(draft, curriculum)
        self.assertEqual(len(dataset["questions"]), 1)
        self.assertEqual(dataset["curriculum"]["english"][0]["key"], "grammar")


if __name__ == "__main__":
    unittest.main()

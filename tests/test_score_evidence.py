import json
from pathlib import Path
import unittest

import jsonschema

from engine.pipeline.scoring import build_score_evidence, apply_score_evidence

ROOT = Path(__file__).resolve().parents[1]


def candidate_bank(section):
    return {
        "source_id": "SRC",
        "subject": "english",
        "sections": [section],
    }


def verified_bank(section_key="single_choice"):
    return {
        "subject": "english",
        "candidate_source_id": "SRC",
        "verified": [{
            "candidate_id": "Q1",
            "source_id": "SRC",
            "subject": "english",
            "source_number": 1,
            "section_key": section_key,
            "kind": "single_choice",
            "stem_text": "A fictional prompt.",
            "options": [
                {"label": "A", "text": "one"},
                {"label": "B", "text": "two"},
                {"label": "C", "text": "three"},
                {"label": "D", "text": "four"},
            ],
            "group_id": None,
            "locators": ["src/1"],
            "verified_answer": "A",
            "verification_method": "human_review",
            "verification_note": "",
            "override_reason": "",
            "machine_aggregate_status": "single_source_consistent",
            "machine_answer": "A",
        }],
    }


class ScoreEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.schema = json.loads(
            (ROOT / "schema/score-evidence.schema.json").read_text(encoding="utf-8")
        )

    def test_explicit_count_per_and_full_score_is_usable(self):
        bank = candidate_bank({
            "section_key": "single_choice",
            "heading": "I.单项选择（共20小题，每小题2分，满分40分）",
            "candidate_count": 20,
        })
        evidence = build_score_evidence(bank)
        jsonschema.validate(evidence, self.schema)
        section = evidence["sections"][0]
        self.assertEqual(section["status"], "usable")
        self.assertEqual(section["declared_count"], 20)
        self.assertEqual(section["per_question_score"], 2.0)
        self.assertEqual(section["full_score"], 40.0)
        self.assertEqual(section["per_question_source"], "explicit")
        self.assertEqual(section["full_score_source"], "explicit")

    def test_declared_count_mismatch_is_conflict(self):
        bank = candidate_bank({
            "section_key": "single_choice",
            "heading": "I.单项选择（共20小题，每小题2分，满分40分）",
            "candidate_count": 19,
        })
        evidence = build_score_evidence(bank)
        section = evidence["sections"][0]
        self.assertEqual(section["status"], "conflict")
        self.assertIn(
            "declared_count_20_!=_parsed_count_19",
            section["reasons"],
        )

    def test_score_math_mismatch_is_conflict(self):
        bank = candidate_bank({
            "section_key": "single_choice",
            "heading": "I.单项选择（共20小题，每小题2分，满分30分）",
            "candidate_count": 20,
        })
        section = build_score_evidence(bank)["sections"][0]
        self.assertEqual(section["status"], "conflict")
        self.assertTrue(any("declared_score_math_40" in r for r in section["reasons"]))

    def test_total_only_multi_question_section_remains_incomplete(self):
        bank = candidate_bank({
            "section_key": "fill_blank",
            "heading": "IV.单词拼写（共10小题，满分20分）",
            "candidate_count": 10,
        })
        section = build_score_evidence(bank)["sections"][0]
        self.assertEqual(section["status"], "incomplete")
        self.assertIsNone(section["per_question_score"])
        self.assertEqual(section["full_score"], 20.0)

    def test_per_question_plus_count_can_derive_full_score(self):
        bank = candidate_bank({
            "section_key": "single_choice",
            "heading": "I.单项选择（共20小题，每小题2分）",
            "candidate_count": 20,
        })
        section = build_score_evidence(bank)["sections"][0]
        self.assertEqual(section["status"], "usable")
        self.assertEqual(section["full_score"], 40.0)
        self.assertEqual(
            section["full_score_source"],
            "derived_from_count_times_per_question",
        )

    def test_single_writing_task_can_use_section_full_score(self):
        bank = candidate_bank({
            "section_key": "writing",
            "heading": "V.书面表达（满分10分）",
            "candidate_count": 1,
        })
        score = build_score_evidence(bank)
        section = score["sections"][0]
        self.assertEqual(section["status"], "usable")
        assigned = apply_score_evidence(
            {
                **verified_bank(section_key="writing"),
                "verified": [{
                    **verified_bank(section_key="writing")["verified"][0],
                    "section_key": "writing",
                    "kind": "composition",
                }],
            },
            score,
        )
        self.assertEqual(assigned["summary"]["assigned"], 1)
        self.assertEqual(assigned["assigned"][0]["score"], 10.0)

    def test_conflicting_section_score_is_not_attached(self):
        bank = candidate_bank({
            "section_key": "single_choice",
            "heading": "I.单项选择（共20小题，每小题2分，满分30分）",
            "candidate_count": 20,
        })
        score = build_score_evidence(bank)
        assigned = apply_score_evidence(verified_bank(), score)
        self.assertEqual(assigned["summary"]["assigned"], 0)
        self.assertEqual(
            assigned["unresolved"][0]["reason"],
            "section_score_conflict",
        )

    def test_incomplete_multi_question_score_is_not_attached(self):
        bank = candidate_bank({
            "section_key": "single_choice",
            "heading": "I.单项选择（共20小题，满分40分）",
            "candidate_count": 20,
        })
        score = build_score_evidence(bank)
        assigned = apply_score_evidence(verified_bank(), score)
        self.assertEqual(assigned["summary"]["assigned"], 0)
        self.assertEqual(assigned["unresolved"][0]["reason"], "score_incomplete")


if __name__ == "__main__":
    unittest.main()

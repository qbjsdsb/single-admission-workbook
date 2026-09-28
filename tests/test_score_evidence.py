import hashlib
import json
from pathlib import Path
import unittest

import jsonschema

from engine.pipeline.scoring import (
    apply_exam_total_residual_resolution,
    build_score_evidence,
    apply_score_evidence,
)

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

    def test_legacy_writing_score_without_character_fen_is_explicit(self):
        bank = candidate_bank({
            "section_key": "writing",
            "heading": "V.书面表达（满10分）",
            "candidate_count": 1,
        })
        section = build_score_evidence(bank)["sections"][0]
        self.assertEqual(section["status"], "usable")
        self.assertEqual(section["full_score"], 10.0)

    def test_legacy_writing_score_in_parentheses_is_explicit(self):
        bank = candidate_bank({
            "section_key": "writing",
            "heading": "五．书面表达（10分）",
            "candidate_count": 1,
        })
        evidence = build_score_evidence(bank)
        jsonschema.validate(evidence, self.schema)
        section = evidence["sections"][0]
        self.assertEqual(section["status"], "usable")
        self.assertEqual(section["full_score"], 10.0)
        self.assertEqual(section["full_score_source"], "explicit")

    def test_legacy_full_score_allows_source_period_after_marker(self):
        bank = candidate_bank({
            "section_key": "writing",
            "heading": "V.书面表达（满分。10分）",
            "candidate_count": 1,
        })
        section = build_score_evidence(bank)["sections"][0]
        self.assertEqual(section["status"], "usable")
        self.assertEqual(section["full_score"], 10.0)

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

    def test_explicit_first_volume_total_derives_only_the_missing_section(self):
        bank = {
            "source_id": "SRC",
            "subject": "english",
            "sections": [
                {"section_key": "single_choice", "heading": "[inferred missing single-choice heading]", "heading_locator": "src/q1", "candidate_count": 20, "inferred": True},
                {"section_key": "cloze", "heading": "II.完形填空（共10小题，每小题2分，满分20分）", "heading_locator": "src/cloze", "candidate_count": 10, "inferred": False},
                {"section_key": "reading", "heading": "III.阅读理解（共15小题，每小题4分，满分60分）", "heading_locator": "src/reading", "candidate_count": 15, "inferred": False},
            ],
        }
        score = build_score_evidence(bank)
        texts = {
            "src/q1": "1. A fictional question.",
            "src/cloze": bank["sections"][1]["heading"],
            "src/reading": bank["sections"][2]["heading"],
            "src/volume": "第一卷（三大题，共120分）",
        }
        resolved = apply_exam_total_residual_resolution(
            bank,
            score,
            {
                "candidate_source_id": "SRC",
                "target_section_key": "single_choice",
                "scope_section_keys": ["single_choice", "cloze", "reading"],
                "total_evidence": {
                    "locator": "src/volume",
                    "text_sha256": hashlib.sha256(texts["src/volume"].encode()).hexdigest(),
                },
                "reviewer": "GPT-6 Luna Max",
                "reviewed_at": "2026-09-28",
                "review_note": "The source explicitly declares three first-volume sections and 120 points; the other two sections explicitly score 20 and 60.",
            },
            source_text_by_locator=texts,
        )
        jsonschema.validate(resolved, self.schema)
        target = next(x for x in resolved["sections"] if x["section_key"] == "single_choice")
        self.assertEqual(target["per_question_score"], 2.0)
        self.assertEqual(target["full_score"], 40.0)
        self.assertEqual(target["per_question_source"], "derived_from_exam_total_residual")
        self.assertEqual(target["residual_resolution"]["other_section_scores"][0]["score"], 20.0)

    def test_residual_score_fails_when_other_scoped_section_is_not_explicit(self):
        bank = {
            "source_id": "SRC", "subject": "english",
            "sections": [
                {"section_key": "single_choice", "heading": "[inferred]", "heading_locator": "src/q", "candidate_count": 20, "inferred": True},
                {"section_key": "cloze", "heading": "II.完形填空", "heading_locator": "src/cloze", "candidate_count": 10, "inferred": False},
            ],
        }
        score = build_score_evidence(bank)
        text = "第一卷（两大题，共80分）"
        with self.assertRaisesRegex(ValueError, "lacks explicit usable score"):
            apply_exam_total_residual_resolution(
                bank, score,
                {"candidate_source_id": "SRC", "target_section_key": "single_choice", "scope_section_keys": ["single_choice", "cloze"], "total_evidence": {"locator": "src/total", "text_sha256": hashlib.sha256(text.encode()).hexdigest()}, "reviewer": "GPT-6 Luna Max", "reviewed_at": "2026-09-28", "review_note": "Synthetic test."},
                source_text_by_locator={"src/total": text, "src/q": "1. example", "src/cloze": "II.完形填空"},
            )

    def test_residual_score_does_not_override_target_score_conflict(self):
        bank = {
            "source_id": "SRC", "subject": "english",
            "sections": [
                {"section_key": "single_choice", "heading": "I.选择（共20小题，每小题2分，满分30分）", "heading_locator": "src/choice", "candidate_count": 20, "inferred": False},
                {"section_key": "cloze", "heading": "II.完形（共10小题，每小题2分，满分20分）", "heading_locator": "src/cloze", "candidate_count": 10, "inferred": False},
            ],
        }
        score = build_score_evidence(bank)
        total_text = "第一卷（两大题，共70分）"
        with self.assertRaisesRegex(ValueError, "not an incomplete gap"):
            apply_exam_total_residual_resolution(
                bank, score,
                {"candidate_source_id": "SRC", "target_section_key": "single_choice", "scope_section_keys": ["single_choice", "cloze"], "total_evidence": {"locator": "src/total", "text_sha256": hashlib.sha256(total_text.encode()).hexdigest()}, "reviewer": "GPT-6 Luna Max", "reviewed_at": "2026-09-28", "review_note": "Synthetic conflict test."},
                source_text_by_locator={
                    "src/total": total_text,
                    "src/choice": bank["sections"][0]["heading"],
                    "src/cloze": bank["sections"][1]["heading"],
                },
            )

    def test_residual_score_can_preserve_exact_fractional_arithmetic(self):
        bank = {
            "source_id": "SRC", "subject": "english",
            "sections": [
                {"section_key": "single_choice", "heading": "[inferred]", "heading_locator": "src/q1", "candidate_count": 5, "inferred": True},
                {"section_key": "cloze", "heading": "II.完形（共2小题，每小题2.5分，满分5分）", "heading_locator": "src/cloze", "candidate_count": 2, "inferred": False},
            ],
        }
        score = build_score_evidence(bank)
        total_text = "第一卷（两大题，共10.75分）"
        resolved = apply_exam_total_residual_resolution(
            bank, score,
            {"candidate_source_id": "SRC", "target_section_key": "single_choice", "scope_section_keys": ["single_choice", "cloze"], "total_evidence": {"locator": "src/total", "text_sha256": hashlib.sha256(total_text.encode()).hexdigest()}, "reviewer": "GPT-6 Luna Max", "reviewed_at": "2026-09-28", "review_note": "Synthetic exact fractional arithmetic test."},
            source_text_by_locator={
                "src/total": total_text,
                "src/q1": "1. example",
                "src/cloze": bank["sections"][1]["heading"],
            },
        )
        jsonschema.validate(resolved, self.schema)
        target = next(x for x in resolved["sections"] if x["section_key"] == "single_choice")
        self.assertEqual(target["per_question_score"], 1.15)


if __name__ == "__main__":
    unittest.main()

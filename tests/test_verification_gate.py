import json
from pathlib import Path
import unittest

import jsonschema

from engine.pipeline.verification import (
    aggregate_pairing_reviews,
    build_verified_candidate_bank,
)

ROOT = Path(__file__).resolve().parents[1]


def review(source, answer, status="ready_for_verification", binding="content_exact"):
    return {
        "schema_version": 1,
        "subject": "english",
        "candidate_source_id": "STUDENT",
        "evidence_source_id": source,
        "source_pair_confidence": "name_exact",
        "rows": [{
            "candidate_id": "Q1",
            "source_number": 1,
            "section_key": "single_choice",
            "candidate_status": "parsed",
            "companion_question_id": f"{source}:Q1",
            "prompt_pair_confidence": "exact",
            "prompt_pair_score": 1.0,
            "prompt_pair_reason": "content_fingerprint",
            "binding_strength": binding,
            "answer_status": "unique" if answer is not None else "missing",
            "normalized_answer": answer,
            "answer_variants": [] if answer is None else [answer],
            "evidence_ids": [] if answer is None else [f"{source}:E1"],
            "review_status": status,
            "review_reasons": [],
            "source_pair_confidence": "name_exact",
            "companion_section_key": "single_choice",
        }],
        "summary": {
            "total": 1,
            "ready_for_verification": 1 if status == "ready_for_verification" else 0,
            "review_required": 1 if status == "review_required" else 0,
            "conflicts": 1 if status == "conflict" else 0,
            "missing_answers": 1 if answer is None else 0,
        },
    }


def candidate_bank(status="parsed"):
    return {
        "source_id": "STUDENT",
        "subject": "english",
        "candidates": [{
            "candidate_id": "Q1",
            "source_id": "STUDENT",
            "subject": "english",
            "source_number": 1,
            "section_key": "single_choice",
            "kind": "single_choice",
            "stem_text": "A fictional prompt.",
            "locators": ["student/1"],
            "status": status,
            "review_reasons": [] if status == "parsed" else ["fixture_review"],
            "options": [
                {"label": "A", "text": "one"},
                {"label": "B", "text": "two"},
                {"label": "C", "text": "three"},
                {"label": "D", "text": "four"},
            ],
        }],
    }


class VerificationGateTests(unittest.TestCase):
    def setUp(self):
        self.aggregate_schema = json.loads(
            (ROOT / "schema/verification-aggregate.schema.json").read_text(encoding="utf-8")
        )
        self.bank_schema = json.loads(
            (ROOT / "schema/verified-candidate-bank.schema.json").read_text(encoding="utf-8")
        )

    def test_two_strong_sources_agree_machine_corroborated(self):
        aggregate = aggregate_pairing_reviews([
            review("TEACHER-A", "B"),
            review("TEACHER-B", "B"),
        ])
        jsonschema.validate(aggregate, self.aggregate_schema)
        row = aggregate["rows"][0]
        self.assertEqual(row["aggregate_status"], "machine_corroborated")
        self.assertEqual(row["normalized_answer"], "B")
        self.assertEqual(
            row["strong_evidence_source_ids"], ["TEACHER-A", "TEACHER-B"]
        )

    def test_two_sources_disagree_conflict(self):
        aggregate = aggregate_pairing_reviews([
            review("TEACHER-A", "A"),
            review("TEACHER-B", "C"),
        ])
        row = aggregate["rows"][0]
        self.assertEqual(row["aggregate_status"], "conflict")
        self.assertIsNone(row["normalized_answer"])
        self.assertEqual(row["answer_variants"], ["A", "C"])

    def test_one_strong_source_is_single_source_consistent(self):
        aggregate = aggregate_pairing_reviews([review("TEACHER-A", "D")])
        self.assertEqual(
            aggregate["rows"][0]["aggregate_status"], "single_source_consistent"
        )

    def test_weak_source_does_not_become_corroborated(self):
        aggregate = aggregate_pairing_reviews([
            review("ANSWER-A", "B", binding="number_only"),
            review("ANSWER-B", "B", binding="number_only"),
        ])
        self.assertEqual(
            aggregate["rows"][0]["aggregate_status"], "review_required"
        )

    def test_machine_corroborated_manifest_can_promote(self):
        aggregate = aggregate_pairing_reviews([
            review("TEACHER-A", "B"),
            review("TEACHER-B", "B"),
        ])
        manifest = {
            "schema_version": 1,
            "candidate_source_id": "STUDENT",
            "decisions": [{
                "candidate_id": "Q1",
                "decision": "approve",
                "method": "machine_corroborated_accepted",
            }],
        }
        bank = build_verified_candidate_bank(candidate_bank(), aggregate, manifest)
        jsonschema.validate(bank, self.bank_schema)
        self.assertEqual(bank["summary"]["verified"], 1)
        self.assertEqual(bank["verified"][0]["verified_answer"], "B")

    def test_machine_method_rejected_for_single_source(self):
        aggregate = aggregate_pairing_reviews([review("TEACHER-A", "B")])
        manifest = {
            "schema_version": 1,
            "candidate_source_id": "STUDENT",
            "decisions": [{
                "candidate_id": "Q1",
                "decision": "approve",
                "method": "machine_corroborated_accepted",
            }],
        }
        with self.assertRaisesRegex(
            ValueError, "requires machine_corroborated aggregate"
        ):
            build_verified_candidate_bank(candidate_bank(), aggregate, manifest)

    def test_ambiguous_candidate_needs_human_review_method(self):
        aggregate = aggregate_pairing_reviews([
            review("TEACHER-A", "A"),
            review("TEACHER-B", "A"),
        ])
        manifest = {
            "schema_version": 1,
            "candidate_source_id": "STUDENT",
            "decisions": [{
                "candidate_id": "Q1",
                "decision": "approve",
                "method": "machine_corroborated_accepted",
            }],
        }
        with self.assertRaisesRegex(ValueError, "requires human_review approval"):
            build_verified_candidate_bank(
                candidate_bank(status="needs_review"), aggregate, manifest
            )

    def test_override_requires_reason(self):
        aggregate = aggregate_pairing_reviews([
            review("TEACHER-A", "B"),
            review("TEACHER-B", "B"),
        ])
        manifest = {
            "schema_version": 1,
            "candidate_source_id": "STUDENT",
            "decisions": [{
                "candidate_id": "Q1",
                "decision": "approve",
                "method": "human_review",
                "verified_answer": "C",
            }],
        }
        with self.assertRaisesRegex(ValueError, "override requires override_reason"):
            build_verified_candidate_bank(candidate_bank(), aggregate, manifest)

    def test_human_override_with_reason_is_recorded(self):
        aggregate = aggregate_pairing_reviews([
            review("TEACHER-A", "B"),
            review("TEACHER-B", "B"),
        ])
        manifest = {
            "schema_version": 1,
            "candidate_source_id": "STUDENT",
            "decisions": [{
                "candidate_id": "Q1",
                "decision": "approve",
                "method": "human_review",
                "verified_answer": "C",
                "override_reason": "Verified against the source during fixture review.",
            }],
        }
        bank = build_verified_candidate_bank(candidate_bank(), aggregate, manifest)
        self.assertEqual(bank["verified"][0]["verified_answer"], "C")
        self.assertIn("source", bank["verified"][0]["override_reason"])

    def test_human_review_can_approve_open_response_writing_without_fake_answer(self):
        aggregate = aggregate_pairing_reviews([review("TEACHER-A", None)])
        bank_input = candidate_bank()
        writing = bank_input["candidates"][0]
        writing["section_key"] = "writing"
        writing["kind"] = "composition"
        writing["options"] = []

        manifest = {
            "schema_version": 1,
            "candidate_source_id": "STUDENT",
            "decisions": [{
                "candidate_id": "Q1",
                "decision": "approve",
                "method": "human_review",
                "answer_mode": "open_response",
                "note": "Writing prompt and source-pair identity reviewed; no unique fixed answer exists.",
            }],
        }
        bank = build_verified_candidate_bank(bank_input, aggregate, manifest)
        jsonschema.validate(bank, self.bank_schema)
        self.assertEqual(bank["summary"]["verified"], 1)
        self.assertEqual(bank["verified"][0]["answer_mode"], "open_response")
        self.assertIsNone(bank["verified"][0]["verified_answer"])

    def test_open_response_mode_is_rejected_for_fixed_answer_question(self):
        aggregate = aggregate_pairing_reviews([review("TEACHER-A", None)])
        manifest = {
            "schema_version": 1,
            "candidate_source_id": "STUDENT",
            "decisions": [{
                "candidate_id": "Q1",
                "decision": "approve",
                "method": "human_review",
                "answer_mode": "open_response",
            }],
        }
        with self.assertRaisesRegex(ValueError, "only valid for writing compositions"):
            build_verified_candidate_bank(candidate_bank(), aggregate, manifest)

    def test_open_response_mode_cannot_hide_fixed_answer_evidence(self):
        aggregate = aggregate_pairing_reviews([review("TEACHER-A", "B")])
        bank_input = candidate_bank()
        writing = bank_input["candidates"][0]
        writing["section_key"] = "writing"
        writing["kind"] = "composition"
        writing["options"] = []

        manifest = {
            "schema_version": 1,
            "candidate_source_id": "STUDENT",
            "decisions": [{
                "candidate_id": "Q1",
                "decision": "approve",
                "method": "human_review",
                "answer_mode": "open_response",
            }],
        }
        with self.assertRaisesRegex(ValueError, "cannot bypass fixed-answer evidence"):
            build_verified_candidate_bank(bank_input, aggregate, manifest)

    def test_manifest_source_must_match(self):
        aggregate = aggregate_pairing_reviews([review("TEACHER-A", "B")])
        manifest = {
            "schema_version": 1,
            "candidate_source_id": "OTHER",
            "decisions": [],
        }
        with self.assertRaisesRegex(ValueError, "manifest source mismatch"):
            build_verified_candidate_bank(candidate_bank(), aggregate, manifest)


if __name__ == "__main__":
    unittest.main()

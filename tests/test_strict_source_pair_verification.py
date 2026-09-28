import unittest

from engine.pipeline.verification import (
    build_strict_source_pair_verification_manifest,
    build_verified_candidate_bank,
)


def fixed_candidate():
    return {
        "candidate_id": "Q1",
        "source_id": "STUDENT",
        "subject": "english",
        "source_number": 1,
        "section_key": "single_choice",
        "kind": "single_choice",
        "stem_text": "A fictional prompt.",
        "options": [
            {"label": "A", "text": "one"},
            {"label": "B", "text": "two"},
            {"label": "C", "text": "three"},
            {"label": "D", "text": "four"},
        ],
        "group_id": None,
        "locators": ["student/1"],
        "status": "parsed",
        "review_reasons": [],
    }


def writing_candidate():
    return {
        "candidate_id": "QW",
        "source_id": "STUDENT",
        "subject": "english",
        "source_number": 56,
        "section_key": "writing",
        "kind": "composition",
        "stem_text": "Write a fictional letter.",
        "options": [],
        "group_id": None,
        "locators": ["student/56"],
        "status": "parsed",
        "review_reasons": [],
    }


def candidate_bank(candidate):
    return {
        "source_id": "STUDENT",
        "subject": "english",
        "candidates": [candidate],
    }


def aggregate(candidate_id, status, answer=None):
    return {
        "schema_version": 1,
        "subject": "english",
        "candidate_source_id": "STUDENT",
        "rows": [{
            "candidate_id": candidate_id,
            "aggregate_status": status,
            "normalized_answer": answer,
            "answer_variants": [] if answer is None else [answer],
            "evidence_source_ids": ["TEACHER"],
            "strong_evidence_source_ids": (
                [] if answer is None else ["TEACHER"]
            ),
            "review_reasons": (
                ["answer_evidence_missing"] if answer is None else []
            ),
        }],
        "summary": {
            "total": 1,
            "machine_corroborated": int(status == "machine_corroborated"),
            "single_source_consistent": int(status == "single_source_consistent"),
            "review_required": int(status == "review_required"),
            "conflicts": int(status == "conflict"),
        },
    }


def pairing_row(
    candidate_id,
    *,
    source_pair_confidence="name_exact",
    binding_strength="content_exact",
    review_status="ready_for_verification",
    answer_status="unique",
    normalized_answer="B",
    prompt_pair_confidence="exact",
    review_reasons=None,
):
    return {
        "candidate_id": candidate_id,
        "source_pair_confidence": source_pair_confidence,
        "binding_strength": binding_strength,
        "review_status": review_status,
        "answer_status": answer_status,
        "normalized_answer": normalized_answer,
        "prompt_pair_confidence": prompt_pair_confidence,
        "review_reasons": list(review_reasons or []),
    }


def pairing_review(row):
    return {
        "schema_version": 1,
        "subject": "english",
        "candidate_source_id": "STUDENT",
        "evidence_source_id": "TEACHER",
        "rows": [row],
    }


class StrictSourcePairVerificationTests(unittest.TestCase):
    def test_name_exact_strong_fixed_answer_can_be_editorially_accepted(self):
        candidate = fixed_candidate()
        bank = candidate_bank(candidate)
        agg = aggregate("Q1", "single_source_consistent", "B")
        manifest = build_strict_source_pair_verification_manifest(
            bank,
            agg,
            [pairing_review(pairing_row("Q1"))],
        )
        decision = manifest["decisions"][0]
        self.assertEqual(decision["decision"], "approve")
        self.assertEqual(decision["method"], "source_pair_evidence_accepted")
        self.assertIn("no human-review claim", decision["note"])

        verified = build_verified_candidate_bank(bank, agg, manifest)
        self.assertEqual(verified["summary"]["verified"], 1)
        self.assertEqual(verified["verified"][0]["verified_answer"], "B")
        self.assertEqual(
            verified["verified"][0]["verification_method"],
            "source_pair_evidence_accepted",
        )

    def test_non_exact_source_pair_stays_deferred(self):
        bank = candidate_bank(fixed_candidate())
        agg = aggregate("Q1", "single_source_consistent", "B")
        manifest = build_strict_source_pair_verification_manifest(
            bank,
            agg,
            [pairing_review(pairing_row(
                "Q1",
                source_pair_confidence="structural_candidate",
            ))],
        )
        self.assertEqual(manifest["decisions"][0]["decision"], "defer")

    def test_name_exact_open_writing_becomes_explicit_open_response(self):
        bank = candidate_bank(writing_candidate())
        agg = aggregate("QW", "review_required", None)
        row = pairing_row(
            "QW",
            binding_strength="content_high",
            review_status="review_required",
            answer_status="missing",
            normalized_answer=None,
            prompt_pair_confidence="high",
            review_reasons=["answer_evidence_missing"],
        )
        manifest = build_strict_source_pair_verification_manifest(
            bank,
            agg,
            [pairing_review(row)],
        )
        decision = manifest["decisions"][0]
        self.assertEqual(decision["decision"], "approve")
        self.assertEqual(decision["method"], "editorial_source_review")
        self.assertEqual(decision["answer_mode"], "open_response")

        verified = build_verified_candidate_bank(bank, agg, manifest)
        self.assertEqual(verified["verified"][0]["answer_mode"], "open_response")
        self.assertIsNone(verified["verified"][0]["verified_answer"])

    def test_open_writing_with_source_discrepancy_stays_deferred(self):
        bank = candidate_bank(writing_candidate())
        agg = aggregate("QW", "review_required", None)
        row = pairing_row(
            "QW",
            binding_strength="content_high",
            review_status="review_required",
            answer_status="missing",
            normalized_answer=None,
            prompt_pair_confidence="high",
            review_reasons=[
                "answer_evidence_missing",
                "writing_prompt_source_discrepancy",
            ],
        )
        manifest = build_strict_source_pair_verification_manifest(
            bank,
            agg,
            [pairing_review(row)],
        )
        self.assertEqual(manifest["decisions"][0]["decision"], "defer")

    def test_source_pair_evidence_method_cannot_bypass_review_required_answer(self):
        bank = candidate_bank(fixed_candidate())
        agg = aggregate("Q1", "review_required", None)
        manifest = {
            "schema_version": 1,
            "candidate_source_id": "STUDENT",
            "decisions": [{
                "candidate_id": "Q1",
                "decision": "approve",
                "method": "source_pair_evidence_accepted",
                "verified_answer": "B",
                "note": "Synthetic provenance note.",
            }],
        }
        with self.assertRaisesRegex(ValueError, "consistent strong evidence"):
            build_verified_candidate_bank(bank, agg, manifest)


if __name__ == "__main__":
    unittest.main()

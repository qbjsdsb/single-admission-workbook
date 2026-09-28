import json
from pathlib import Path
import unittest

import jsonschema

from engine.pipeline.reconcile import reconcile_candidate_and_evidence

ROOT = Path(__file__).resolve().parents[1]


def candidate(qid, number, stem, answer_status="parsed", section="single_choice"):
    return {
        "candidate_id": qid,
        "source_id": "STUDENT",
        "subject": "english",
        "source_number": number,
        "section_key": section,
        "kind": "single_choice",
        "stem_text": stem,
        "locators": [f"student/{number}"],
        "status": answer_status,
        "review_reasons": [] if answer_status == "parsed" else ["fixture_review"],
        "options": [
            {"label": "A", "text": "one"},
            {"label": "B", "text": "two"},
            {"label": "C", "text": "three"},
            {"label": "D", "text": "four"},
        ],
    }


def prompt(pid, number, stem, section="single_choice"):
    return {
        "id": pid,
        "number": number,
        "section_key": section,
        "stem": stem,
        "locators": [f"teacher/{number}"],
        "match_status": "content_available",
        "options": [
            {"label": "A", "text": "one"},
            {"label": "B", "text": "two"},
            {"label": "C", "text": "three"},
            {"label": "D", "text": "four"},
        ],
    }


def evidence(eid, number, value, section="single_choice"):
    return {
        "evidence_id": eid,
        "source_id": "TEACHER",
        "subject": "english",
        "source_number": number,
        "section_key": section,
        "field": "answer",
        "value": value,
        "locator": f"teacher/answer/{eid}",
        "extraction_mode": "explicit_current",
        "status": "extracted",
    }


class PairingReviewTests(unittest.TestCase):
    def setUp(self):
        self.schema = json.loads(
            (ROOT / "schema/pairing-review.schema.json").read_text(encoding="utf-8")
        )

    def test_exact_content_plus_unique_answer_is_ready_for_verification(self):
        cb = {
            "source_id": "STUDENT",
            "subject": "english",
            "candidates": [candidate("Q1", 1, "A fictional prompt.")],
        }
        eb = {
            "source_id": "TEACHER",
            "subject": "english",
            "question_records": [prompt("T1", 1, "A fictional prompt.")],
            "evidence": [evidence("E1", 1, "B")],
        }
        review = reconcile_candidate_and_evidence(cb, eb)
        jsonschema.validate(review, self.schema)
        row = review["rows"][0]
        self.assertEqual(row["prompt_pair_confidence"], "exact")
        self.assertEqual(row["binding_strength"], "content_exact")
        self.assertEqual(row["answer_status"], "unique")
        self.assertEqual(row["normalized_answer"], "B")
        self.assertEqual(row["review_status"], "ready_for_verification")

    def test_answer_only_name_exact_pair_can_reach_verification_queue(self):
        cb = {
            "source_id": "STUDENT",
            "subject": "english",
            "candidates": [candidate("Q1", 1, "A fictional prompt.")],
        }
        eb = {
            "source_id": "ANSWER",
            "subject": "english",
            "question_records": [],
            "evidence": [evidence("E1", 1, "A")],
        }
        review = reconcile_candidate_and_evidence(
            cb, eb, source_pair_confidence="name_exact"
        )
        row = review["rows"][0]
        self.assertEqual(row["prompt_pair_confidence"], "unmatched")
        self.assertEqual(row["binding_strength"], "paired_source_number")
        self.assertEqual(row["review_status"], "ready_for_verification")

    def test_number_only_non_exact_source_pair_remains_review_required(self):
        cb = {
            "source_id": "STUDENT",
            "subject": "english",
            "candidates": [candidate("Q1", 1, "A fictional prompt.")],
        }
        eb = {
            "source_id": "ANSWER",
            "subject": "english",
            "question_records": [],
            "evidence": [evidence("E1", 1, "A")],
        }
        review = reconcile_candidate_and_evidence(
            cb, eb, source_pair_confidence="structural_candidate"
        )
        row = review["rows"][0]
        self.assertEqual(row["binding_strength"], "number_only")
        self.assertEqual(row["review_status"], "review_required")
        self.assertIn("weak_or_missing_evidence_binding", row["review_reasons"])

    def test_conflicting_answers_are_fail_closed(self):
        cb = {
            "source_id": "STUDENT",
            "subject": "english",
            "candidates": [candidate("Q1", 1, "A fictional prompt.")],
        }
        eb = {
            "source_id": "TEACHER",
            "subject": "english",
            "question_records": [prompt("T1", 1, "A fictional prompt.")],
            "evidence": [
                evidence("E1", 1, "A"),
                evidence("E2", 1, "C"),
            ],
        }
        review = reconcile_candidate_and_evidence(cb, eb)
        row = review["rows"][0]
        self.assertEqual(row["answer_status"], "conflict")
        self.assertEqual(row["review_status"], "conflict")
        self.assertEqual(row["answer_variants"], ["A", "C"])

    def test_candidate_review_status_is_not_hidden_by_good_answer(self):
        cb = {
            "source_id": "STUDENT",
            "subject": "english",
            "candidates": [
                candidate("Q1", 1, "A fictional prompt.", answer_status="needs_review")
            ],
        }
        eb = {
            "source_id": "TEACHER",
            "subject": "english",
            "question_records": [prompt("T1", 1, "A fictional prompt.")],
            "evidence": [evidence("E1", 1, "D")],
        }
        review = reconcile_candidate_and_evidence(cb, eb)
        row = review["rows"][0]
        self.assertEqual(row["review_status"], "review_required")
        self.assertIn("candidate_structure_needs_review", row["review_reasons"])

    def test_name_exact_writing_pair_can_use_long_prompt_prefix(self):
        writing = candidate(
            "Q-WRITE",
            None,
            (
                "Write a fictional letter about the school activity. "
                "Mention the time, place, participants, and one preparation detail. "
                "Dear Sam, ______________________________"
            ),
            section="writing",
        )
        writing["kind"] = "composition"
        writing["options"] = []

        teacher_prompt = prompt(
            "T-WRITE",
            56,
            (
                "Write a fictional letter about the school activity. "
                "Mention the time, place, participants, and one preparation detail. "
                "Dear Sam, A fictional model response continues here with extra teacher prose."
            ),
            section="writing",
        )
        teacher_prompt.pop("options")

        cb = {
            "source_id": "STUDENT",
            "subject": "english",
            "candidates": [writing],
        }
        eb = {
            "source_id": "TEACHER",
            "subject": "english",
            "question_records": [teacher_prompt],
            "evidence": [],
        }
        review = reconcile_candidate_and_evidence(
            cb,
            eb,
            source_pair_confidence="name_exact",
        )
        jsonschema.validate(review, self.schema)
        row = review["rows"][0]
        self.assertEqual(row["prompt_pair_confidence"], "high")
        self.assertEqual(row["prompt_pair_reason"], "name_exact_writing_prompt_prefix")
        self.assertGreaterEqual(row["prompt_pair_score"], 0.80)
        self.assertEqual(row["binding_strength"], "content_high")
        self.assertEqual(row["companion_source_number"], 56)
        self.assertEqual(row["answer_status"], "missing")
        self.assertEqual(row["review_status"], "review_required")

    def test_writing_prefix_fallback_requires_exact_source_pair(self):
        writing = candidate(
            "Q-WRITE",
            None,
            (
                "Write a fictional letter about the school activity. "
                "Mention the time, place, participants, and one preparation detail. "
                "Dear Sam, ______________________________"
            ),
            section="writing",
        )
        writing["kind"] = "composition"
        writing["options"] = []
        teacher_prompt = prompt(
            "T-WRITE",
            56,
            (
                "Write a fictional letter about the school activity. "
                "Mention the time, place, participants, and one preparation detail. "
                "Dear Sam, A fictional model response continues here with extra teacher prose."
            ),
            section="writing",
        )
        teacher_prompt.pop("options")
        cb = {"source_id": "STUDENT", "subject": "english", "candidates": [writing]}
        eb = {
            "source_id": "TEACHER",
            "subject": "english",
            "question_records": [teacher_prompt],
            "evidence": [],
        }
        review = reconcile_candidate_and_evidence(
            cb,
            eb,
            source_pair_confidence="structural_candidate",
        )
        row = review["rows"][0]
        self.assertEqual(row["prompt_pair_confidence"], "unmatched")
        self.assertEqual(row["binding_strength"], "none")

    def test_missing_answer_is_review_required_even_when_prompt_matches(self):
        cb = {
            "source_id": "STUDENT",
            "subject": "english",
            "candidates": [candidate("Q1", 1, "A fictional prompt.")],
        }
        eb = {
            "source_id": "TEACHER",
            "subject": "english",
            "question_records": [prompt("T1", 1, "A fictional prompt.")],
            "evidence": [],
        }
        review = reconcile_candidate_and_evidence(cb, eb)
        row = review["rows"][0]
        self.assertEqual(row["answer_status"], "missing")
        self.assertEqual(row["review_status"], "review_required")
        self.assertEqual(review["summary"]["missing_answers"], 1)


if __name__ == "__main__":
    unittest.main()

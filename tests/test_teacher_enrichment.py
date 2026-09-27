import json
from pathlib import Path
import unittest

import jsonschema

from engine.pipeline.teacher_enrichment import build_teacher_enrichment

ROOT = Path(__file__).resolve().parents[1]


def review(binding="content_exact", status="ready_for_verification"):
    return {
        "schema_version": 1,
        "subject": "english",
        "candidate_source_id": "STUDENT",
        "evidence_source_id": "TEACHER",
        "source_pair_confidence": "name_exact",
        "rows": [{
            "candidate_id": "Q1",
            "source_number": 1,
            "section_key": "single_choice",
            "candidate_status": "parsed",
            "companion_question_id": "T1",
            "prompt_pair_confidence": "exact",
            "prompt_pair_score": 1.0,
            "prompt_pair_reason": "content_fingerprint",
            "binding_strength": binding,
            "answer_status": "unique",
            "normalized_answer": "B",
            "answer_variants": ["B"],
            "evidence_ids": ["E-ANSWER"],
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
            "missing_answers": 0,
        },
    }


def evidence_bank():
    return {
        "schema_version": 1,
        "source_id": "TEACHER",
        "subject": "english",
        "question_records": [],
        "evidence": [
            {
                "evidence_id": "E-ANSWER",
                "source_id": "TEACHER",
                "subject": "english",
                "source_number": 1,
                "section_key": "single_choice",
                "field": "answer",
                "value": "B",
                "locator": "teacher/1/answer",
                "extraction_mode": "explicit_current",
                "status": "extracted",
            },
            {
                "evidence_id": "E-A1",
                "source_id": "TEACHER",
                "subject": "english",
                "source_number": 1,
                "section_key": "single_choice",
                "field": "analysis",
                "value": "First reviewed analysis paragraph.",
                "locator": "teacher/1/analysis/1",
                "extraction_mode": "explicit_current",
                "status": "extracted",
            },
            {
                "evidence_id": "E-A2",
                "source_id": "TEACHER",
                "subject": "english",
                "source_number": 1,
                "section_key": "single_choice",
                "field": "analysis",
                "value": "Second reviewed analysis paragraph.",
                "locator": "teacher/1/analysis/2",
                "extraction_mode": "explicit_current",
                "status": "extracted",
            },
            {
                "evidence_id": "E-N1",
                "source_id": "TEACHER",
                "subject": "english",
                "source_number": 1,
                "section_key": "single_choice",
                "field": "teacher_notes",
                "value": "Teaching focus.",
                "locator": "teacher/1/note",
                "extraction_mode": "explicit_current",
                "status": "extracted",
            },
        ],
        "blockers": [],
        "summary": {},
    }


class TeacherEnrichmentTests(unittest.TestCase):
    def setUp(self):
        self.schema = json.loads(
            (ROOT / "schema/teacher-enrichment-batch.schema.json").read_text(encoding="utf-8")
        )

    def test_strong_binding_collects_analysis_and_notes(self):
        result = build_teacher_enrichment(review(), evidence_bank())
        jsonschema.validate(result, self.schema)
        self.assertEqual(result["summary"], {"enriched": 1, "unresolved": 0})
        item = result["items"][0]
        self.assertIn("First reviewed", item["analysis"])
        self.assertIn("Second reviewed", item["analysis"])
        self.assertLess(
            item["analysis"].index("First reviewed"),
            item["analysis"].index("Second reviewed"),
        )
        self.assertEqual(item["teacher_notes"], "Teaching focus.")

    def test_number_only_binding_does_not_auto_enrich(self):
        result = build_teacher_enrichment(
            review(binding="number_only", status="review_required"),
            evidence_bank(),
        )
        self.assertEqual(result["summary"]["enriched"], 0)
        self.assertEqual(result["unresolved"][0]["reason"], "weak_evidence_binding")

    def test_conflict_does_not_auto_enrich(self):
        result = build_teacher_enrichment(
            review(status="conflict"),
            evidence_bank(),
        )
        self.assertEqual(result["summary"]["enriched"], 0)
        self.assertEqual(
            result["unresolved"][0]["reason"], "pairing_or_answer_conflict"
        )

    def test_source_identity_must_match(self):
        bank = evidence_bank()
        bank["source_id"] = "OTHER"
        with self.assertRaisesRegex(ValueError, "source mismatch"):
            build_teacher_enrichment(review(), bank)


if __name__ == "__main__":
    unittest.main()

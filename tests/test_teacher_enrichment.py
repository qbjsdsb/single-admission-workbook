import json
import hashlib
from pathlib import Path
import unittest

import jsonschema

from engine.pipeline.teacher_enrichment import (
    apply_reviewed_analysis_supplements,
    build_teacher_enrichment,
)

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

    def test_open_composition_keeps_source_sample_with_paragraph_provenance(self):
        p1 = "Dear Mark,"
        p2 = "A fictional sample paragraph."
        evidence = []
        for index, value in enumerate((p1, p2), start=1):
            digest = hashlib.sha256(value.encode()).hexdigest()
            evidence.append({
                "evidence_id": f"E-SAMPLE-{index}",
                "source_id": "TEACHER",
                "subject": "english",
                "source_number": 56,
                "section_key": "writing",
                "field": "source_sample_response",
                "value": value,
                "locator": f"word/document.xml/body/{index}",
                "extraction_mode": "explicit_sample_response",
                "status": "extracted",
                "value_sha256": digest,
            })
        pairing = review()
        pairing["rows"][0].update({
            "candidate_id": "Q1",
            "candidate_kind": "composition",
            "source_number": 56,
            "section_key": "writing",
            "candidate_status": "parsed",
            "binding_strength": "paired_source_number",
            "source_pair_confidence": "name_exact",
            "review_status": "review_required",
            "evidence_ids": [],
            "source_sample_response_evidence_ids": ["E-SAMPLE-1", "E-SAMPLE-2"],
        })
        bank = {
            "schema_version": 1,
            "source_id": "TEACHER",
            "source_sha256": "b" * 64,
            "subject": "english",
            "question_records": [],
            "evidence": evidence,
            "blockers": [],
            "summary": {},
        }

        result = build_teacher_enrichment(pairing, bank)
        jsonschema.validate(result, self.schema)
        item = result["items"][0]
        self.assertEqual(item["source_sample_response"], f"{p1}\n{p2}")
        self.assertNotIn("analysis", item)
        self.assertEqual(
            item["source_sample_response_provenance"]["evidence_ids"],
            ["E-SAMPLE-1", "E-SAMPLE-2"],
        )
        self.assertEqual(
            item["source_sample_response_provenance"]["source_sha256"], "b" * 64
        )

    def test_conflict_does_not_auto_enrich(self):
        result = build_teacher_enrichment(
            review(status="conflict"),
            evidence_bank(),
        )
        self.assertEqual(result["summary"]["enriched"], 0)
        self.assertEqual(
            result["unresolved"][0]["reason"], "pairing_or_answer_conflict"
        )

    def test_reviewed_generated_analysis_fills_only_missing_source_analysis(self):
        merged = {
            "schema_version": 1,
            "candidate_source_id": "STUDENT",
            "items": [
                {"candidate_id": "Q1", "teacher_notes": "Existing source note."},
                {"candidate_id": "Q2", "analysis": "Existing source analysis."},
            ],
        }
        supplement = {
            "schema_version": 1,
            "candidate_source_id": "STUDENT",
            "items": [
                {
                    "candidate_id": "Q1",
                    "analysis": "Reviewed generated explanation.",
                    "origin": "generated",
                    "decision": "approve",
                    "review_note": "Checked against the question and verified answer.",
                },
                {
                    "candidate_id": "Q3",
                    "analysis": "Draft not yet approved.",
                    "origin": "generated",
                    "decision": "defer",
                },
            ],
        }
        result = apply_reviewed_analysis_supplements(
            merged,
            supplement,
            known_candidate_ids={"Q1", "Q2", "Q3"},
        )
        by_id = {item["candidate_id"]: item for item in result["items"]}
        self.assertEqual(by_id["Q1"]["analysis"], "Reviewed generated explanation.")
        self.assertEqual(by_id["Q1"]["teacher_notes"], "Existing source note.")
        self.assertEqual(by_id["Q2"]["analysis"], "Existing source analysis.")
        self.assertNotIn("Q3", by_id)

    def test_supplement_never_overwrites_different_source_analysis(self):
        merged = {
            "schema_version": 1,
            "candidate_source_id": "STUDENT",
            "items": [{"candidate_id": "Q1", "analysis": "Source analysis."}],
        }
        supplement = {
            "schema_version": 1,
            "candidate_source_id": "STUDENT",
            "items": [{
                "candidate_id": "Q1",
                "analysis": "Generated replacement.",
                "origin": "generated",
                "decision": "approve",
                "review_note": "Reviewed.",
            }],
        }
        with self.assertRaisesRegex(ValueError, "cannot overwrite source teacher analysis"):
            apply_reviewed_analysis_supplements(
                merged,
                supplement,
                known_candidate_ids={"Q1"},
            )

    def test_approved_supplement_requires_known_candidate(self):
        supplement = {
            "schema_version": 1,
            "candidate_source_id": "STUDENT",
            "items": [{
                "candidate_id": "UNKNOWN",
                "analysis": "Reviewed generated explanation.",
                "origin": "generated",
                "decision": "approve",
                "review_note": "Reviewed.",
            }],
        }
        with self.assertRaisesRegex(ValueError, "unknown candidate"):
            apply_reviewed_analysis_supplements(
                None,
                supplement,
                known_candidate_ids={"Q1"},
            )

    def test_source_identity_must_match(self):
        bank = evidence_bank()
        bank["source_id"] = "OTHER"
        with self.assertRaisesRegex(ValueError, "source mismatch"):
            build_teacher_enrichment(review(), bank)


if __name__ == "__main__":
    unittest.main()

import json
from pathlib import Path
import unittest

import jsonschema

from engine.pipeline.editorial_queue import build_editorial_queue

ROOT = Path(__file__).resolve().parents[1]


def candidate(qid, number, status="parsed", section="single_choice"):
    return {
        "candidate_id": qid,
        "source_id": "SRC",
        "subject": "english",
        "source_number": number,
        "section_key": section,
        "kind": "single_choice",
        "stem_text": f"Fictional prompt {number}.",
        "locators": [f"src/{number}"],
        "status": status,
        "review_reasons": [] if status == "parsed" else ["fixture_structure"],
        "options": [
            {"label": "A", "text": "one"},
            {"label": "B", "text": "two"},
            {"label": "C", "text": "three"},
            {"label": "D", "text": "four"},
        ],
    }


def aggregate_row(qid, status="machine_corroborated", answer="B"):
    return {
        "candidate_id": qid,
        "aggregate_status": status,
        "normalized_answer": None if status == "conflict" else answer,
        "answer_variants": ["A", "C"] if status == "conflict" else [answer],
        "evidence_source_ids": ["T1", "T2"],
        "strong_evidence_source_ids": ["T1", "T2"],
        "review_reasons": [],
    }


def score(status="usable"):
    return {
        "section_key": "single_choice",
        "heading": "I.单项选择（共4小题，每小题2分，满分8分）",
        "candidate_count": 4,
        "declared_count": 4,
        "per_question_score": 2.0 if status != "incomplete" else None,
        "full_score": 8.0,
        "per_question_source": "explicit" if status != "incomplete" else None,
        "full_score_source": "explicit",
        "status": status,
        "reasons": ["fixture conflict"] if status == "conflict" else [],
    }


def classification(qid, decision="assign"):
    item = {"candidate_id": qid, "decision": decision}
    if decision == "assign":
        item.update({
            "chapter_key": "grammar",
            "section_key": "verb",
            "tags": ["动词"],
            "difficulty": "standard",
        })
    else:
        item["note"] = "semantic_classification_required"
    return item


def verified_bank(ids):
    return {
        "schema_version": 1,
        "subject": "english",
        "candidate_source_id": "SRC",
        "verified": [
            {
                "candidate_id": qid,
                "source_id": "SRC",
                "subject": "english",
                "source_number": int(qid[-1]),
                "section_key": "single_choice",
                "kind": "single_choice",
                "stem_text": "fixture",
                "options": [],
                "group_id": None,
                "locators": [],
                "verified_answer": "B",
                "verification_method": "human_review",
                "verification_note": "",
                "override_reason": "",
                "machine_aggregate_status": "machine_corroborated",
                "machine_answer": "B",
            }
            for qid in ids
        ],
        "rejected_candidate_ids": [],
        "deferred_candidate_ids": [],
        "summary": {"verified": len(ids), "rejected": 0, "deferred": 0},
    }


def enrichment(ids):
    return {
        "schema_version": 1,
        "candidate_source_id": "SRC",
        "evidence_source_id": "TEACHER",
        "items": [
            {"candidate_id": qid, "analysis": "Reviewed analysis."}
            for qid in ids
        ],
        "unresolved": [],
        "summary": {"enriched": len(ids), "unresolved": 0},
    }


class EditorialQueueTests(unittest.TestCase):
    def setUp(self):
        self.schema = json.loads(
            (ROOT / "schema/editorial-queue.schema.json").read_text(encoding="utf-8")
        )

    def test_queue_prioritizes_conflicts_then_review_then_ready(self):
        candidate_bank = {
            "source_id": "SRC",
            "subject": "english",
            "candidates": [
                candidate("Q1", 1),
                candidate("Q2", 2, status="needs_review"),
                candidate("Q3", 3),
            ],
        }
        aggregate = {
            "candidate_source_id": "SRC",
            "subject": "english",
            "rows": [
                aggregate_row("Q1", status="conflict"),
                aggregate_row("Q2"),
                aggregate_row("Q3"),
            ],
        }
        score_evidence = {
            "candidate_source_id": "SRC",
            "subject": "english",
            "sections": [score()],
        }
        manifest = {
            "candidate_source_id": "SRC",
            "subject": "english",
            "decisions": [
                classification("Q1"),
                classification("Q2"),
                classification("Q3"),
            ],
        }

        queue = build_editorial_queue(
            candidate_bank,
            aggregate,
            score_evidence,
            manifest,
            verified_candidate_bank=verified_bank(["Q2", "Q3"]),
            teacher_enrichment=enrichment(["Q1", "Q2", "Q3"]),
        )
        jsonschema.validate(queue, self.schema)

        by_id = {x["candidate_id"]: x for x in queue["entries"]}
        self.assertEqual(by_id["Q1"]["state"], "blocked")
        self.assertEqual(by_id["Q1"]["priority"], 0)
        self.assertEqual(by_id["Q1"]["next_action"], "resolve_answer_conflict")

        self.assertEqual(by_id["Q2"]["state"], "needs_review")
        self.assertEqual(by_id["Q2"]["priority"], 1)
        self.assertEqual(by_id["Q2"]["next_action"], "review_source_structure")

        self.assertEqual(by_id["Q3"]["state"], "ready_for_sample")
        self.assertEqual(by_id["Q3"]["priority"], 9)
        self.assertEqual(by_id["Q3"]["issues"], [])

    def test_machine_corroboration_without_verification_manifest_is_not_ready(self):
        candidate_bank = {
            "source_id": "SRC",
            "subject": "english",
            "candidates": [candidate("Q1", 1)],
        }
        queue = build_editorial_queue(
            candidate_bank,
            {
                "candidate_source_id": "SRC",
                "subject": "english",
                "rows": [aggregate_row("Q1")],
            },
            {
                "candidate_source_id": "SRC",
                "subject": "english",
                "sections": [score()],
            },
            {
                "candidate_source_id": "SRC",
                "subject": "english",
                "decisions": [classification("Q1")],
            },
            teacher_enrichment=enrichment(["Q1"]),
        )
        entry = queue["entries"][0]
        self.assertEqual(entry["state"], "needs_review")
        self.assertTrue(any(
            issue["code"] == "answer_verification"
            for issue in entry["issues"]
        ))

    def test_rich_content_blocker_on_shared_material_reaches_every_child(self):
        q1 = candidate("Q1", 1)
        q1["group_id"] = "G1"
        candidate_bank = {
            "source_id": "SRC",
            "subject": "english",
            "candidates": [q1],
            "groups": [{"group_id": "G1", "locators": ["src/shared-table"]}],
            "blockers": [{
                "locator": "src/shared-table",
                "reasons": ["unsupported_table_feature:drawing"],
            }],
        }
        queue = build_editorial_queue(
            candidate_bank,
            {"candidate_source_id": "SRC", "subject": "english", "rows": [aggregate_row("Q1")]},
            {"candidate_source_id": "SRC", "subject": "english", "sections": [score()]},
            {"candidate_source_id": "SRC", "subject": "english", "decisions": [classification("Q1")]},
            verified_candidate_bank=verified_bank(["Q1"]),
            teacher_enrichment=enrichment(["Q1"]),
        )
        jsonschema.validate(queue, self.schema)
        entry = queue["entries"][0]
        self.assertEqual(entry["state"], "needs_review")
        issue = next(issue for issue in entry["issues"] if issue["code"] == "rich_content")
        self.assertIn("unsupported_table_feature:drawing", issue["detail"])

    def test_score_conflict_is_blocking(self):
        candidate_bank = {
            "source_id": "SRC",
            "subject": "english",
            "candidates": [candidate("Q1", 1)],
        }
        queue = build_editorial_queue(
            candidate_bank,
            {
                "candidate_source_id": "SRC",
                "subject": "english",
                "rows": [aggregate_row("Q1")],
            },
            {
                "candidate_source_id": "SRC",
                "subject": "english",
                "sections": [score(status="conflict")],
            },
            {
                "candidate_source_id": "SRC",
                "subject": "english",
                "decisions": [classification("Q1")],
            },
            verified_candidate_bank=verified_bank(["Q1"]),
            teacher_enrichment=enrichment(["Q1"]),
        )
        entry = queue["entries"][0]
        self.assertEqual(entry["state"], "blocked")
        self.assertTrue(any(
            issue["code"] == "score_conflict"
            for issue in entry["issues"]
        ))

    def test_deferred_classification_and_missing_analysis_are_both_visible(self):
        candidate_bank = {
            "source_id": "SRC",
            "subject": "english",
            "candidates": [candidate("Q1", 1)],
        }
        queue = build_editorial_queue(
            candidate_bank,
            {
                "candidate_source_id": "SRC",
                "subject": "english",
                "rows": [aggregate_row("Q1")],
            },
            {
                "candidate_source_id": "SRC",
                "subject": "english",
                "sections": [score()],
            },
            {
                "candidate_source_id": "SRC",
                "subject": "english",
                "decisions": [classification("Q1", decision="defer")],
            },
            verified_candidate_bank=verified_bank(["Q1"]),
        )
        codes = {x["code"] for x in queue["entries"][0]["issues"]}
        self.assertEqual(codes, {"classification", "teacher_analysis"})
        self.assertEqual(queue["entries"][0]["priority"], 2)

    def test_source_identity_mismatch_fails_closed(self):
        candidate_bank = {
            "source_id": "SRC",
            "subject": "english",
            "candidates": [candidate("Q1", 1)],
        }
        with self.assertRaisesRegex(ValueError, "aggregate review source mismatch"):
            build_editorial_queue(
                candidate_bank,
                {"candidate_source_id": "OTHER", "subject": "english", "rows": []},
                {"candidate_source_id": "SRC", "subject": "english", "sections": []},
                {"candidate_source_id": "SRC", "subject": "english", "decisions": []},
            )


if __name__ == "__main__":
    unittest.main()

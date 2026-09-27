import csv
import json
from pathlib import Path
import tempfile
import unittest

from engine.pipeline.production_snapshot import (
    build_production_snapshot,
    render_production_snapshot_markdown,
)


class ProductionSnapshotTests(unittest.TestCase):
    def _fixture(self, root: Path):
        summary = {
            "schema_version": 1,
            "subject": "english",
            "student_source_groups": 2,
            "companion_sources": 2,
            "candidate_units": 4,
            "failed_student_groups": 0,
            "states": {
                "blocked": 1,
                "needs_review": 2,
                "ready_for_sample": 1,
            },
            "issue_counts": {
                "answer_conflict": 1,
                "candidate_structure": 1,
                "teacher_analysis": 1,
            },
            "verification_aggregate_counts": {
                "conflict": 1,
                "single_source_consistent": 3,
            },
            "status": "review_only_not_verified_or_publishable",
        }
        (root / "batch-summary.json").write_text(
            json.dumps(summary),
            encoding="utf-8",
        )

        with (root / "editorial-queue.csv").open(
            "w",
            encoding="utf-8-sig",
            newline="",
        ) as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "student_source_id",
                    "student_path",
                    "priority",
                    "state",
                    "source_number",
                    "section_key",
                    "candidate_id",
                    "next_action",
                    "issue_codes",
                    "details",
                ],
            )
            writer.writeheader()
            writer.writerows([
                {
                    "student_source_id": "SRC-A",
                    "student_path": "private/a.docx",
                    "priority": 0,
                    "state": "blocked",
                    "source_number": 1,
                    "section_key": "single_choice",
                    "candidate_id": "A1",
                    "next_action": "resolve_answer_conflict",
                    "issue_codes": "answer_conflict|teacher_analysis",
                    "details": "private detail",
                },
                {
                    "student_source_id": "SRC-A",
                    "student_path": "private/a.docx",
                    "priority": 3,
                    "state": "needs_review",
                    "source_number": 2,
                    "section_key": "single_choice",
                    "candidate_id": "A2",
                    "next_action": "review_teacher_analysis",
                    "issue_codes": "teacher_analysis",
                    "details": "private detail",
                },
                {
                    "student_source_id": "SRC-B",
                    "student_path": "private/b.docx",
                    "priority": 1,
                    "state": "needs_review",
                    "source_number": 1,
                    "section_key": "single_choice",
                    "candidate_id": "B1",
                    "next_action": "review_source_structure",
                    "issue_codes": "candidate_structure",
                    "details": "private detail",
                },
                {
                    "student_source_id": "SRC-B",
                    "student_path": "private/b.docx",
                    "priority": 9,
                    "state": "ready_for_sample",
                    "source_number": 2,
                    "section_key": "single_choice",
                    "candidate_id": "B2",
                    "next_action": "no_action",
                    "issue_codes": "",
                    "details": "",
                },
            ])

    def test_snapshot_prioritizes_blockers_without_exposing_paths(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._fixture(root)
            snapshot = build_production_snapshot(root)

            self.assertEqual(snapshot["candidate_units"], 4)
            self.assertEqual(snapshot["priority_counts"]["P0"], 1)
            self.assertEqual(snapshot["priority_counts"]["P1"], 1)
            self.assertEqual(snapshot["priority_counts"]["P3"], 1)
            self.assertEqual(snapshot["next_source_ids"][0], "SRC-A")
            self.assertEqual(snapshot["sources"][0]["next_priority"], "P0")
            self.assertNotIn("private/a.docx", json.dumps(snapshot))

            markdown = render_production_snapshot_markdown(snapshot)
            self.assertIn("ready for sample: 1", markdown)
            self.assertIn("answer_conflict: 1", markdown)
            self.assertNotIn("private/a.docx", markdown)

    def test_queue_count_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._fixture(root)
            summary = json.loads(
                (root / "batch-summary.json").read_text(encoding="utf-8")
            )
            summary["candidate_units"] = 5
            (root / "batch-summary.json").write_text(
                json.dumps(summary),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "candidate count mismatch"):
                build_production_snapshot(root)


if __name__ == "__main__":
    unittest.main()

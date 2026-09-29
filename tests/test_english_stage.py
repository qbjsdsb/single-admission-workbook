import json
from pathlib import Path
import tempfile
import unittest

from engine.pipeline.english_stage import (
    assemble_english_stage_canonical,
    curriculum_from_english_taxonomy,
    deduplicate_stage_questions,
)


def canonical_question(qid, answer="B", *, analysis=True):
    question = {
        "id": qid,
        "subject": "english",
        "kind": "single_choice",
        "score": 2.0,
        "stem": [{"type": "text", "text": "A fictional English prompt."}],
        "options": [
            {"label": "A", "content": [{"type": "text", "text": "one"}]},
            {"label": "B", "content": [{"type": "text", "text": "two"}]},
            {"label": "C", "content": [{"type": "text", "text": "three"}]},
            {"label": "D", "content": [{"type": "text", "text": "four"}]},
        ],
        "answer": answer,
        "chapter_key": "grammar",
        "section_key": "mixed_choice",
        "difficulty": "standard",
        "layout": {"choice_mode": "auto", "keep_together": True},
    }
    if analysis:
        question["analysis"] = [
            {"type": "text", "text": "A source-derived fictional explanation."}
        ]
    return question


class EnglishStageTests(unittest.TestCase):
    def test_curriculum_comes_from_named_taxonomy(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "english.yaml"
            path.write_text(
                """
version: 1
subject: english
chapters:
  - key: grammar
    title: 语法
    sections:
      - {key: mixed_choice, title: 单项选择综合训练}
""".strip(),
                encoding="utf-8",
            )
            curriculum = curriculum_from_english_taxonomy(path)
            self.assertEqual(curriculum["english"][0]["title"], "语法")
            self.assertEqual(
                curriculum["english"][0]["sections"][0]["title"],
                "单项选择综合训练",
            )

    def test_exact_duplicate_keeps_richer_representative(self):
        weak = canonical_question("ENG_WEAK", analysis=False)
        rich = canonical_question("ENG_RICH", analysis=True)
        kept, records, conflicts = deduplicate_stage_questions([weak, rich])
        self.assertEqual([q["id"] for q in kept], ["ENG_RICH"])
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["representative_question_id"], "ENG_RICH")
        self.assertEqual(conflicts, [])

    def test_exact_duplicate_answer_conflict_is_quarantined(self):
        left = canonical_question("ENG_LEFT", answer="A")
        right = canonical_question("ENG_RIGHT", answer="B")
        kept, records, conflicts = deduplicate_stage_questions([left, right])
        self.assertEqual(kept, [])
        self.assertEqual(records, [])
        self.assertEqual(conflicts[0]["reason"], "exact_duplicate_answer_conflict")

    def _write_group(self, review: Path, verified: Path, source: str, candidate_id: str):
        rdir = review / source
        vdir = verified / source
        rdir.mkdir(parents=True)
        vdir.mkdir(parents=True)

        candidate = {
            "schema_version": 1,
            "source_id": source,
            "subject": "english",
            "candidates": [{
                "candidate_id": candidate_id,
                "source_id": source,
                "subject": "english",
                "source_number": 1,
                "section_key": "single_choice",
                "kind": "single_choice",
                "stem_text": "A fictional unique prompt for stage assembly.",
                "options": [
                    {"label": "A", "text": "one"},
                    {"label": "B", "text": "two"},
                    {"label": "C", "text": "three"},
                    {"label": "D", "text": "four"},
                ],
                "group_id": None,
                "locators": ["body/1"],
                "status": "parsed",
                "review_reasons": [],
            }],
            "groups": [],
        }
        classification = {
            "schema_version": 1,
            "candidate_source_id": source,
            "subject": "english",
            "decisions": [{
                "candidate_id": candidate_id,
                "decision": "assign",
                "chapter_key": "grammar",
                "section_key": "mixed_choice",
                "tags": ["单项选择", "综合训练"],
                "difficulty": "standard",
                "note": "broad_source_section_fallback",
            }],
        }
        teacher = {
            "schema_version": 1,
            "candidate_source_id": source,
            "items": [{
                "candidate_id": candidate_id,
                "analysis": "A source-derived fictional explanation for this prompt.",
            }],
        }
        scored = {
            "schema_version": 1,
            "subject": "english",
            "candidate_source_id": source,
            "assigned": [{
                "candidate_id": candidate_id,
                "source_id": source,
                "subject": "english",
                "source_number": 1,
                "section_key": "single_choice",
                "kind": "single_choice",
                "stem_text": "A fictional unique prompt for stage assembly.",
                "options": [
                    {"label": "A", "text": "one"},
                    {"label": "B", "text": "two"},
                    {"label": "C", "text": "three"},
                    {"label": "D", "text": "four"},
                ],
                "group_id": None,
                "locators": ["body/1"],
                "verified_answer": "B",
                "answer_mode": "fixed",
                "verification_method": "source_pair_evidence_accepted",
                "verification_note": "Paired source evidence agrees; no truth-verification claim.",
                "override_reason": "",
                "machine_aggregate_status": "single_source_consistent",
                "machine_answer": "B",
                "score": 2.0,
                "score_source": "explicit",
            }],
            "unresolved": [],
            "summary": {"assigned": 1, "unresolved": 0},
        }

        for path, value in (
            (rdir / "candidate-bank.json", candidate),
            (rdir / "classification-manifest.json", classification),
            (rdir / "teacher-enrichment.json", teacher),
            (vdir / "scored-verified-bank.json", scored),
        ):
            path.write_text(json.dumps(value), encoding="utf-8")

    def test_assembly_uses_post_verification_pool_not_editorial_queue_state(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            review = root / "review"
            verified = root / "verified"
            review.mkdir()
            verified.mkdir()
            self._write_group(
                review,
                verified,
                "SRC-A",
                "SRC-A:q:1:abcd1234",
            )

            canonical, report = assemble_english_stage_canonical(review, verified)
            self.assertEqual(canonical["summary"]["promoted"], 1)
            self.assertEqual(report["canonical_question_groups"], 1)
            self.assertEqual(
                report["verification_methods"]["source_pair_evidence_accepted"],
                1,
            )


if __name__ == "__main__":
    unittest.main()

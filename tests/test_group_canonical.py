import copy
import json
from pathlib import Path
import unittest

import jsonschema

from engine.pipeline.canonical_promotion import promote_to_canonical_draft
from engine.pipeline.sample_selection import select_sample_questions
from engine.render.latex import render_body
from engine.quality.dedup import exact_duplicate_clusters

ROOT = Path(__file__).resolve().parents[1]


def assigned(candidate_id, number, answer):
    return {
        "candidate_id": candidate_id,
        "source_id": "ENG-SOURCE",
        "subject": "english",
        "source_number": number,
        "section_key": "cloze",
        "kind": "single_choice",
        "stem_text": f"Choose the best word for blank {number}.",
        "options": [
            {"label": "A", "text": "one"},
            {"label": "B", "text": "two"},
            {"label": "C", "text": "three"},
            {"label": "D", "text": "four"},
        ],
        "group_id": "ENG-SOURCE:group:fixture",
        "locators": [f"word/document.xml/body/{number}"],
        "verified_answer": answer,
        "verification_method": "human_review",
        "verification_note": "",
        "override_reason": "",
        "machine_aggregate_status": "single_source_consistent",
        "machine_answer": answer,
        "score": 2.0,
        "score_source": "explicit",
    }


def classification(candidate_id, section="cloze_training"):
    return {
        "candidate_id": candidate_id,
        "decision": "assign",
        "chapter_key": "cloze",
        "section_key": section,
        "tags": ["完形填空"],
        "difficulty": "standard",
    }


class GroupCanonicalTests(unittest.TestCase):
    def setUp(self):
        self.question_schema = json.loads(
            (ROOT / "schema/question.schema.json").read_text(encoding="utf-8")
        )
        self.curriculum = {
            "english": [
                {
                    "key": "cloze",
                    "title": "完形填空",
                    "sections": [
                        {"key": "cloze_training", "title": "完形填空专项训练"}
                    ],
                }
            ]
        }

    def _promote(self, *, missing_second=False, mismatch=False):
        assigned_items = [assigned("C1", 21, "A")]
        if not missing_second:
            assigned_items.append(assigned("C2", 22, "B"))
        scored = {
            "subject": "english",
            "candidate_source_id": "ENG-SOURCE",
            "assigned": assigned_items,
        }
        manifest = {
            "candidate_source_id": "ENG-SOURCE",
            "subject": "english",
            "decisions": [
                classification("C1"),
                classification("C2", "other_section" if mismatch else "cloze_training"),
            ],
        }
        candidate_bank = {
            "source_id": "ENG-SOURCE",
            "subject": "english",
            "groups": [{
                "group_id": "ENG-SOURCE:group:fixture",
                "kind": "cloze_group",
                "section_key": "cloze",
                "label": None,
                "shared_material_text": "A fictional passage with two blanks.",
                "shared_material_rich": [
                    {"type": "text", "text": "A fictional passage with two blanks."},
                    {"type": "table", "rows": [{"cells": [
                        {"text": "Day", "grid_span": 1},
                        {"text": "Activity", "grid_span": 1},
                    ]}]},
                ],
                "locators": ["word/document.xml/body/100"],
                "child_candidate_ids": ["C1", "C2"],
            }],
        }
        enrichment = {
            "candidate_source_id": "ENG-SOURCE",
            "items": [
                {"candidate_id": "C1", "analysis": "Reviewed explanation one."},
                {"candidate_id": "C2", "analysis": "Reviewed explanation two."},
            ],
        }
        return promote_to_canonical_draft(
            scored,
            manifest,
            teacher_enrichment=enrichment,
            candidate_bank=candidate_bank,
        )

    def test_cloze_group_promotes_atomically_with_shared_material_once(self):
        draft = self._promote()
        self.assertEqual(draft["summary"], {"promoted": 1, "unresolved": 0})
        group = draft["questions"][0]
        jsonschema.validate(group, self.question_schema)

        self.assertEqual(group["kind"], "cloze_group")
        self.assertEqual(group["score"], 4.0)
        self.assertEqual(group["answer"], ["A", "B"])
        self.assertEqual(len(group["children"]), 2)
        self.assertEqual(group["chapter_key"], "cloze")
        self.assertEqual(group["section_key"], "cloze_training")
        jsonschema.validate(group, self.question_schema)
        self.assertEqual(group["stem"][1]["type"], "table")
        self.assertIn("fictional passage", group["stem"][0]["text"])

        selection = select_sample_questions(draft, self.curriculum)
        self.assertEqual(selection["summary"], {"selected": 1, "excluded": 0})

        book = {
            "edition": "student",
            "chapters": [{
                "title": "完形填空",
                "sections": [{
                    "title": "专项训练",
                    "question_ids": [group["id"]],
                }],
            }],
        }
        student_tex = render_body(book, {group["id"]: group})
        self.assertEqual(student_tex.count("A fictional passage with two blanks."), 1)
        self.assertIn(r"\begin{tabularx}", student_tex)
        self.assertIn(r"\q{1}{2}", student_tex)
        self.assertIn(r"\q{2}{2}", student_tex)
        self.assertNotIn(r"\teacheranswer", student_tex)

        teacher_book = {**book, "edition": "teacher"}
        teacher_tex = render_body(teacher_book, {group["id"]: group})
        self.assertEqual(teacher_tex.count("A fictional passage with two blanks."), 1)
        self.assertIn(r"\teacheranswer{A}", teacher_tex)
        self.assertIn(r"\teacheranswer{B}", teacher_tex)
        self.assertIn("Reviewed explanation one.", teacher_tex)
        self.assertIn("Reviewed explanation two.", teacher_tex)

    def test_incomplete_group_never_falls_back_to_detached_children(self):
        draft = self._promote(missing_second=True)
        self.assertEqual(draft["questions"], [])
        self.assertEqual(draft["summary"]["promoted"], 0)
        self.assertEqual(
            draft["unresolved"][0]["reason"],
            "group_incomplete_verified_or_score",
        )

    def test_group_children_must_share_one_publication_placement(self):
        draft = self._promote(mismatch=True)
        self.assertEqual(draft["questions"], [])
        self.assertEqual(
            draft["unresolved"][0]["reason"],
            "group_classification_mismatch",
        )

    def test_group_duplicate_identity_ignores_answers_and_analysis(self):
        draft = self._promote()
        left = draft["questions"][0]
        right = copy.deepcopy(left)
        right["id"] = "ENG_FFFFFFFFFFFF"
        right["children"][0]["answer"] = "D"
        right["children"][0]["analysis"] = [{"type": "text", "text": "Different reviewed explanation."}]
        clusters = exact_duplicate_clusters([left, right])
        self.assertEqual(len(clusters), 1)
        self.assertEqual(set(clusters[0].question_ids), {left["id"], right["id"]})

    def test_group_sample_requires_every_child_analysis(self):
        draft = self._promote()
        del draft["questions"][0]["children"][1]["analysis"]
        selection = select_sample_questions(draft, self.curriculum)
        self.assertEqual(selection["summary"]["selected"], 0)
        self.assertEqual(
            selection["excluded"][0]["reason"],
            "missing_teacher_analysis",
        )


if __name__ == "__main__":
    unittest.main()

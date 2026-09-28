import json
from pathlib import Path
import unittest

import jsonschema

from engine.pipeline.scoring import apply_score_evidence, build_score_evidence
from engine.pipeline.verification import (
    build_embedded_source_verified_candidate_bank,
)

ROOT = Path(__file__).resolve().parents[1]


def candidate(
    *,
    candidate_id="Q1",
    kind="single_choice",
    section_key="single_choice",
    source_number=1,
    status="parsed",
    review_reasons=None,
):
    item = {
        "candidate_id": candidate_id,
        "source_id": "SRC",
        "subject": "english",
        "source_number": source_number,
        "section_key": section_key,
        "kind": kind,
        "stem_text": "A fictional prompt.",
        "locators": ["src/1"],
        "status": status,
        "review_reasons": list(review_reasons or []),
    }
    if kind == "single_choice":
        item["options"] = [
            {"label": "A", "text": "one"},
            {"label": "B", "text": "two"},
            {"label": "C", "text": "three"},
            {"label": "D", "text": "four"},
        ]
    return item


def bank(*items):
    return {
        "source_id": "SRC",
        "subject": "english",
        "candidates": list(items),
    }


def evidence(items):
    out = []
    for index, item in enumerate(items):
        row = {
            "evidence_id": f"E{index}",
            "source_id": "SRC",
            "subject": "english",
            "source_number": item["source_number"],
            "section_key": item["section_key"],
            "field": item["field"],
            "value": item["value"],
            "locator": f"src/e/{index}",
            "extraction_mode": item.get("extraction_mode", "explicit_current"),
            "status": "extracted",
        }
        if row["field"] == "source_sample_response":
            import hashlib
            row["value_sha256"] = hashlib.sha256(
                row["value"].encode("utf-8")
            ).hexdigest()
        out.append(row)
    return {
        "source_id": "SRC",
        "subject": "english",
        "evidence": out,
    }


class EmbeddedSourceVerificationTests(unittest.TestCase):
    def setUp(self):
        self.schema = json.loads(
            (ROOT / "schema/verified-candidate-bank.schema.json").read_text(
                encoding="utf-8"
            )
        )

    def test_exact_same_source_choice_answer_is_verified(self):
        result = build_embedded_source_verified_candidate_bank(
            bank(candidate()),
            evidence([{
                "source_number": 1,
                "section_key": "single_choice",
                "field": "answer",
                "value": "B",
            }]),
        )
        jsonschema.validate(result, self.schema)
        self.assertEqual(result["summary"], {
            "verified": 1,
            "rejected": 0,
            "deferred": 0,
        })
        item = result["verified"][0]
        self.assertEqual(item["verified_answer"], "B")
        self.assertEqual(
            item["verification_method"],
            "embedded_source_evidence_accepted",
        )

    def test_missing_heading_is_allowed_only_as_sole_safe_reason(self):
        safe = candidate(
            status="needs_review",
            review_reasons=["section_heading_missing_inferred_single_choice"],
        )
        unsafe = candidate(
            candidate_id="Q2",
            source_number=2,
            status="needs_review",
            review_reasons=[
                "section_heading_missing_inferred_single_choice",
                "option_parse_ambiguous_continuation",
            ],
        )
        result = build_embedded_source_verified_candidate_bank(
            bank(safe, unsafe),
            evidence([
                {
                    "source_number": 1,
                    "section_key": "single_choice",
                    "field": "answer",
                    "value": "A",
                },
                {
                    "source_number": 2,
                    "section_key": "single_choice",
                    "field": "answer",
                    "value": "C",
                },
            ]),
        )
        self.assertEqual(result["summary"]["verified"], 1)
        self.assertEqual(result["deferred_candidate_ids"], ["Q2"])

    def test_conflicting_same_source_answers_stay_deferred(self):
        result = build_embedded_source_verified_candidate_bank(
            bank(candidate()),
            evidence([
                {
                    "source_number": 1,
                    "section_key": "single_choice",
                    "field": "answer",
                    "value": "A",
                },
                {
                    "source_number": 1,
                    "section_key": "single_choice",
                    "field": "answer",
                    "value": "C",
                },
            ]),
        )
        self.assertEqual(result["summary"]["verified"], 0)
        self.assertEqual(result["deferred_candidate_ids"], ["Q1"])

    def test_repeated_self_test_numbers_are_separated_by_section_scope(self):
        first = candidate(
            candidate_id="Q1",
            section_key="single_choice_self_test_1",
        )
        second = candidate(
            candidate_id="Q2",
            section_key="single_choice_self_test_2",
        )
        result = build_embedded_source_verified_candidate_bank(
            bank(first, second),
            evidence([
                {
                    "source_number": 1,
                    "section_key": "single_choice_self_test_1",
                    "field": "answer",
                    "value": "A",
                },
                {
                    "source_number": 1,
                    "section_key": "single_choice_self_test_2",
                    "field": "answer",
                    "value": "D",
                },
            ]),
        )
        self.assertEqual(result["summary"]["verified"], 2)
        self.assertEqual(
            [item["verified_answer"] for item in result["verified"]],
            ["A", "D"],
        )

    def test_composition_requires_explicit_same_source_sample(self):
        writing = candidate(
            kind="composition",
            section_key="writing",
            source_number=56,
        )
        with_sample = build_embedded_source_verified_candidate_bank(
            bank(writing),
            evidence([{
                "source_number": 56,
                "section_key": "writing",
                "field": "source_sample_response",
                "value": "A fictional source sample response.",
                "extraction_mode": "explicit_sample_response",
            }]),
        )
        self.assertEqual(with_sample["summary"]["verified"], 1)
        self.assertEqual(with_sample["verified"][0]["answer_mode"], "open_response")
        self.assertIsNone(with_sample["verified"][0]["verified_answer"])

        without_sample = build_embedded_source_verified_candidate_bank(
            bank(writing),
            evidence([]),
        )
        self.assertEqual(without_sample["summary"]["verified"], 0)
        self.assertEqual(without_sample["deferred_candidate_ids"], ["Q1"])


    def test_embedded_verified_candidate_can_be_scored_from_source_heading(self):
        candidate_bank = bank(candidate())
        candidate_bank["sections"] = [{
            "section_key": "single_choice",
            "heading": "I.单项选择（共1小题，每小题2分，满分2分）",
            "heading_locator": "src/h/1",
            "candidate_count": 1,
            "inferred": False,
        }]
        verified = build_embedded_source_verified_candidate_bank(
            candidate_bank,
            evidence([{
                "source_number": 1,
                "section_key": "single_choice",
                "field": "answer",
                "value": "B",
            }]),
        )
        scored = apply_score_evidence(
            verified,
            build_score_evidence(candidate_bank),
        )
        self.assertEqual(scored["summary"], {"assigned": 1, "unresolved": 0})
        self.assertEqual(scored["assigned"][0]["score"], 2.0)



if __name__ == "__main__":
    unittest.main()

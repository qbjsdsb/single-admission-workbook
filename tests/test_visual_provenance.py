import json
from pathlib import Path
import unittest

import jsonschema

from engine.pipeline.canonical_promotion import promote_to_canonical_draft
from engine.pipeline.scoring import apply_score_evidence
from engine.pipeline.verification import build_verified_candidate_bank

ROOT = Path(__file__).resolve().parents[1]


ASSET_REF = {
    "relationship_id": "rIdFigure",
    "locator": "word/document.xml/body/4/drawing/0",
    "source": "drawingml",
    "asset_sha256": "a" * 64,
    "asset_target": "media/figure.png",
    "asset_extension": ".png",
}


class VisualProvenanceTests(unittest.TestCase):
    def candidate_bank(self):
        return {
            "source_id": "POL-VISUAL",
            "subject": "politics",
            "candidates": [{
                "candidate_id": "POL-VISUAL:q:1:abcd1234",
                "source_id": "POL-VISUAL",
                "subject": "politics",
                "source_number": 1,
                "section_key": "single_choice",
                "kind": "single_choice",
                "stem_text": "观察下图，选择正确答案。",
                "options": [
                    {"label": "A", "text": "甲"},
                    {"label": "B", "text": "乙"},
                    {"label": "C", "text": "丙"},
                    {"label": "D", "text": "丁"},
                ],
                "locators": ["word/document.xml/body/4"],
                "status": "needs_review",
                "review_reasons": ["source_visual_asset_requires_resolution"],
                "asset_refs": [ASSET_REF],
            }],
        }

    def test_human_review_does_not_drop_source_visual_provenance(self):
        bank = self.candidate_bank()
        aggregate = {
            "candidate_source_id": "POL-VISUAL",
            "subject": "politics",
            "rows": [{
                "candidate_id": "POL-VISUAL:q:1:abcd1234",
                "aggregate_status": "single_source_consistent",
                "normalized_answer": "A",
            }],
        }
        manifest = {
            "candidate_source_id": "POL-VISUAL",
            "decisions": [{
                "candidate_id": "POL-VISUAL:q:1:abcd1234",
                "decision": "approve",
                "method": "human_review",
                "verified_answer": "A",
                "note": "Synthetic visual review fixture.",
            }],
        }
        verified = build_verified_candidate_bank(bank, aggregate, manifest)
        self.assertEqual(verified["verified"][0]["asset_refs"], [ASSET_REF])
        schema = json.loads(
            (ROOT / "schema/verified-candidate-bank.schema.json").read_text(encoding="utf-8")
        )
        jsonschema.validate(verified, schema)

    def test_scoring_preserves_source_visual_provenance(self):
        bank = self.candidate_bank()
        aggregate = {
            "candidate_source_id": "POL-VISUAL",
            "subject": "politics",
            "rows": [{
                "candidate_id": "POL-VISUAL:q:1:abcd1234",
                "aggregate_status": "single_source_consistent",
                "normalized_answer": "A",
            }],
        }
        manifest = {
            "candidate_source_id": "POL-VISUAL",
            "decisions": [{
                "candidate_id": "POL-VISUAL:q:1:abcd1234",
                "decision": "approve",
                "method": "human_review",
                "verified_answer": "A",
            }],
        }
        verified = build_verified_candidate_bank(bank, aggregate, manifest)
        scored = apply_score_evidence(
            verified,
            {
                "candidate_source_id": "POL-VISUAL",
                "subject": "politics",
                "sections": [{
                    "section_key": "single_choice",
                    "candidate_count": 1,
                    "status": "usable",
                    "per_question_score": 3.0,
                    "per_question_source": "explicit",
                }],
            },
        )
        self.assertEqual(scored["assigned"][0]["asset_refs"], [ASSET_REF])

    def test_unresolved_source_visual_cannot_reach_canonical(self):
        scored = {
            "subject": "politics",
            "candidate_source_id": "POL-VISUAL",
            "assigned": [{
                "candidate_id": "POL-VISUAL:q:1:abcd1234",
                "source_id": "POL-VISUAL",
                "subject": "politics",
                "source_number": 1,
                "section_key": "single_choice",
                "kind": "single_choice",
                "stem_text": "观察下图，选择正确答案。",
                "options": [
                    {"label": "A", "text": "甲"},
                    {"label": "B", "text": "乙"},
                    {"label": "C", "text": "丙"},
                    {"label": "D", "text": "丁"},
                ],
                "locators": ["word/document.xml/body/4"],
                "asset_refs": [ASSET_REF],
                "verified_answer": "A",
                "score": 3.0,
            }],
        }
        classification = {
            "candidate_source_id": "POL-VISUAL",
            "subject": "politics",
            "decisions": [{
                "candidate_id": "POL-VISUAL:q:1:abcd1234",
                "decision": "assign",
                "chapter_key": "philosophy_culture",
                "section_key": "culture_innovation",
                "tags": ["图像题"],
                "difficulty": "standard",
            }],
        }
        draft = promote_to_canonical_draft(scored, classification)
        self.assertEqual(draft["summary"], {"promoted": 0, "unresolved": 1})
        self.assertEqual(
            draft["unresolved"][0]["reason"],
            "unresolved_source_visual_asset",
        )


if __name__ == "__main__":
    unittest.main()

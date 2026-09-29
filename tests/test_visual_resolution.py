import hashlib
from pathlib import Path
import tempfile
import unittest

from engine.pipeline.canonical_promotion import promote_to_canonical_draft
from engine.pipeline.visual_resolution import resolve_safe_single_visuals


class VisualResolutionTests(unittest.TestCase):
    def bank(self, digest):
        return {
            "schema_version": 1,
            "subject": "politics",
            "candidate_source_id": "POL-SOURCE",
            "assigned": [{
                "candidate_id": "POL-SOURCE:q:1:abcd1234",
                "source_id": "POL-SOURCE",
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
                "asset_refs": [{
                    "relationship_id": "rId7",
                    "locator": "word/document.xml/body/4/drawing/0",
                    "source": "drawingml",
                    "asset_sha256": digest,
                    "asset_target": "media/figure.png",
                    "asset_extension": ".png",
                }],
                "verified_answer": "A",
                "score": 3.0,
            }],
            "unresolved": [],
            "summary": {"assigned": 1, "unresolved": 0},
        }

    def manifest(self, digest, export_name):
        return {
            "source_name": "fictional.docx",
            "source_sha256": "b" * 64,
            "asset_count": 1,
            "assets": {
                "rId7": {
                    "sha256": digest,
                    "export_status": "exported",
                    "export_name": export_name,
                }
            },
        }

    def test_single_explicit_raster_visual_resolves_by_source_hash(self):
        payload = b"fictional-png-fixture"
        digest = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as td:
            asset_dir = Path(td)
            export_name = digest + ".png"
            (asset_dir / export_name).write_bytes(payload)

            result = resolve_safe_single_visuals(
                self.bank(digest),
                self.manifest(digest, export_name),
                asset_dir=asset_dir,
            )
            item = result["bank"]["assigned"][0]
            self.assertNotIn("asset_refs", item)
            self.assertEqual(item["stem_rich"][-1]["type"], "image")
            self.assertEqual(result["audit"]["resolved"], 1)
            self.assertEqual(result["audit"]["deferred"], 0)

            draft = promote_to_canonical_draft(
                result["bank"],
                {
                    "candidate_source_id": "POL-SOURCE",
                    "subject": "politics",
                    "decisions": [{
                        "candidate_id": "POL-SOURCE:q:1:abcd1234",
                        "decision": "assign",
                        "chapter_key": "philosophy_culture",
                        "section_key": "culture_innovation",
                        "tags": ["图像题"],
                        "difficulty": "standard",
                    }],
                },
            )
            self.assertEqual(draft["summary"], {"promoted": 1, "unresolved": 0})
            self.assertEqual(draft["questions"][0]["stem"][-1]["type"], "image")

    def test_hash_mismatch_stays_unresolved_and_fail_closed(self):
        payload = b"fictional-png-fixture"
        digest = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as td:
            asset_dir = Path(td)
            export_name = digest + ".png"
            (asset_dir / export_name).write_bytes(b"different-bytes")

            result = resolve_safe_single_visuals(
                self.bank(digest),
                self.manifest(digest, export_name),
                asset_dir=asset_dir,
            )
            item = result["bank"]["assigned"][0]
            self.assertIn("asset_refs", item)
            self.assertEqual(result["audit"]["resolved"], 0)
            self.assertEqual(result["audit"]["deferred"], 1)
            self.assertEqual(
                result["audit"]["rows"][0]["reason"],
                "exported_visual_bytes_do_not_match_source",
            )

    def test_no_visual_cue_never_guesses_image_placement(self):
        payload = b"fictional-png-fixture"
        digest = hashlib.sha256(payload).hexdigest()
        bank = self.bank(digest)
        bank["assigned"][0]["stem_text"] = "选择正确答案。"
        with tempfile.TemporaryDirectory() as td:
            asset_dir = Path(td)
            export_name = digest + ".png"
            (asset_dir / export_name).write_bytes(payload)
            result = resolve_safe_single_visuals(
                bank,
                self.manifest(digest, export_name),
                asset_dir=asset_dir,
            )
            self.assertEqual(result["audit"]["resolved"], 0)
            self.assertEqual(
                result["audit"]["rows"][0]["reason"],
                "source_stem_has_no_explicit_visual_cue",
            )


if __name__ == "__main__":
    unittest.main()

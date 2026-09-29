import unittest

from engine.pipeline.classification import build_safe_classification_proposals


def bank(stem, *, section_key="single_choice", candidate_id="POL:q:1"):
    return {
        "schema_version": 1,
        "source_id": "POL-SOURCE",
        "subject": "politics",
        "candidates": [{
            "candidate_id": candidate_id,
            "section_key": section_key,
            "stem_text": stem,
        }],
    }


class PoliticsClassificationTests(unittest.TestCase):
    def test_market_economy_maps_to_official_syllabus_section(self):
        result = build_safe_classification_proposals(
            bank("市场调节有自发性、盲目性和滞后性，宏观调控应发挥作用。")
        )
        decision = result["decisions"][0]
        self.assertEqual(decision["decision"], "assign")
        self.assertEqual(decision["chapter_key"], "economy_society")
        self.assertEqual(decision["section_key"], "market_economy")

    def test_culture_maps_to_culture_innovation(self):
        result = build_safe_classification_proposals(
            bank("中华优秀传统文化需要实现创造性转化和创新性发展。")
        )
        decision = result["decisions"][0]
        self.assertEqual(decision["decision"], "assign")
        self.assertEqual(decision["chapter_key"], "philosophy_culture")
        self.assertEqual(decision["section_key"], "culture_innovation")

    def test_ambiguous_multi_section_question_stays_deferred(self):
        result = build_safe_classification_proposals(
            bank("坚持党的领导，全面推进依法治国，建设法治国家。")
        )
        decision = result["decisions"][0]
        self.assertEqual(decision["decision"], "defer")
        self.assertEqual(
            decision["note"],
            "politics_semantic_ambiguous_or_unsupported",
        )

    def test_explicit_current_affairs_source_section_maps_directly(self):
        result = build_safe_classification_proposals(
            bank(
                "某年度国内外重大时事填空。",
                section_key="annual_current_affairs",
            )
        )
        decision = result["decisions"][0]
        self.assertEqual(decision["decision"], "assign")
        self.assertEqual(decision["chapter_key"], "current_affairs")
        self.assertEqual(decision["section_key"], "annual_current_affairs")


if __name__ == "__main__":
    unittest.main()

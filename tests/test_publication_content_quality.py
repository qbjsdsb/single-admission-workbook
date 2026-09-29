import unittest

from engine.quality.publication_content import validate_publication_content


class PublicationContentQualityTests(unittest.TestCase):
    def _question(self, qid, analysis):
        return {
            "id": qid,
            "kind": "single_choice",
            "stem": [{"type": "text", "text": f"Fictional stem {qid}"}],
            "analysis": [{"type": "text", "text": analysis}],
        }

    def test_many_identical_teacher_analyses_are_blocked(self):
        repeated = (
            "This is a deliberately generic fictional explanation that repeats "
            "without question-specific reasoning."
        )
        questions = [
            self._question(f"Q{i}", repeated)
            for i in range(8)
        ]
        errors = validate_publication_content(questions)
        self.assertTrue(any(
            "teacher analysis boilerplate repeated 8 times" in error
            for error in errors
        ))

    def test_normal_unique_teacher_analyses_are_not_blocked(self):
        questions = [
            self._question(
                f"Q{i}",
                f"Fictional explanation {i}: this answer follows from a distinct premise.",
            )
            for i in range(8)
        ]
        errors = validate_publication_content(questions)
        self.assertFalse(any(
            "teacher analysis boilerplate repeated" in error
            for error in errors
        ))


if __name__ == "__main__":
    unittest.main()

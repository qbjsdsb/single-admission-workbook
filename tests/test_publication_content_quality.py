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

    def test_repeated_composition_analysis_is_blocked_after_two_prompts(self):
        repeated = (
            "A reviewed-looking but generic writing explanation that says to cover all points, "
            "use clear paragraphs, and check grammar after finishing."
        )
        questions = []
        for i in range(2):
            question = self._question(f"W{i}", repeated)
            question["kind"] = "composition"
            questions.append(question)
        errors = validate_publication_content(questions)
        self.assertTrue(any(
            "composition teacher analysis repeated 2 times" in error
            for error in errors
        ))

    def test_known_generic_open_writing_template_is_blocked(self):
        question = self._question(
            "W1",
            "本题为开放写作。先逐项圈出题干中的内容要求，再确定合适的人称、时态和书信格式。",
        )
        question["kind"] = "composition"
        errors = validate_publication_content([question])
        self.assertTrue(any(
            "placeholder/template teacher analysis is not publishable" in error
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

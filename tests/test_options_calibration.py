import unittest

from engine.parse.options import parse_options


class OptionCalibrationTests(unittest.TestCase):
    def test_recovers_bare_initial_a_only_when_later_marker_confirms_option_row(self):
        result = parse_options([
            "A first choice    B. second choice",
            "C. third choice    D. fourth choice",
        ])
        self.assertEqual(result.status, "ok")
        self.assertEqual([label for label, _ in result.options], list("ABCD"))
        self.assertEqual(result.options[0][1], "first choice")

    def test_recovers_bare_later_labels_after_option_parsing_started(self):
        result = parse_options([
            "A. first choice",
            "B. second choice",
            "C third choice",
            "D fourth choice",
        ])
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.options[2], ("C", "third choice"))
        self.assertEqual(result.options[3], ("D", "fourth choice"))

    def test_plain_stem_starting_with_a_is_not_reinterpreted_as_option(self):
        result = parse_options([
            "A person can still write a normal stem here.",
            "The next sentence is also part of the stem.",
        ])
        self.assertEqual(result.status, "none")
        self.assertEqual(
            result.stem_paragraphs[0],
            "A person can still write a normal stem here.",
        )

    def test_volume_marker_after_complete_options_is_ignored(self):
        result = parse_options([
            "A. first choice",
            "B. second choice",
            "C. third choice",
            "D. fourth choice",
            "第二卷（两大题，共30分）",
        ])
        self.assertEqual(result.status, "ok")

    def test_arbitrary_text_after_complete_options_remains_fail_closed(self):
        result = parse_options([
            "A. first choice",
            "B. second choice",
            "C. third choice",
            "D. fourth choice",
            "This could be a wrapped option and must not be silently dropped.",
        ])
        self.assertEqual(result.status, "ambiguous_continuation")

    def test_nonsequential_labels_still_fail_closed(self):
        result = parse_options([
            "A first choice    C. third choice",
            "D. fourth choice",
        ])
        self.assertNotEqual(result.status, "ok")


if __name__ == "__main__":
    unittest.main()

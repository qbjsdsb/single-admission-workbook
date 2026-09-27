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

    def test_recovers_bare_initial_a_on_own_line_when_next_line_is_strict_b(self):
        result = parse_options([
            "A first choice",
            "B. second choice",
            "C. third choice",
            "D. fourth choice",
        ])
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.options[0], ("A", "first choice"))

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

    def test_stem_starting_with_a_before_strict_inline_options_stays_stem(self):
        result = parse_options([
            "A fictional stem A. One B. Two C. Three D. Four",
        ])
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.stem_paragraphs, ("A fictional stem",))
        self.assertEqual(
            result.options,
            (("A", "One"), ("B", "Two"), ("C", "Three"), ("D", "Four")),
        )

    def test_acronym_tail_does_not_become_fake_option_marker(self):
        result = parse_options([
            "A. TTEC.    B. Hopper.",
            "C. Kaplan.  D. Zoom.",
        ])
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.options[0], ("A", "TTEC."))
        self.assertEqual(result.options[1], ("B", "Hopper."))

    def test_glued_label_after_lowercase_text_still_parses(self):
        result = parse_options([
            "A. oneB. twoC. threeD. four",
        ])
        self.assertEqual(result.status, "ok")
        self.assertEqual(
            result.options,
            (("A", "one"), ("B", "two"), ("C", "three"), ("D", "four")),
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

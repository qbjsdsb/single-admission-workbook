import unittest

from engine.ingest.pairing import exact_pair_candidates
from engine.parse.exam_split import extract_answer_annotations, split_numbered_questions

class PairAndSplitTests(unittest.TestCase):
    def test_exact_pair(self):
        items = [
            {"path": "a-student.docx", "pair_key": "abc", "role": "student", "subject": "english"},
            {"path": "a-solution.docx", "pair_key": "abc", "role": "solution", "subject": "english"},
        ]
        pairs = exact_pair_candidates(items)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0].companion_role, "solution")

    def test_english_sections_and_questions(self):
        paras = [
            "单项选择（共2小题）",
            "1. This is a fictional question.",
            "A. Alpha B. Beta",
            "2. This is another fictional question.",
            "A. One B. Two",
            "II.完形填空（共1小题）",
            "3. A fictional cloze item.",
        ]
        blocks = split_numbered_questions(paras, "english")
        self.assertEqual([b.number for b in blocks], [1, 2, 3])
        self.assertEqual(blocks[0].kind, "single_choice")
        self.assertEqual(blocks[2].kind, "cloze_group")

    def test_politics_answer_annotations(self):
        paras = [
            "1. 答案：B",
            "题干核心：虚构核心提示。",
            "解析：这是虚构解析。",
            "26.甲27.乙28.丙",
            "31.第一点；第二点。",
        ]
        got = extract_answer_annotations(paras)
        self.assertEqual(got[1]["answer"], "B")
        self.assertEqual(got[1]["analysis"], "这是虚构解析。")
        self.assertEqual(got[26]["answer"], "甲")
        self.assertEqual(got[28]["answer"], "丙")
        self.assertEqual(got[31]["answer"], "第一点；第二点。")

if __name__ == "__main__":
    unittest.main()

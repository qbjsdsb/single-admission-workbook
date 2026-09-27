import unittest

from engine.ingest.pairing import exact_pair_candidates
from engine.parse.exam_split import (
    extract_answer_annotations,
    split_section,
    split_sections,
)

class PairAndSplitTests(unittest.TestCase):
    def test_exact_pair(self):
        items = [
            {"path": "a-student.docx", "pair_key": "abc", "role": "student", "subject": "english"},
            {"path": "a-solution.docx", "pair_key": "abc", "role": "solution", "subject": "english"},
        ]
        pairs = exact_pair_candidates(items)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0].companion_role, "solution")

    def test_english_grouped_sections_and_missing_number_punctuation(self):
        paras = [
            "单项选择（共2小题）",
            "1. This is a fictional question.",
            "A. Alpha B. Beta",
            "2 This fictional source intentionally misses punctuation after the number.",
            "A. One B. Two",
            "II.完形填空（共2小题）",
            "Read this fictional cloze passage with blanks.",
            "3. A. red B. blue C. green D. black",
            "4. A. north B. south C. east D. west",
            "III.阅读理解（共2小题）",
            "Read the fictional passages.",
            "A",
            "A fictional passage A.",
            "5. What is the passage about?",
            "A. One B. Two",
            "B",
            "A fictional passage B.",
            "6. What is the second passage about?",
            "A. Three B. Four",
            "V.书面表达（满分10分）",
            "Write a fictional email of about 100 words.",
        ]
        sections = split_sections(paras, "english")
        self.assertEqual([s.section_key for s in sections], [
            "single_choice", "cloze", "reading", "writing"
        ])

        simple = split_section(sections[0], "english")
        self.assertEqual([q.number for q in simple], [1, 2])

        cloze = split_section(sections[1], "english")
        self.assertEqual(len(cloze), 1)
        self.assertEqual([q.number for q in cloze[0].questions], [3, 4])
        self.assertTrue(cloze[0].shared_material)

        reading = split_section(sections[2], "english")
        self.assertEqual([g.label for g in reading], ["A", "B"])
        self.assertEqual([q.number for q in reading[0].questions], [5])
        self.assertEqual([q.number for q in reading[1].questions], [6])

        writing = split_section(sections[3], "english")
        self.assertEqual(len(writing), 1)
        self.assertIsNone(writing[0].number)
        self.assertEqual(writing[0].kind, "composition")

    def test_companion_answer_annotations(self):
        paras = [
            "1. A fictional question stem.",
            "A. Alpha B. Beta",
            "答案：B",
            "题干核心：虚构核心提示。",
            "解析：这是虚构解析。",
            "12 Another fictional question with missing punctuation.",
            "A. One B. Two",
            "答案：A",
            "26.甲27.乙28.丙",
            "31.第一点；第二点。",
        ]
        got = extract_answer_annotations(paras)
        self.assertEqual(got[1]["answer"], "B")
        self.assertEqual(got[1]["analysis"], "这是虚构解析。")
        self.assertEqual(got[12]["answer"], "A")
        self.assertEqual(got[26]["answer"], "甲")
        self.assertEqual(got[28]["answer"], "丙")
        self.assertEqual(got[31]["answer"], "第一点；第二点。")

if __name__ == "__main__":
    unittest.main()

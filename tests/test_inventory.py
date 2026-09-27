from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.ingest.inventory import (
    infer_role, infer_source_class, infer_subject, infer_year,
    inventory_zip, parser_lane, summarize,
)

class InventoryTests(unittest.TestCase):
    def test_subject_and_year(self):
        self.assertEqual(infer_subject("资料/语文/2024真题.docx"), "chinese")
        self.assertEqual(infer_subject("资料/数学/示例.pdf"), "mathematics")
        self.assertEqual(infer_year("2011-2025/2024年英语真题.doc"), 2024)

    def test_source_classes(self):
        self.assertEqual(infer_source_class("【备考笔记】体育单招文化课——英语/全国英语大纲.pdf"), "syllabus")
        self.assertEqual(infer_source_class("【备考笔记】体育单招文化课——数学/数学公式大全.pdf"), "reference")
        self.assertEqual(infer_source_class("资料/2026全真模拟卷.pdf"), "mock_exam")
        self.assertEqual(infer_source_class("资料/2024年体育单招真题.pdf"), "past_exam")

    def test_roles(self):
        self.assertEqual(infer_role("模拟卷（学生版）.docx"), "student")
        self.assertEqual(infer_role("模拟卷【原卷版】.pdf"), "student")
        self.assertEqual(infer_role("模拟卷（教师版）.docx"), "teacher")
        self.assertEqual(infer_role("模拟卷【解析版】.pdf"), "solution")
        self.assertEqual(infer_role("2024真题及答案.pdf"), "mixed")

    def test_lanes(self):
        self.assertEqual(parser_lane(".docx"), "docx")
        self.assertEqual(parser_lane(".doc"), "legacy_doc")
        self.assertEqual(parser_lane(".pdf"), "pdf_probe")

    def test_zip_inventory_and_pairing(self):
        with tempfile.TemporaryDirectory() as td:
            zpath = Path(td) / "sources.zip"
            with zipfile.ZipFile(zpath, "w") as zf:
                zf.writestr("语文/2025模拟卷1（学生版）.docx", b"a")
                zf.writestr("语文/2025模拟卷1（教师版）.docx", b"b")
                zf.writestr("数学/2024真题.pdf", b"c")
            result = summarize(inventory_zip(zpath))
            self.assertEqual(result["files"], 3)
            self.assertEqual(result["by_subject"]["chinese"], 2)
            self.assertEqual(result["by_source_class"]["mock_exam"], 2)
            self.assertEqual(result["candidate_student_teacher_or_solution_pairs"], 1)

if __name__ == "__main__":
    unittest.main()

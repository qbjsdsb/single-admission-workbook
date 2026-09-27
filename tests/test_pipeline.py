import copy
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from engine.ingest.inventory import infer_role, infer_year, normalized_pair_key
from engine.pipeline.intake import intake
from engine.pipeline.books import plan_books

ROOT = Path(__file__).resolve().parents[1]

class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT / 'examples/eight-books/dataset.json').read_text())

    def plan(self):
        return plan_books(self.data['questions'], self.data['ledger'], self.data['curriculum'])

    def test_eight_editions_same_order(self):
        books, _ = self.plan()
        self.assertEqual(len(books), 8)
        for i in range(0, 8, 2):
            self.assertEqual(books[i]['chapters'], books[i + 1]['chapters'])

    def test_missing_analysis_blocks(self):
        self.data['questions'][0]['analysis'] = [{'type': 'text', 'text': ' '}]
        with self.assertRaisesRegex(ValueError, 'missing answer or analysis'):
            self.plan()

    def test_source_coverage_blocks(self):
        self.data['ledger']['sources'][0]['expected_questions'] = 2
        with self.assertRaisesRegex(ValueError, 'expected 2, accounted 1'):
            self.plan()

    def test_unknown_chapter_blocks(self):
        self.data['questions'][0]['chapter_key'] = 'unknown'
        with self.assertRaisesRegex(ValueError, 'unresolved chapter'):
            self.plan()

    def test_duplicate_canonical_ids_block(self):
        self.data['questions'].append(copy.deepcopy(self.data['questions'][0]))
        with self.assertRaisesRegex(ValueError, 'duplicate canonical'):
            self.plan()

    def test_duplicate_sources_preserve_occurrences(self):
        source = copy.deepcopy(self.data['ledger']['sources'][0])
        source['id'] = 'copy-source'
        occurrence = copy.deepcopy(self.data['ledger']['occurrences'][0])
        occurrence.update(id='copy-occurrence', source_id='copy-source')
        self.data['ledger']['sources'].append(source)
        self.data['ledger']['expected_source_ids'].append('copy-source')
        self.data['ledger']['occurrences'].append(occurrence)
        books, bank = self.plan()
        self.assertEqual(len(bank), 4)
        self.assertEqual(len(books[0]['chapters'][0]['sections'][0]['question_ids']), 1)

    def test_teacher_volume_and_spaces(self):
        self.assertEqual(infer_role('政治（教师卷）.docx'), 'teacher')
        self.assertEqual(normalized_pair_key('政治/模拟 1（教师卷）.docx'),
                         normalized_pair_key('政治/模拟1（学生卷）.docx'))
        self.assertIsNone(infer_year('12024年'))

    def test_cache_and_path_traversal(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            archive = root / 'input.zip'
            with zipfile.ZipFile(archive, 'w') as z:
                z.writestr('../../escaped.bin', b'legacy payload')
                z.writestr('数学/copy.bin', b'legacy payload')
            first = intake(archive, root / 'out')
            second = intake(archive, root / 'out')
            self.assertEqual(first['files'], 2)
            self.assertEqual(first['unique_payloads'], 1)
            self.assertEqual(second['cache_hits'], 1)
            self.assertFalse((root / 'escaped.bin').exists())

    def test_pdf_later_scan_is_not_lost(self):
        try:
            import fitz
        except ImportError:
            self.skipTest('PyMuPDF not installed')
        from engine.pipeline.intake import extract
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'mixed.pdf'
            with fitz.open() as doc:
                p = doc.new_page()
                p.insert_text((50, 50), 'A readable line. ' * 8)
                doc.new_page()
                doc.save(path)
            result = extract(path)
            self.assertEqual(len(result['pages']), 2)
            self.assertTrue(result['pages'][1]['needs_ocr'])
            self.assertIn('ocr', result['required_work'])

if __name__ == '__main__':
    unittest.main()

class RichCaptureTests(unittest.TestCase):
    def test_marks_math_and_tables_remain_explicit(self):
        from engine.parse.docx_structure import extract_structure
        xml = '''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"><w:body><w:p><w:r><w:rPr><w:em w:val="dot"/><w:u w:val="single"/></w:rPr><w:t>春</w:t></w:r><m:oMath><m:r><m:t>x</m:t></m:r></m:oMath></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>保留单元格</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>'''
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'source.docx'
            with zipfile.ZipFile(path, 'w') as z:
                z.writestr('word/document.xml', xml)
            blocks = extract_structure(path)['blocks']
            self.assertEqual(blocks[0]['runs'][0]['properties']['em'], 'dot')
            self.assertEqual(blocks[0]['runs'][0]['properties']['u'], 'single')
            self.assertEqual(len(blocks[0]['math_omml']), 1)
            self.assertEqual(blocks[1]['kind'], 'tbl')
            self.assertIn('保留单元格', blocks[1]['xml'])

    def test_duplicate_archive_names_are_blocked(self):
        import warnings
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                with zipfile.ZipFile(root / 'source.zip', 'w') as z:
                    z.writestr('same.docx', b'first')
                    z.writestr('same.docx', b'second')
            with self.assertRaisesRegex(ValueError, 'Duplicate ZIP'):
                intake(root / 'source.zip', root / 'out')

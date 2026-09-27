import json
from pathlib import Path
import tempfile
import unittest
import fitz

from engine.document.pdf_reader import read_pdf_document_with_pages
from engine.pipeline.intake import extract
from scripts.prepare_pdf_visual_review import prepare


class PdfVisualReviewTests(unittest.TestCase):
    def make_source(self, path):
        with fitz.open() as doc:
            for _ in range(3):
                page = doc.new_page()
                page.insert_textbox(fitz.Rect(50, 50, 500, 250), 'Fictional exercise text. ' * 20)
            doc[1].draw_line((50, 300), (200, 400))
            doc[2].add_ink_annot([[(50, 300), (70, 320), (90, 290)]])
            doc.save(path)

    def test_native_text_does_not_hide_vectors_or_ink(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'source.pdf'
            self.make_source(path)
            ast, pages = read_pdf_document_with_pages(path)
            self.assertFalse(any(p['needs_ocr'] for p in pages))
            self.assertFalse(pages[0]['needs_visual_review'])
            self.assertIn('vector_content', pages[1]['visual_reasons'])
            self.assertIn('annotations', pages[2]['visual_reasons'])
            self.assertIn('visual_content_review', extract(path)['required_work'])
            self.assertIn('pdf_visual_content_requires_review', ast.warnings)

    def test_prepare_preserves_coverage_and_reuses_page_renders(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / 'source.pdf'
            self.make_source(source)
            result = prepare(source, root / 'out', 72)
            manifest_path = Path(result['manifest'])
            manifest = json.loads(manifest_path.read_text())
            self.assertEqual(len(manifest['pages']), 3)
            self.assertEqual(result['visual_review_pages'], 2)
            image = manifest_path.parent / manifest['pages'][1]['original_page_image']
            stamp = image.stat().st_mtime_ns
            prepare(source, root / 'out', 72)
            self.assertEqual(stamp, image.stat().st_mtime_ns)
            self.assertEqual(manifest['status'], 'review_only_not_publishable')
            image.write_bytes(b'broken')
            prepare(source, root / 'out', 72)
            self.assertGreater(fitz.Pixmap(str(image)).width, 0)

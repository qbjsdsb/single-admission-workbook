from pathlib import Path
import tempfile
import unittest
import zipfile

from engine.ingest.probe import classify_pdf_sample, probe_docx

DOC_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
 xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">
 <w:body>
  <w:p><w:r><w:rPr><w:em w:val="dot"/><w:u w:val="single"/></w:rPr><w:t>示例</w:t></w:r></w:p>
  <w:tbl><w:tr><w:tc><w:p/></w:tc></w:tr></w:tbl>
  <m:oMath><m:r/></m:oMath>
 </w:body>
</w:document>
"""

class ProbeTests(unittest.TestCase):
    def test_pdf_mode_classification(self):
        self.assertEqual(classify_pdf_sample(sampled_pages=5, text_chars=2500, image_blocks=0), "text")
        self.assertEqual(classify_pdf_sample(sampled_pages=5, text_chars=20, image_blocks=5), "scan")
        self.assertEqual(classify_pdf_sample(sampled_pages=5, text_chars=1800, image_blocks=20), "mixed")
        self.assertEqual(classify_pdf_sample(sampled_pages=5, text_chars=0, image_blocks=0), "sparse")

    def test_docx_capability_probe(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "sample.docx"
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("word/document.xml", DOC_XML)
                zf.writestr("word/media/image1.png", b"fake")
                zf.writestr("word/embeddings/oleObject1.bin", b"fake")
            result = probe_docx(path)
            self.assertGreaterEqual(result.paragraphs, 1)
            self.assertEqual(result.tables, 1)
            self.assertEqual(result.emphasis_marks, 1)
            self.assertEqual(result.underlines, 1)
            self.assertEqual(result.math_objects, 1)
            self.assertEqual(result.media_files, 1)
            self.assertEqual(result.embedded_files, 1)

if __name__ == "__main__":
    unittest.main()

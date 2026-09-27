import json
from pathlib import Path
import tempfile
import unittest
import zipfile

import jsonschema

from engine.document.docx_reader import structure_to_document_ast
from engine.document.pdf_reader import read_pdf_document_with_pages
from engine.pipeline.intake import extract
from engine.parse.docx_structure import extract_structure

ROOT = Path(__file__).resolve().parents[1]

DOC_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
 xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"
 xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
 <w:body>
  <w:p>
   <w:r><w:rPr><w:em w:val="dot"/><w:u w:val="single"/></w:rPr><w:t>甲</w:t></w:r>
   <w:r><w:tab/><w:t>乙</w:t><w:br/><w:t>丙</w:t></w:r>
   <m:oMath><m:r><m:t>x+1</m:t></m:r></m:oMath>
  </w:p>
  <w:tbl><w:tr><w:tc><w:p><w:r><w:t>表格</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
 </w:body>
</w:document>
"""

class DocumentAstTests(unittest.TestCase):
    def setUp(self):
        self.schema = json.loads((ROOT / "schema/document.schema.json").read_text(encoding="utf-8"))

    def test_docx_structure_preserves_tab_break_and_rich_nodes(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "sample.docx"
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("word/document.xml", DOC_XML)
            structure = extract_structure(path)
            self.assertIn("\t", structure["blocks"][0]["runs"][1]["text"])
            self.assertIn("\n", structure["blocks"][0]["runs"][1]["text"])

            ast = structure_to_document_ast(structure).to_dict()
            jsonschema.validate(ast, self.schema)
            paragraph = ast["blocks"][0]
            self.assertEqual(paragraph["type"], "paragraph")
            self.assertIn("emphasis_dot", paragraph["inlines"][0]["styles"])
            self.assertIn("underline", paragraph["inlines"][0]["styles"])
            self.assertTrue(any(n["type"] == "math_omml" for n in paragraph["inlines"]))
            self.assertEqual(ast["blocks"][1]["type"], "unsupported")
            self.assertEqual(ast["blocks"][1]["feature"], "docx_table")

    def test_intake_docx_emits_document_ast(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "sample.docx"
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("word/document.xml", DOC_XML)
            result = extract(path)
            self.assertEqual(result["format"], "docx")
            self.assertEqual(result["document_ast"]["version"], 1)
            jsonschema.validate(result["document_ast"], self.schema)

    def test_pdf_reader_emits_page_bbox_and_ocr_marker(self):
        import fitz
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "sample.pdf"
            doc = fitz.open()
            p1 = doc.new_page()
            p1.insert_text((72, 72), "A sufficiently long fictional paragraph " * 5)
            p2 = doc.new_page()
            p2.insert_text((72, 72), "short")
            doc.save(path)
            doc.close()

            ast, pages = read_pdf_document_with_pages(path)
            data = ast.to_dict()
            jsonschema.validate(data, self.schema)
            self.assertEqual(len(pages), 2)
            self.assertFalse(pages[0]["needs_ocr"])
            self.assertTrue(pages[1]["needs_ocr"])
            paragraph = next(b for b in data["blocks"] if b["type"] == "paragraph")
            self.assertEqual(paragraph["page"], 1)
            self.assertEqual(len(paragraph["bbox"]), 4)
            self.assertTrue(any(
                b["type"] == "unsupported" and b["feature"] == "ocr_required" and b["page"] == 2
                for b in data["blocks"]
            ))

if __name__ == "__main__":
    unittest.main()

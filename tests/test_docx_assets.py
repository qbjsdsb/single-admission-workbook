import json
from pathlib import Path
import tempfile
import unittest
import zipfile

import jsonschema

from engine.document.docx_assets import export_docx_assets
from engine.document.docx_reader import read_docx_document
from engine.parse.candidate_bank import safe_paragraphs
from engine.parse.docx_text import paragraphs_from_document_ast
from engine.parse.docx_structure import extract_structure
from engine.parse.evidence_bank import _safe_paragraphs

ROOT = Path(__file__).resolve().parents[1]

DOC_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document
 xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
 xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
 xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
 xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"
 xmlns:v="urn:schemas-microsoft-com:vml"
 xmlns:o="urn:schemas-microsoft-com:office:office">
 <w:body>
  <w:p>
   <w:r><w:t>图：</w:t></w:r>
   <w:r><w:drawing><wp:inline><wp:extent cx="914400" cy="457200"/>
    <wp:docPr id="1" name="示例图"/>
    <a:graphic><a:graphicData><pic:pic><pic:blipFill>
     <a:blip r:embed="rIdPhoto"/>
    </pic:blipFill></pic:pic></a:graphicData></a:graphic>
   </wp:inline></w:drawing></w:r>
  </w:p>
  <w:p>
   <w:r><w:t>公式：</w:t></w:r>
   <w:r><w:object>
    <v:shape id="_x0000_i1025" style="height:22pt;width:73pt;">
     <v:imagedata r:id="rIdPreview"/>
    </v:shape>
    <o:OLEObject Type="Embed" ProgID="Equation.DSMT4"
      ShapeID="_x0000_i1025" ObjectID="_fixture" r:id="rIdOle"/>
   </w:object></w:r>
  </w:p>
  <w:p>
   <w:r><w:t>按照老师教</w:t></w:r>
   <w:r><w:drawing><wp:inline><wp:extent cx="133350" cy="177800"/>
    <wp:docPr id="2" name="MathType glyph"/>
    <a:graphic><a:graphicData><pic:pic><pic:blipFill>
     <a:blip r:embed="rIdMath"/>
    </pic:blipFill></pic:pic></a:graphicData></a:graphic>
   </wp:inline></w:drawing></w:r>
   <w:r><w:t>方法学习</w:t></w:r>
  </w:p>
 </w:body>
</w:document>
"""

RELS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Id="rIdPhoto"
  Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
  Target="media/photo.png"/>
 <Relationship Id="rIdPreview"
  Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
  Target="media/equation.wmf"/>
 <Relationship Id="rIdOle"
  Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/oleObject"
  Target="embeddings/oleObject1.bin"/>
 <Relationship Id="rIdMath"
  Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
  Target="media/math-symbol.wmf"/>
</Relationships>
"""

MATHML_WMF = (
    b"\x01\x00\x09\x00MathType"
    b"<?xml version=\"1.0\"?><!-- MathType synthetic fixture -->"
    b"<math display='block' xmlns='http://www.w3.org/1998/Math/MathML'>"
    b"<mi>&#x7684;</mi></math><!-- end synthetic fixture -->"
)


def make_docx(path: Path):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("word/document.xml", DOC_XML)
        zf.writestr("word/_rels/document.xml.rels", RELS_XML)
        zf.writestr("word/media/photo.png", b"PNG-FIXTURE")
        zf.writestr("word/media/equation.wmf", b"WMF-FIXTURE")
        zf.writestr("word/media/math-symbol.wmf", MATHML_WMF)
        zf.writestr("word/embeddings/oleObject1.bin", b"OLE-FIXTURE")


class DocxAssetTests(unittest.TestCase):
    def setUp(self):
        self.schema = json.loads(
            (ROOT / "schema/document.schema.json").read_text(encoding="utf-8")
        )

    def test_structure_captures_asset_hashes_drawing_and_equation_ole(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "fixture.docx"
            make_docx(path)
            structure = extract_structure(path)

            self.assertEqual(set(structure["assets"]), {"rIdPhoto", "rIdPreview", "rIdOle", "rIdMath"})
            self.assertEqual(structure["assets"]["rIdPhoto"]["extension"], ".png")
            self.assertEqual(structure["assets"]["rIdPreview"]["extension"], ".wmf")
            self.assertEqual(structure["assets"]["rIdOle"]["relationship_type"], "oleObject")
            self.assertEqual(structure["assets"]["rIdMath"]["mathml_inline_text"], "的")

            drawing = structure["blocks"][0]["drawings"][0]
            self.assertEqual(drawing["relationship_id"], "rIdPhoto")
            self.assertEqual(drawing["cx_emu"], 914400)
            self.assertEqual(drawing["cy_emu"], 457200)

            ole = structure["blocks"][1]["ole_objects"][0]
            self.assertTrue(ole["is_equation"])
            self.assertEqual(ole["prog_id"], "Equation.DSMT4")
            self.assertEqual(ole["relationship_id"], "rIdOle")
            self.assertEqual(ole["preview_relationship_id"], "rIdPreview")

    def test_document_ast_links_assets_without_flattening_equation(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "fixture.docx"
            make_docx(path)
            ast = read_docx_document(path).to_dict()
            jsonschema.validate(ast, self.schema)

            nodes = [
                inline
                for block in ast["blocks"]
                if block["type"] == "paragraph"
                for inline in block["inlines"]
            ]
            image = next(n for n in nodes if n["type"] == "image_ref")
            equation = next(n for n in nodes if n["type"] == "ole_object_ref")

            self.assertEqual(image["asset_extension"], ".png")
            self.assertEqual(image["cx_emu"], 914400)
            self.assertEqual(equation["feature"], "equation_ole")
            self.assertEqual(equation["asset_extension"], ".bin")
            self.assertEqual(equation["preview_asset_extension"], ".wmf")
            self.assertEqual(equation["status"], "captured_not_normalized")

    def test_content_addressed_asset_export(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "fixture.docx"
            out = Path(td) / "assets"
            make_docx(path)
            manifest = export_docx_assets(path, out)

            self.assertEqual(manifest["asset_count"], 4)
            exported = [
                item for item in manifest["assets"].values()
                if item["export_status"] == "exported"
            ]
            self.assertEqual(len(exported), 4)
            for item in exported:
                self.assertTrue((out / item["export_name"]).is_file())
                self.assertEqual(len(item["sha256"]), 64)
            self.assertTrue((out / "assets-manifest.json").is_file())

    def test_mathml_wmf_text_is_recovered_in_order_with_provenance(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "symbol.docx"
            make_docx(path)
            structure = extract_structure(path)
            asset = structure["assets"]["rIdMath"]
            self.assertEqual(asset["mathml_status"], "inline_text")
            self.assertEqual(asset["mathml_inline_text"], "的")

            ast = read_docx_document(path).to_dict()
            jsonschema.validate(ast, self.schema)
            paragraph = ast["blocks"][2]
            self.assertEqual(
                [inline["type"] for inline in paragraph["inlines"]],
                ["text", "mathml_inline_text", "text"],
            )
            symbol = paragraph["inlines"][1]
            self.assertEqual(symbol["text"], "的")
            self.assertEqual(symbol["source_asset_sha256"], asset["sha256"])
            self.assertIn("<mi>", symbol["mathml_xml"])

            visible_text = "".join(
                inline.get("text", "") for inline in paragraph["inlines"]
            )
            self.assertEqual(visible_text, "按照老师教的方法学习")
            self.assertIn(visible_text, paragraphs_from_document_ast(ast))
            candidate_paragraphs, candidate_blockers = safe_paragraphs(ast)
            self.assertIn(visible_text, [item.text for item in candidate_paragraphs])
            self.assertNotIn(paragraph["locator"], [item["locator"] for item in candidate_blockers])
            evidence_paragraphs, evidence_blockers = _safe_paragraphs(ast)
            self.assertIn(visible_text, [item.text for item in evidence_paragraphs])
            self.assertNotIn(paragraph["locator"], [item["locator"] for item in evidence_blockers])


if __name__ == "__main__":
    unittest.main()

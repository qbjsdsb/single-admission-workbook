from __future__ import annotations

from io import BytesIO
from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

def _paragraphs_from_zip(zf: zipfile.ZipFile) -> list[str]:
    root = ET.fromstring(zf.read("word/document.xml"))
    out: list[str] = []
    for p in root.findall(f".//{{{W}}}p"):
        pieces: list[str] = []
        for node in p.iter():
            if node.tag == f"{{{W}}}t":
                pieces.append(node.text or "")
            elif node.tag == f"{{{W}}}tab":
                pieces.append("\t")
            elif node.tag == f"{{{W}}}br":
                pieces.append("\n")
        text = "".join(pieces).strip()
        if text:
            out.append(text)
    return out

def extract_docx_paragraphs(path: Path) -> list[str]:
    from engine.document.docx_reader import structure_to_document_ast
    from engine.parse.docx_structure import extract_structure

    ast = structure_to_document_ast(extract_structure(path)).to_dict()
    return paragraphs_from_document_ast(ast)


def paragraphs_from_document_ast(document_ast: dict) -> list[str]:
    out: list[str] = []
    for block in document_ast.get('blocks') or []:
        if block.get('type') != 'paragraph':
            continue
        text = ''.join(
            str(inline.get('text') or '')
            for inline in block.get('inlines') or []
            if inline.get('type') in {'text', 'mathml_inline_text'}
        ).strip()
        if text:
            out.append(text)
    return out

def extract_docx_paragraphs_bytes(data: bytes) -> list[str]:
    with zipfile.ZipFile(BytesIO(data)) as zf:
        return _paragraphs_from_zip(zf)

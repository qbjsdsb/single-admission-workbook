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
    with zipfile.ZipFile(path) as zf:
        return _paragraphs_from_zip(zf)

def extract_docx_paragraphs_bytes(data: bytes) -> list[str]:
    with zipfile.ZipFile(BytesIO(data)) as zf:
        return _paragraphs_from_zip(zf)

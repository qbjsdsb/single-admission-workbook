#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"

@dataclass(frozen=True)
class PdfProbe:
    pages: int
    sampled_pages: int
    text_chars: int
    image_blocks: int
    text_blocks: int
    mode: str

@dataclass(frozen=True)
class DocxProbe:
    paragraphs: int
    tables: int
    emphasis_marks: int
    underlines: int
    math_objects: int
    media_files: int
    embedded_files: int

def classify_pdf_sample(*, sampled_pages: int, text_chars: int, image_blocks: int) -> str:
    if sampled_pages <= 0:
        return "unknown"
    # A page with an ordinary exam usually has far more than 80 extractable chars.
    avg_chars = text_chars / sampled_pages
    if avg_chars >= 80:
        if image_blocks > sampled_pages * 2:
            return "mixed"
        return "text"
    if image_blocks > 0:
        return "scan"
    return "sparse"

def probe_pdf(path: Path, sample_pages: int = 5) -> PdfProbe:
    import fitz  # PyMuPDF; imported lazily so inventory does not need it.

    doc = fitz.open(path)
    count = min(sample_pages, len(doc))
    text_chars = 0
    image_blocks = 0
    text_blocks = 0
    for index in range(count):
        page = doc[index]
        text = page.get_text("text")
        text_chars += len(text.strip())
        blocks = page.get_text("blocks")
        for block in blocks:
            if len(block) < 7:
                continue
            if block[6] == 0 and str(block[4]).strip():
                text_blocks += 1
        image_blocks += len(page.get_images(full=True))
    return PdfProbe(
        pages=len(doc),
        sampled_pages=count,
        text_chars=text_chars,
        image_blocks=image_blocks,
        text_blocks=text_blocks,
        mode=classify_pdf_sample(
            sampled_pages=count, text_chars=text_chars, image_blocks=image_blocks
        ),
    )

def _count_xml(root: ET.Element, namespace: str, local: str) -> int:
    return len(root.findall(f".//{{{namespace}}}{local}"))

def probe_docx(path: Path) -> DocxProbe:
    with zipfile.ZipFile(path) as zf:
        names = set(zf.namelist())
        if "word/document.xml" not in names:
            raise ValueError(f"{path}: missing word/document.xml")
        root = ET.fromstring(zf.read("word/document.xml"))
        media = [n for n in names if n.startswith("word/media/") and not n.endswith("/")]
        embeds = [n for n in names if n.startswith("word/embeddings/") and not n.endswith("/")]
        return DocxProbe(
            paragraphs=_count_xml(root, W_NS, "p"),
            tables=_count_xml(root, W_NS, "tbl"),
            emphasis_marks=_count_xml(root, W_NS, "em"),
            underlines=_count_xml(root, W_NS, "u"),
            math_objects=_count_xml(root, M_NS, "oMath"),
            media_files=len(media),
            embedded_files=len(embeds),
        )

def probe_file(path: Path) -> dict:
    ext = path.suffix.lower()
    if ext == ".pdf":
        return {"kind": "pdf", **asdict(probe_pdf(path))}
    if ext == ".docx":
        return {"kind": "docx", **asdict(probe_docx(path))}
    if ext == ".doc":
        return {"kind": "legacy_doc", "needs_conversion": True}
    if ext in {".png", ".jpg", ".jpeg"}:
        return {"kind": "image", "needs_ocr": True}
    return {"kind": "unsupported"}

__all__ = [
    "PdfProbe",
    "DocxProbe",
    "classify_pdf_sample",
    "probe_pdf",
    "probe_docx",
    "probe_file",
]

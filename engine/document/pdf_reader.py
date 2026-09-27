from __future__ import annotations

from pathlib import Path

from engine.document.model import DocumentAst, paragraph_block, text_node, unsupported_block


def read_pdf_document(path: Path) -> DocumentAst:
    """Read text-bearing PDF blocks while preserving page and bounding-box provenance.

    OCR is deliberately not performed here. Pages without reliable text remain explicit
    unsupported blocks so a later slow lane can replace them with OCR-derived content.
    """
    import fitz

    blocks: list[dict] = []
    warnings: list[str] = []

    with fitz.open(path) as doc:
        for page_index, page in enumerate(doc, start=1):
            extracted = page.get_text("blocks", sort=True)
            text_chars = 0
            for block_index, item in enumerate(extracted):
                if len(item) < 7:
                    continue
                x0, y0, x1, y1, text, _block_no, block_type = item[:7]
                if block_type != 0:
                    continue
                text = str(text or "").strip()
                if not text:
                    continue
                text_chars += len(text)
                blocks.append(paragraph_block(
                    f"pdf/page/{page_index}/block/{block_index}",
                    [text_node(text)],
                    page=page_index,
                    bbox=(x0, y0, x1, y1),
                ))

            if text_chars < 80:
                blocks.append(unsupported_block(
                    f"pdf/page/{page_index}",
                    "ocr_required",
                    page=page_index,
                ))
                warnings.append("ocr_required")

            if page.get_images(full=True):
                warnings.append("pdf_images_present")

    return DocumentAst(
        source_format="pdf",
        blocks=tuple(blocks),
        warnings=tuple(sorted(set(warnings))),
    )

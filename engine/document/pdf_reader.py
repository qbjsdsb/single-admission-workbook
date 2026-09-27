from __future__ import annotations

from pathlib import Path

from engine.document.model import DocumentAst, paragraph_block, text_node, unsupported_block


def read_pdf_document_with_pages(path: Path) -> tuple[DocumentAst, list[dict]]:
    """Read a PDF once and return both Document AST and page-level intake facts."""
    import fitz

    blocks: list[dict] = []
    warnings: list[str] = []
    pages: list[dict] = []

    with fitz.open(path) as doc:
        for page_index, page in enumerate(doc, start=1):
            extracted = page.get_text("blocks", sort=True)
            text_chars = 0
            page_text: list[str] = []

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
                page_text.append(text)
                blocks.append(paragraph_block(
                    f"pdf/page/{page_index}/block/{block_index}",
                    [text_node(text)],
                    page=page_index,
                    bbox=(x0, y0, x1, y1),
                ))

            # Displayed images include inline images; resource tables can omit them.
            images = len(page.get_image_info())
            drawings = len(page.get_drawings())
            annotations = sum(1 for _ in page.annots())
            visual_reasons = []
            if images:
                visual_reasons.append("raster_content")
            if drawings:
                visual_reasons.append("vector_content")
            if annotations:
                visual_reasons.append("annotations")
            needs_ocr = text_chars < 80
            pages.append({
                "page": page_index,
                "text": "\n".join(page_text),
                "images": images,
                "needs_ocr": needs_ocr,
                "needs_visual_review": bool(visual_reasons) or needs_ocr,
                "visual_reasons": visual_reasons + (["low_text"] if needs_ocr else []),
                "drawings": drawings,
                "annotations": annotations,
            })

            if needs_ocr:
                blocks.append(unsupported_block(
                    f"pdf/page/{page_index}",
                    "ocr_required",
                    page=page_index,
                ))
                warnings.append("ocr_required")
            if visual_reasons:
                blocks.append(unsupported_block(
                    f"pdf/page/{page_index}/visual",
                    "pdf_visual_content_requires_review",
                    page=page_index,
                ))
                warnings.append("pdf_visual_content_requires_review")
            if images:
                warnings.append("pdf_images_present")

    return (
        DocumentAst(
            source_format="pdf",
            blocks=tuple(blocks),
            warnings=tuple(sorted(set(warnings))),
        ),
        pages,
    )


def read_pdf_document(path: Path) -> DocumentAst:
    return read_pdf_document_with_pages(path)[0]

#!/usr/bin/env python3
"""Preserve suspect PDF pages for visual/OCR review without approving their content."""
import argparse
import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.document.pdf_reader import read_pdf_document_with_pages
from engine.pipeline.intake import write_json


def prepare(source: Path, out: Path, dpi: int = 180) -> dict:
    import fitz
    if not 72 <= dpi <= 300:
        raise ValueError('dpi must be between 72 and 300')
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    # Separate source revisions and render settings; never reuse stale page images.
    destination = out / source_hash / f'dpi-{dpi}'
    destination.mkdir(parents=True, exist_ok=True)
    _, pages = read_pdf_document_with_pages(source)
    records = []
    with fitz.open(source) as document:
        for facts in pages:
            record = {
                'page': facts['page'], 'reasons': facts['visual_reasons'],
                'status': 'pending_visual_review' if facts['needs_visual_review'] else 'text_extraction_only',
                'handwriting': 'not_classified',
                'text': facts['text'],
            }
            if facts['needs_visual_review']:
                image_path = destination / f"page-{facts['page']:04d}.png"
                # Reuse intact renders, recover interrupted or corrupted output.
                valid = False
                if image_path.exists():
                    try:
                        fitz.Pixmap(str(image_path))
                        valid = True
                    except Exception:
                        pass
                if not valid:
                    temporary = image_path.with_suffix('.tmp.png')
                    document[facts['page'] - 1].get_pixmap(dpi=dpi, alpha=False, annots=True).save(temporary)
                    temporary.replace(image_path)
                record['original_page_image'] = image_path.name
                record['image_sha256'] = hashlib.sha256(image_path.read_bytes()).hexdigest()
            records.append(record)
    manifest = {
        'version': 1, 'source_sha256': source_hash, 'dpi': dpi,
        'status': 'review_only_not_publishable',
        'page_count': len(records),
        'visual_review_pages': sum(p['status'] == 'pending_visual_review' for p in records),
        'pages': records,
    }
    write_json(destination / 'manifest.json', manifest)
    return {'manifest': str(destination / 'manifest.json'),
            'pages': len(records), 'visual_review_pages': manifest['visual_review_pages']}


if __name__ == '__main__':
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--dpi', type=int, default=180)
    args = parser.parse_args()
    print(json.dumps(prepare(args.source, args.out, args.dpi), indent=2))

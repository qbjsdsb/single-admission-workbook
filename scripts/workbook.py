#!/usr/bin/env python3
"""Private intake or validated eight-edition rendering. Never uploads source data."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.pipeline.intake import intake, write_json


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest='command', required=True)
    ingest = commands.add_parser('intake')
    ingest.add_argument('archive', type=Path)
    ingest.add_argument('--out', type=Path, default=ROOT / 'build/private/intake')
    ingest.add_argument('--workers', type=int, default=4)
    build = commands.add_parser('build')
    build.add_argument('dataset', type=Path, help='JSON with questions, ledger and curriculum')
    build.add_argument('--out', type=Path, default=ROOT / 'build/eight-books')
    build.add_argument('--compile', action='store_true')
    args = parser.parse_args()
    if args.command == 'intake':
        print(json.dumps(intake(args.archive, args.out, args.workers), ensure_ascii=False, indent=2))
        return
    from engine.pipeline.books import prepare
    data = json.loads(args.dataset.read_text(encoding='utf-8'))
    # Clear the completion marker first, including when subsequent validation fails.
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / 'build-complete.json').unlink(missing_ok=True)
    try:
        books = prepare(data['questions'], data['ledger'], data['curriculum'], args.out)
        if args.compile:
            for book in books:
                folder = (args.out / book['book_id']).resolve()
                digest = (folder / 'build-id.txt').read_text()
                stamp = folder / 'compiled-id.txt'
                pdf = folder / 'main.pdf'
                if not (stamp.exists() and stamp.read_text() == digest and pdf.exists()):
                    stamp.unlink(missing_ok=True)
                    for _ in range(2):
                        result = subprocess.run(['xelatex', '-no-shell-escape', '-interaction=nonstopmode',
                                                 '-halt-on-error', 'main.tex'], cwd=folder,
                                                capture_output=True, timeout=180)
                        if result.returncode:
                            raise ValueError(f"{book['book_id']}: compile failed; inspect main.log")
                    log = (folder / 'main.log').read_text(errors='replace')
                    if any(x in log for x in ('Overfull \\hbox', 'Overfull \\vbox', 'Missing character:')):
                        raise ValueError(f"{book['book_id']}: overflow or missing glyph; inspect main.log")
                    import fitz
                    with fitz.open(pdf) as document:
                        if not len(document) or any(not p.get_text().strip() for p in document):
                            raise ValueError(f"{book['book_id']}: empty PDF/page")
                    stamp.write_text(digest)
            write_json(args.out / 'build-complete.json', {'books': 8, 'pdfs': 8,
                         'status': 'compiled_not_publication_approved', 'visual_review': 'required'})
        print(f'Prepared {len(books)} editions. Publication approval remains separate from compilation.')
    except (ValueError, KeyError) as exc:
        write_json(args.out / 'blocked.json', {'status': 'blocked', 'reason': str(exc)})
        print(str(exc), file=sys.stderr)
        return 2
    (args.out / 'blocked.json').unlink(missing_ok=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys

import fitz
import jsonschema

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.pipeline.editorial_batch import prepare_editorial_batch
from engine.render.compile import compile_xelatex


A4_WIDTH = 595.28
A4_HEIGHT = 841.89
PAGE_TOLERANCE = 2.0


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _compile_and_review(folder: Path, review_root: Path) -> int:
    compile_xelatex(folder)

    log = (folder / "main.log").read_text(
        encoding="utf-8",
        errors="replace",
    )
    blockers = [
        token
        for token in (
            r"Overfull \hbox",
            r"Overfull \vbox",
            "Missing character:",
        )
        if token in log
    ]
    if blockers:
        raise ValueError(
            f"{folder.name}: print QA blocker: {', '.join(blockers)}"
        )

    pdf = folder / "main.pdf"
    edition_review = review_root / folder.name
    edition_review.mkdir(parents=True, exist_ok=True)

    with fitz.open(pdf) as document:
        if not len(document):
            raise ValueError(f"{folder.name}: empty PDF")

        for index, page in enumerate(document, start=1):
            if not page.get_text().strip():
                raise ValueError(f"{folder.name}: empty page {index}")

            width, height = page.rect.width, page.rect.height
            if (
                abs(width - A4_WIDTH) > PAGE_TOLERANCE
                or abs(height - A4_HEIGHT) > PAGE_TOLERANCE
            ):
                raise ValueError(
                    f"{folder.name}: page {index} is not A4 "
                    f"({width:.1f}x{height:.1f})"
                )

            pixmap = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
            pixmap.save(edition_review / f"page-{index:03d}.png")

        return len(document)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare a small private AI-editorial batch directly for "
            "student/teacher A4 visual review."
        )
    )
    parser.add_argument("batch", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--compile", action="store_true")
    args = parser.parse_args()

    try:
        summary = prepare_editorial_batch(
            load_json(args.batch),
            args.out,
        )

        if args.compile:
            if not shutil.which("xelatex"):
                raise ValueError("xelatex is required when --compile is used")

            pages = {}
            review_root = args.out / "visual-review"
            for edition in summary["editions"]:
                folder = args.out / edition["book_id"]
                pages[edition["edition"]] = _compile_and_review(
                    folder,
                    review_root,
                )

            summary = {
                **summary,
                "pages": pages,
                "visual_review_dir": "visual-review",
                "status": "compiled_editorial_batch_visual_review_required",
            }
            (args.out / "batch-build.json").write_text(
                json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    except (jsonschema.ValidationError, KeyError, ValueError) as exc:
        args.out.mkdir(parents=True, exist_ok=True)
        blocked = {
            "status": "blocked",
            "reason": str(exc),
        }
        (args.out / "blocked.json").write_text(
            json.dumps(blocked, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

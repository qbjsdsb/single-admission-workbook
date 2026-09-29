#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys

import fitz

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.pipeline.english_stage import (
    assemble_english_stage_canonical,
    curriculum_from_english_taxonomy,
)
from engine.pipeline.sample_render import prepare_private_sample
from engine.render.compile import compile_xelatex


A4_WIDTH = 595.28
A4_HEIGHT = 841.89
PAGE_TOLERANCE = 2.0


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _qa_pdf(pdf: Path) -> int:
    with fitz.open(pdf) as document:
        if not len(document):
            raise ValueError(f"{pdf.parent.name}: empty PDF")
        for index, page in enumerate(document, start=1):
            text = page.get_text().strip()
            if not text:
                raise ValueError(f"{pdf.parent.name}: empty page {index}")
            width, height = page.rect.width, page.rect.height
            if (
                abs(width - A4_WIDTH) > PAGE_TOLERANCE
                or abs(height - A4_HEIGHT) > PAGE_TOLERANCE
            ):
                raise ValueError(
                    f"{pdf.parent.name}: page {index} is not A4 ({width:.1f}x{height:.1f})"
                )
        return len(document)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Assemble the current strict English verified/scored groups into a "
            "quality-gated two-book stage preview."
        )
    )
    parser.add_argument("review_dir", type=Path)
    parser.add_argument("verified_dir", type=Path)
    parser.add_argument(
        "--taxonomy",
        type=Path,
        default=ROOT / "taxonomy" / "english.v01.yaml",
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--compile", action="store_true")
    parser.add_argument("--title-suffix", default="阶段全册")
    args = parser.parse_args()

    try:
        canonical, report = assemble_english_stage_canonical(
            args.review_dir,
            args.verified_dir,
        )
        curriculum = curriculum_from_english_taxonomy(args.taxonomy)

        args.out.mkdir(parents=True, exist_ok=True)
        _write_json(args.out / "canonical-stage.private.json", canonical)
        _write_json(args.out / "curriculum.json", curriculum)
        _write_json(args.out / "stage-assembly.json", report)

        sample = prepare_private_sample(
            canonical,
            curriculum,
            args.out / "books",
            require_teacher_analysis=True,
            title_suffix=args.title_suffix,
        )

        pages = {}
        if args.compile:
            if not shutil.which("xelatex"):
                raise ValueError("xelatex is required when --compile is used")
            for edition in sample["editions"]:
                folder = args.out / "books" / edition["book_id"]
                compile_xelatex(folder)
                log = (folder / "main.log").read_text(
                    encoding="utf-8",
                    errors="replace",
                )
                blockers = [
                    token
                    for token in (
                        "Overfull \\hbox",
                        "Overfull \\vbox",
                        "Missing character:",
                    )
                    if token in log
                ]
                if blockers:
                    raise ValueError(
                        f"{folder.name}: print QA blocker: {', '.join(blockers)}"
                    )
                pages[edition["edition"]] = _qa_pdf(folder / "main.pdf")

        result = {
            "schema_version": 1,
            "subject": "english",
            "stage_assembly": report,
            "sample": sample,
            "pages": pages,
            "status": (
                "compiled_english_stage_visual_review_required"
                if args.compile
                else "prepared_english_stage_not_publication_approved"
            ),
        }
        _write_json(args.out / "english-stage-build.json", result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (KeyError, OSError, ValueError) as exc:
        args.out.mkdir(parents=True, exist_ok=True)
        _write_json(
            args.out / "blocked.json",
            {"status": "blocked", "reason": str(exc)},
        )
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

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

from engine.pipeline.sample_render import prepare_private_sample
from engine.render.compile import compile_xelatex


A4_WIDTH = 595.28
A4_HEIGHT = 841.89
PAGE_TOLERANCE = 2.0


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _page_count_and_geometry(pdf: Path) -> int:
    with fitz.open(pdf) as document:
        if not len(document):
            raise ValueError(f"{pdf.parent.name}: empty PDF")
        for index, page in enumerate(document, start=1):
            if not page.get_text().strip():
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
        description="Render a private Canonical Draft sample through the production XeLaTeX path."
    )
    parser.add_argument("canonical_draft", type=Path)
    parser.add_argument("curriculum", type=Path)
    parser.add_argument("--ids", type=Path, help="Optional newline-separated canonical IDs")
    parser.add_argument("--allow-missing-analysis", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--title-suffix",
        default="样章",
        help="Visible book-title suffix, e.g. 样章 or 阶段全册; use empty string for none.",
    )
    parser.add_argument("--compile", action="store_true")
    args = parser.parse_args()

    requested = None
    if args.ids:
        requested = [
            line.strip()
            for line in args.ids.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    try:
        summary = prepare_private_sample(
            load_json(args.canonical_draft),
            load_json(args.curriculum),
            args.out,
            requested_ids=requested,
            require_teacher_analysis=not args.allow_missing_analysis,
            title_suffix=args.title_suffix,
        )

        if args.compile:
            if not shutil.which("xelatex"):
                raise ValueError("xelatex is required when --compile is used")

            pages = {}
            for edition in summary["editions"]:
                folder = args.out / edition["book_id"]
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
                pages[edition["edition"]] = _page_count_and_geometry(
                    folder / "main.pdf"
                )

            summary = {
                **summary,
                "pages": pages,
                "status": "compiled_private_sample_visual_review_required",
            }

        (args.out / "sample-build.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    except (KeyError, ValueError) as exc:
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "blocked.json").write_text(
            json.dumps(
                {"status": "blocked", "reason": str(exc)},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

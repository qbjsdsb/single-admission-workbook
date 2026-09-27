#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.parse.docx_structure import extract_structure


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate DOCX media/OLE structure without exposing payloads.")
    parser.add_argument("docx", type=Path)
    args = parser.parse_args()

    structure = extract_structure(args.docx)
    assets = structure.get("assets") or {}
    ole = [
        obj
        for block in structure.get("blocks") or []
        for obj in (block.get("ole_objects") or [])
    ]
    drawings = [
        obj
        for block in structure.get("blocks") or []
        for obj in (block.get("drawings") or [])
    ]

    summary = {
        "asset_relationships": len(assets),
        "asset_extensions": dict(sorted(Counter(
            str(a.get("extension") or "") for a in assets.values()
        ).items())),
        "ole_objects": len(ole),
        "equation_ole_objects": sum(1 for x in ole if x.get("is_equation")),
        "ole_prog_ids": dict(sorted(Counter(
            str(x.get("prog_id") or "") for x in ole
        ).items())),
        "drawingml_images": len(drawings),
        "ole_with_preview": sum(1 for x in ole if x.get("preview_relationship_id")),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

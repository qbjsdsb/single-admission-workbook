#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.pipeline.batch_review import review_intake_directory
from engine.pipeline.production_snapshot import (
    build_production_snapshot,
    render_production_snapshot_markdown,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Batch-review every exact English/Politics pair from an existing private intake cache."
    )
    parser.add_argument("intake_dir", type=Path)
    parser.add_argument("--subject", required=True, choices=["english", "politics"])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    summary = review_intake_directory(
        args.intake_dir,
        args.out,
        subject=args.subject,
    )

    snapshot = build_production_snapshot(args.out)
    (args.out / "production-snapshot.json").write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (args.out / "production-snapshot.md").write_text(
        render_production_snapshot_markdown(snapshot),
        encoding="utf-8",
    )

    print(json.dumps({
        **summary,
        "production_snapshot": {
            "states": snapshot["states"],
            "priority_counts": snapshot["priority_counts"],
            "next_source_ids": snapshot["next_source_ids"],
        },
    }, ensure_ascii=False, indent=2))
    return 0 if summary["failed_student_groups"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())

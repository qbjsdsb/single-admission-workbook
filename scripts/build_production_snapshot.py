#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.pipeline.production_snapshot import (
    build_production_snapshot,
    render_production_snapshot_markdown,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a compact production snapshot from a private batch-review directory."
    )
    parser.add_argument("review_dir", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    try:
        snapshot = build_production_snapshot(args.review_dir)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "production-snapshot.json").write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (args.out / "production-snapshot.md").write_text(
        render_production_snapshot_markdown(snapshot),
        encoding="utf-8",
    )
    print(json.dumps({
        "subject": snapshot["subject"],
        "source_groups": snapshot["source_groups"],
        "candidate_units": snapshot["candidate_units"],
        "states": snapshot["states"],
        "priority_counts": snapshot["priority_counts"],
        "next_source_ids": snapshot["next_source_ids"],
        "status": snapshot["status"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

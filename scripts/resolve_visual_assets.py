#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.pipeline.visual_resolution import resolve_safe_single_visuals


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Resolve only hash-bound single source visuals in a scored verified bank."
    )
    parser.add_argument("bank", type=Path)
    parser.add_argument("asset_manifest", type=Path)
    parser.add_argument("asset_dir", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--audit", type=Path)
    args = parser.parse_args()

    bank = json.loads(args.bank.read_text(encoding="utf-8"))
    manifest = json.loads(args.asset_manifest.read_text(encoding="utf-8"))
    result = resolve_safe_single_visuals(
        bank,
        manifest,
        asset_dir=args.asset_dir,
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(result["bank"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    audit_path = args.audit or args.out.with_name(args.out.stem + "-visual-audit.json")
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(
        json.dumps(result["audit"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps({
        "resolved": result["audit"]["resolved"],
        "deferred": result["audit"]["deferred"],
        "bank": str(args.out),
        "audit": str(audit_path),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.pipeline.batch_review import review_intake_directory
from engine.pipeline.production_snapshot import (
    build_production_snapshot,
    render_production_snapshot_markdown,
)


FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_zip_member(info: zipfile.ZipInfo) -> PurePosixPath:
    path = PurePosixPath(info.filename)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ValueError(f"unsafe checkpoint member: {info.filename}")
    mode = (info.external_attr >> 16) & 0o170000
    if mode == stat.S_IFLNK:
        raise ValueError(f"checkpoint symlink is not allowed: {info.filename}")
    return path


def _safe_extract(checkpoint_zip: Path, destination: Path) -> None:
    with zipfile.ZipFile(checkpoint_zip) as archive:
        for info in archive.infolist():
            relative = _validate_zip_member(info)
            target = destination.joinpath(*relative.parts)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, target.open("wb") as sink:
                shutil.copyfileobj(source, sink)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_deterministic_zip(source_root: Path, out_zip: Path) -> None:
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        out_zip,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for path in sorted(
            (item for item in source_root.rglob("*") if item.is_file()),
            key=lambda item: item.relative_to(source_root).as_posix(),
        ):
            relative = path.relative_to(source_root).as_posix()
            info = zipfile.ZipInfo(relative, date_time=FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED)


def refresh_checkpoint(
    checkpoint_zip: Path,
    out_zip: Path,
    *,
    subject: str,
) -> dict[str, object]:
    """Rerun downstream review from a private cached-intake checkpoint.

    Raw source files are not required. The checkpoint's private intake metadata
    and Document AST cache are preserved; the old batch-review directory is
    replaced by results from the current code. The returned archive remains
    private and must never be committed to the public repository.
    """
    checkpoint_zip = checkpoint_zip.resolve()
    out_zip = out_zip.resolve()
    if subject not in {"english", "politics"}:
        raise ValueError("checkpoint rerun currently supports english or politics")
    if checkpoint_zip == out_zip:
        raise ValueError("output checkpoint must not overwrite the input archive")
    if not checkpoint_zip.is_file():
        raise FileNotFoundError(checkpoint_zip)

    input_sha256 = _sha256(checkpoint_zip)

    with tempfile.TemporaryDirectory(prefix="workbook-checkpoint-") as temp:
        workspace = Path(temp)
        _safe_extract(checkpoint_zip, workspace)

        subject_root = workspace / "production" / subject
        intake = subject_root / "intake"
        required = [
            intake / "sources.private.json",
            intake / "pairs.private.json",
            intake / "cache",
        ]
        missing = [str(path.relative_to(workspace)) for path in required if not path.exists()]
        if missing:
            raise ValueError(
                "checkpoint is missing cached intake components: " + ", ".join(missing)
            )

        review = subject_root / "batch-review"
        if review.exists():
            shutil.rmtree(review)
        review.mkdir(parents=True, exist_ok=True)

        summary = review_intake_directory(
            intake,
            review,
            subject=subject,
        )
        snapshot = build_production_snapshot(review)
        _write_json(review / "production-snapshot.json", snapshot)
        (review / "production-snapshot.md").write_text(
            render_production_snapshot_markdown(snapshot),
            encoding="utf-8",
        )

        refresh_summary = {
            "schema_version": 1,
            "subject": subject,
            "input_checkpoint_sha256": input_sha256,
            "student_source_groups": int(summary.get("student_source_groups") or 0),
            "companion_sources": int(summary.get("companion_sources") or 0),
            "candidate_units": int(summary.get("candidate_units") or 0),
            "failed_student_groups": int(summary.get("failed_student_groups") or 0),
            "states": summary.get("states") or {},
            "issue_counts": summary.get("issue_counts") or {},
            "verification_aggregate_counts": summary.get(
                "verification_aggregate_counts"
            ) or {},
            "production_snapshot": {
                "priority_counts": snapshot.get("priority_counts") or {},
                "next_source_ids": snapshot.get("next_source_ids") or [],
            },
            "status": "private_checkpoint_refreshed_not_release_approval",
        }
        _write_json(subject_root / "refresh-summary.private.json", refresh_summary)

        # Write only the subject production tree. The archive therefore carries
        # the cached intake needed for the next rerun plus the refreshed review.
        _write_deterministic_zip(workspace, out_zip)

    return {
        **refresh_summary,
        "output_checkpoint": str(out_zip),
        "output_checkpoint_sha256": _sha256(out_zip),
        "output_bytes": out_zip.stat().st_size,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Refresh a private English/Politics production checkpoint from its "
            "cached Document AST intake without reparsing the raw source corpus."
        )
    )
    parser.add_argument("checkpoint_zip", type=Path)
    parser.add_argument(
        "--subject",
        required=True,
        choices=["english", "politics"],
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    result = refresh_checkpoint(
        args.checkpoint_zip,
        args.out,
        subject=args.subject,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["failed_student_groups"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())

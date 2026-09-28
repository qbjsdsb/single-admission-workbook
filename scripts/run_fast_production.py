#!/usr/bin/env python3
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _load_optional(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _run(command: list[str]) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return {
        "returncode": completed.returncode,
        "stdout_tail": "\n".join(completed.stdout.splitlines()[-20:]),
        "stderr_tail": "\n".join(completed.stderr.splitlines()[-20:]),
    }


def run_fast_production(
    intake_dir: Path,
    out_dir: Path,
    *,
    subject: str,
    workers: int = 4,
) -> dict[str, Any]:
    if workers < 1:
        raise ValueError("workers must be >= 1")

    paired_dir = out_dir / "paired-review"
    embedded_dir = out_dir / "embedded"
    paired_verified_dir = out_dir / "paired-verified"
    out_dir.mkdir(parents=True, exist_ok=True)

    paired_command = [
        sys.executable,
        str(ROOT / "scripts" / "review_intake_pairs.py"),
        str(intake_dir),
        "--subject",
        subject,
        "--out",
        str(paired_dir),
        "--workers",
        str(workers),
    ]
    embedded_command = [
        sys.executable,
        str(ROOT / "scripts" / "build_embedded_source_batch.py"),
        str(intake_dir),
        "--subject",
        subject,
        "--out",
        str(embedded_dir),
    ]

    # Paired and unpaired lanes read the same immutable cache but write separate
    # outputs, so they are safe to run concurrently.
    with ThreadPoolExecutor(max_workers=2) as executor:
        paired_future = executor.submit(_run, paired_command)
        embedded_future = executor.submit(_run, embedded_command)
        paired_run = paired_future.result()
        embedded_run = embedded_future.result()

    paired_summary = _load_optional(paired_dir / "batch-summary.json")
    embedded_summary = _load_optional(embedded_dir / "embedded-source-summary.json")

    hard_failures: list[str] = []
    if paired_summary is None:
        hard_failures.append("paired_review_summary_missing")
    elif int(paired_summary.get("failed_student_groups") or 0) > 0:
        hard_failures.append("paired_review_group_failures")
    if embedded_summary is None:
        hard_failures.append("embedded_source_summary_missing")
    if paired_run["returncode"] not in {0, 2}:
        hard_failures.append("paired_review_process_failed")
    if embedded_run["returncode"] != 0:
        hard_failures.append("embedded_source_process_failed")

    strict_run: dict[str, Any] | None = None
    strict_summary: dict[str, Any] | None = None
    if (
        paired_summary is not None
        and int(paired_summary.get("student_source_groups") or 0) > 0
        and "paired_review_group_failures" not in hard_failures
    ):
        strict_command = [
            sys.executable,
            str(ROOT / "scripts" / "build_strict_verified_batch.py"),
            str(paired_dir),
            "--intake",
            str(intake_dir),
            "--out",
            str(paired_verified_dir),
        ]
        strict_run = _run(strict_command)
        strict_summary = _load_optional(
            paired_verified_dir / "batch-verification-summary.json"
        )
        if strict_summary is None:
            hard_failures.append("paired_strict_summary_missing")
        # rc=2 means evidence/content blockers remain; it is not an
        # infrastructure failure and should still produce a useful checkpoint.
        if strict_run["returncode"] not in {0, 2}:
            hard_failures.append("paired_strict_process_failed")

    paired_verified = int((strict_summary or {}).get("verified") or 0)
    paired_deferred = int((strict_summary or {}).get("deferred") or 0)
    paired_rejected = int((strict_summary or {}).get("rejected") or 0)
    paired_score_assigned = int((strict_summary or {}).get("score_assigned") or 0)
    paired_score_unresolved = int((strict_summary or {}).get("score_unresolved") or 0)

    embedded_verified = int((embedded_summary or {}).get("verified") or 0)
    embedded_deferred = int((embedded_summary or {}).get("deferred") or 0)
    embedded_score_assigned = int((embedded_summary or {}).get("score_assigned") or 0)
    embedded_score_unresolved = int((embedded_summary or {}).get("score_unresolved") or 0)
    embedded_candidate_blockers = int(
        (embedded_summary or {}).get("candidate_blockers") or 0
    )

    blockers = (
        paired_deferred
        + paired_rejected
        + paired_score_unresolved
        + embedded_deferred
        + embedded_score_unresolved
        + embedded_candidate_blockers
    )

    if hard_failures:
        status = "hard_failure"
    elif blockers:
        status = "complete_with_content_blockers"
    else:
        status = "verified_scored_pool_ready"

    summary = {
        "schema_version": 1,
        "subject": subject,
        "status": status,
        "hard_failures": sorted(set(hard_failures)),
        "paired": {
            "source_groups": int((paired_summary or {}).get("student_source_groups") or 0),
            "candidate_units": int((paired_summary or {}).get("candidate_units") or 0),
            "verified": paired_verified,
            "deferred": paired_deferred,
            "rejected": paired_rejected,
            "score_assigned": paired_score_assigned,
            "score_unresolved": paired_score_unresolved,
        },
        "embedded": {
            "source_files": int((embedded_summary or {}).get("source_files") or 0),
            "candidate_units": int((embedded_summary or {}).get("candidate_units") or 0),
            "verified": embedded_verified,
            "deferred": embedded_deferred,
            "score_assigned": embedded_score_assigned,
            "score_unresolved": embedded_score_unresolved,
            "candidate_blockers": embedded_candidate_blockers,
        },
        "combined": {
            "verified": paired_verified + embedded_verified,
            "deferred": paired_deferred + embedded_deferred,
            "rejected": paired_rejected,
            "score_assigned": paired_score_assigned + embedded_score_assigned,
            "score_unresolved": paired_score_unresolved + embedded_score_unresolved,
            "content_blockers": blockers,
        },
    }
    (out_dir / "fast-production-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    if hard_failures:
        for name, stage in (
            ("paired", paired_run),
            ("embedded", embedded_run),
            ("strict", strict_run),
        ):
            if stage and stage.get("returncode") not in {0, 2}:
                print(f"[{name}] {stage.get('stderr_tail') or stage.get('stdout_tail')}", file=sys.stderr)

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the highest-confidence production lanes as far as source evidence "
            "allows, preserving blockers instead of silently weakening gates."
        )
    )
    parser.add_argument("intake_dir", type=Path)
    parser.add_argument("--subject", required=True, choices=["english", "politics"])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    try:
        summary = run_fast_production(
            args.intake_dir,
            args.out,
            subject=args.subject,
            workers=args.workers,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 2 if summary["status"] == "hard_failure" else 0


if __name__ == "__main__":
    raise SystemExit(main())

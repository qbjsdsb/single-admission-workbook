from __future__ import annotations

from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
from typing import Any, Mapping


PRIORITY_KEYS = (0, 1, 2, 3)


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _priority_key(raw: str) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 9


def build_production_snapshot(review_dir: Path) -> dict[str, Any]:
    """Build a compact production dashboard from one subject batch review.

    The snapshot deliberately omits source paths and question text. It is meant
    to answer "how much real content is ready, blocked, or next in line?" without
    exposing private corpus payloads or pretending to grant publication approval.
    """
    summary = _read_json(review_dir / "batch-summary.json")
    queue_path = review_dir / "editorial-queue.csv"

    by_source: dict[str, list[dict[str, str]]] = defaultdict(list)
    with queue_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            source_id = str(row.get("student_source_id") or "").strip()
            if not source_id:
                raise ValueError("editorial queue row missing student_source_id")
            by_source[source_id].append(row)

    total_rows = sum(len(rows) for rows in by_source.values())
    expected_units = int(summary.get("candidate_units") or 0)
    if total_rows != expected_units:
        raise ValueError(
            f"editorial queue candidate count mismatch: {total_rows} != {expected_units}"
        )

    priority_counts: Counter[int] = Counter()
    state_counts: Counter[str] = Counter()
    issue_counts: Counter[str] = Counter()
    sources_out: list[dict[str, Any]] = []

    for source_id, rows in sorted(by_source.items()):
        source_priorities: Counter[int] = Counter()
        source_states: Counter[str] = Counter()
        source_issues: Counter[str] = Counter()

        for row in rows:
            priority = _priority_key(row.get("priority"))
            state = str(row.get("state") or "")
            priority_counts[priority] += 1
            source_priorities[priority] += 1
            state_counts[state] += 1
            source_states[state] += 1

            for code in str(row.get("issue_codes") or "").split("|"):
                code = code.strip()
                if code:
                    issue_counts[code] += 1
                    source_issues[code] += 1

        pending = [p for p in PRIORITY_KEYS if source_priorities[p] > 0]
        next_priority = min(pending) if pending else None

        sources_out.append({
            "source_id": source_id,
            "candidate_units": len(rows),
            "blocked": source_states.get("blocked", 0),
            "needs_review": source_states.get("needs_review", 0),
            "ready_for_sample": source_states.get("ready_for_sample", 0),
            "priority_counts": {
                f"P{priority}": source_priorities.get(priority, 0)
                for priority in PRIORITY_KEYS
            },
            "next_priority": None if next_priority is None else f"P{next_priority}",
            "top_issue_codes": [
                code for code, _count in source_issues.most_common(3)
            ],
        })

    sources_out.sort(
        key=lambda item: (
            9 if item["next_priority"] is None else int(item["next_priority"][1:]),
            -item["blocked"],
            -item["needs_review"],
            item["source_id"],
        )
    )

    if dict(sorted(state_counts.items())) != dict(sorted((summary.get("states") or {}).items())):
        raise ValueError("editorial queue state totals do not match batch summary")

    return {
        "schema_version": 1,
        "subject": summary.get("subject"),
        "source_groups": int(summary.get("student_source_groups") or 0),
        "candidate_units": expected_units,
        "failed_source_groups": int(summary.get("failed_student_groups") or 0),
        "states": dict(sorted(state_counts.items())),
        "priority_counts": {
            f"P{priority}": priority_counts.get(priority, 0)
            for priority in PRIORITY_KEYS
        },
        "issue_counts": dict(sorted(issue_counts.items())),
        "verification_aggregate_counts": dict(
            sorted((summary.get("verification_aggregate_counts") or {}).items())
        ),
        "sources": sources_out,
        "next_source_ids": [
            item["source_id"]
            for item in sources_out
            if item["next_priority"] is not None
        ][:10],
        "status": "production_snapshot_not_release_approval",
    }


def render_production_snapshot_markdown(snapshot: Mapping[str, Any]) -> str:
    states = snapshot.get("states") or {}
    priorities = snapshot.get("priority_counts") or {}
    issues = snapshot.get("issue_counts") or {}

    lines = [
        f"# {snapshot.get('subject', 'unknown')} production snapshot",
        "",
        "> Private-corpus progress summary. No source paths or question text are included.",
        "",
        "## Overall",
        "",
        f"- source groups: {snapshot.get('source_groups', 0)}",
        f"- candidate units: {snapshot.get('candidate_units', 0)}",
        f"- failed source groups: {snapshot.get('failed_source_groups', 0)}",
        f"- ready for sample: {states.get('ready_for_sample', 0)}",
        f"- needs review: {states.get('needs_review', 0)}",
        f"- blocked: {states.get('blocked', 0)}",
        "",
        "## Priority queue",
        "",
    ]
    for priority in PRIORITY_KEYS:
        lines.append(f"- P{priority}: {priorities.get(f'P{priority}', 0)}")

    lines.extend(["", "## Top issues", ""])
    if issues:
        for code, count in sorted(
            issues.items(),
            key=lambda item: (-int(item[1]), item[0]),
        )[:10]:
            lines.append(f"- {code}: {count}")
    else:
        lines.append("- none")

    lines.extend(["", "## Next source groups", ""])
    next_ids = snapshot.get("next_source_ids") or []
    if next_ids:
        for source_id in next_ids:
            lines.append(f"- {source_id}")
    else:
        lines.append("- none")

    lines.extend([
        "",
        "This snapshot is operational triage only. It does not verify answers or approve publication.",
        "",
    ])
    return "\n".join(lines)

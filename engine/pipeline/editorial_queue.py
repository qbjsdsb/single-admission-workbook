from __future__ import annotations

from typing import Any, Mapping


PRIORITY = {
    "answer_conflict": 0,
    "score_conflict": 0,
    "candidate_structure": 1,
    "rich_content": 1,
    "answer_verification": 1,
    "score_missing": 2,
    "classification": 2,
    "teacher_analysis": 3,
}


def _index(items, key):
    return {
        str(item.get(key) or ""): item
        for item in (items or [])
        if str(item.get(key) or "")
    }


def build_editorial_queue(
    candidate_bank: Mapping[str, Any],
    aggregate_review: Mapping[str, Any],
    score_evidence: Mapping[str, Any],
    classification_manifest: Mapping[str, Any],
    *,
    verified_candidate_bank: Mapping[str, Any] | None = None,
    teacher_enrichment: Mapping[str, Any] | None = None,
    require_teacher_analysis: bool = True,
) -> dict[str, Any]:
    """Collapse all pre-publication review work into one deterministic queue."""
    source_id = str(candidate_bank.get("source_id") or "")
    subject = str(candidate_bank.get("subject") or "")

    if aggregate_review.get("candidate_source_id") != source_id:
        raise ValueError("aggregate review source mismatch")
    if score_evidence.get("candidate_source_id") != source_id:
        raise ValueError("score evidence source mismatch")
    if classification_manifest.get("candidate_source_id") != source_id:
        raise ValueError("classification manifest source mismatch")
    if aggregate_review.get("subject") != subject:
        raise ValueError("aggregate review subject mismatch")
    if score_evidence.get("subject") != subject:
        raise ValueError("score evidence subject mismatch")
    if classification_manifest.get("subject") != subject:
        raise ValueError("classification manifest subject mismatch")
    if verified_candidate_bank is not None:
        if verified_candidate_bank.get("candidate_source_id") != source_id:
            raise ValueError("verified candidate bank source mismatch")
        if verified_candidate_bank.get("subject") != subject:
            raise ValueError("verified candidate bank subject mismatch")
    if teacher_enrichment is not None:
        enrichment_source = teacher_enrichment.get("candidate_source_id")
        if enrichment_source not in {None, source_id}:
            raise ValueError("teacher enrichment source mismatch")

    aggregate_by_candidate = _index(aggregate_review.get("rows"), "candidate_id")
    classification_by_candidate = _index(
        classification_manifest.get("decisions"), "candidate_id"
    )
    score_by_section = _index(score_evidence.get("sections"), "section_key")
    teacher_items = _index(
        [] if teacher_enrichment is None else teacher_enrichment.get("items"),
        "candidate_id",
    )
    verified_ids = {
        str(item.get("candidate_id") or "")
        for item in ([] if verified_candidate_bank is None else verified_candidate_bank.get("verified") or [])
        if str(item.get("candidate_id") or "")
    }

    groups_by_id = _index(candidate_bank.get("groups"), "group_id")
    blockers_by_locator: dict[str, list[str]] = {}
    for blocker in candidate_bank.get("blockers") or []:
        locator = str(blocker.get("locator") or "")
        if not locator:
            continue
        blockers_by_locator.setdefault(locator, []).extend(
            str(reason) for reason in blocker.get("reasons") or []
        )

    entries: list[dict[str, Any]] = []

    for candidate in candidate_bank.get("candidates") or []:
        candidate_id = str(candidate.get("candidate_id") or "")
        section_key = str(candidate.get("section_key") or "")
        aggregate = aggregate_by_candidate.get(candidate_id)
        classification = classification_by_candidate.get(candidate_id)
        score = score_by_section.get(section_key)

        issues: list[dict[str, Any]] = []

        def add_issue(code: str, detail: str, action: str) -> None:
            issues.append({
                "code": code,
                "priority": PRIORITY[code],
                "detail": detail,
                "suggested_action": action,
            })

        if candidate.get("status") != "parsed":
            add_issue(
                "candidate_structure",
                ",".join(candidate.get("review_reasons") or [])
                or "candidate structure requires review",
                "review_source_structure",
            )

        relevant_locators = set(str(x) for x in candidate.get("locators") or [])
        group = groups_by_id.get(str(candidate.get("group_id") or ""))
        if group is not None:
            relevant_locators.update(str(x) for x in group.get("locators") or [])
        rich_blockers = [
            (locator, sorted(set(blockers_by_locator[locator])))
            for locator in sorted(relevant_locators & blockers_by_locator.keys())
        ]
        if rich_blockers:
            detail = "; ".join(
                locator + ":" + ",".join(reasons)
                for locator, reasons in rich_blockers
            )
            add_issue(
                "rich_content",
                detail,
                "review_source_visual_rich_content",
            )

        if aggregate is None:
            add_issue(
                "answer_verification",
                "no aggregate answer review",
                "build_or_review_answer_evidence",
            )
        elif aggregate.get("aggregate_status") == "conflict":
            add_issue(
                "answer_conflict",
                "answer variants: " + ", ".join(aggregate.get("answer_variants") or []),
                "resolve_answer_conflict",
            )
        elif candidate_id not in verified_ids:
            aggregate_status = str(aggregate.get("aggregate_status") or "unknown")
            add_issue(
                "answer_verification",
                "verification manifest not approved; machine aggregate=" + aggregate_status,
                "verify_answer_evidence",
            )

        if score is None:
            add_issue(
                "score_missing",
                "section has no score evidence",
                "verify_section_score",
            )
        elif score.get("status") == "conflict":
            add_issue(
                "score_conflict",
                "; ".join(score.get("reasons") or []) or "section score conflict",
                "resolve_score_conflict",
            )
        elif score.get("status") != "usable":
            add_issue(
                "score_missing",
                "section score evidence is incomplete",
                "verify_section_score",
            )

        if classification is None:
            add_issue(
                "classification",
                "no classification decision",
                "classify_taxonomy",
            )
        elif classification.get("decision") != "assign":
            add_issue(
                "classification",
                str(classification.get("note") or "classification deferred"),
                "classify_taxonomy",
            )

        if require_teacher_analysis and not str(teacher_items.get(candidate_id, {}).get("analysis") or "").strip():
            add_issue(
                "teacher_analysis",
                "no non-empty teacher analysis enrichment",
                "review_teacher_analysis",
            )

        issues.sort(key=lambda x: (x["priority"], x["code"], x["detail"]))
        if issues:
            priority = min(issue["priority"] for issue in issues)
            state = "blocked" if priority == 0 else "needs_review"
            next_action = issues[0]["suggested_action"]
        else:
            priority = 9
            state = "ready_for_sample"
            next_action = "no_action"

        entries.append({
            "candidate_id": candidate_id,
            "source_number": candidate.get("source_number"),
            "section_key": section_key,
            "state": state,
            "priority": priority,
            "next_action": next_action,
            "issues": issues,
        })

    entries.sort(key=lambda x: (x["priority"], x["source_number"] or 10**9, x["candidate_id"]))

    counts = {"blocked": 0, "needs_review": 0, "ready_for_sample": 0}
    issue_counts: dict[str, int] = {}
    for entry in entries:
        counts[entry["state"]] += 1
        for issue in entry["issues"]:
            issue_counts[issue["code"]] = issue_counts.get(issue["code"], 0) + 1

    return {
        "schema_version": 1,
        "subject": subject,
        "candidate_source_id": source_id,
        "entries": entries,
        "summary": {
            "total": len(entries),
            **counts,
            "issue_counts": dict(sorted(issue_counts.items())),
        },
    }

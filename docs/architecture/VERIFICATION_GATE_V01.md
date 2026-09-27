# Verification Gate v0.1

This layer reduces manual review without turning machine agreement into an unsupported claim of correctness.

Multiple pairing-review outputs for one student/original source are aggregated by candidate ID.

Aggregate states:

- machine_corroborated: at least two distinct strong companion sources agree on one answer;
- single_source_consistent: one strong companion source provides one answer;
- review_required: evidence is weak, missing, or structurally unresolved;
- conflict: distinct answer values are present.

Machine corroboration is a prioritization signal, not final correctness.

A Verification Manifest records the explicit decision for each promoted candidate. Approval methods are:

- human_review;
- machine_corroborated_accepted;
- source_pair_manual_approval.

A candidate with ambiguous structure or conflicting evidence cannot be approved by a non-human method.

If the verified answer differs from the machine aggregate, an explicit override reason is mandatory.

The output Verified Candidate Bank remains private and pre-canonical. Scores, chapter taxonomy, rich-content fidelity and editorial ordering are separate publication gates.

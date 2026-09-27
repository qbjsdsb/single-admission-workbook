# Candidate / Evidence pairing review v0.1

This is the last machine-generated review boundary before canonical promotion.

Evidence strength:

- content_exact: student/original candidate and teacher/solution prompt have the same structural fingerprint.
- content_high: content similarity is high and unambiguous.
- paired_source_number: the file pair is already a trusted candidate pair and answer evidence agrees by section plus question number, but the teacher source does not contain a matchable prompt.
- number_only: answer evidence matches only by number. This is weak and cannot auto-progress.
- none: no usable binding.

Review state ready_for_verification does not mean answer correctness is proven. It means candidate structure is parsed, answer evidence has one normalized value, there is no machine-visible conflict, and answer binding is at least content-based or from a name-exact paired source.

A human/content verification gate is still required before canonical promotion.

review_required means one or more structural, pairing, answer, or binding issues remain.

conflict means at least two distinct answer values are present. Conflict is fail-closed and cannot be resolved by source priority alone.

This review queue remains private derived data when built from the user's corpus. The public repository contains only code, schemas and synthetic tests.

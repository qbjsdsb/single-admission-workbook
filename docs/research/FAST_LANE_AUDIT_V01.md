# English / Politics fast-lane audit v0.1

Private calibration against the user-provided source archive. No raw question text or private paths are committed.

## Scope

This audit targets source-like DOCX files that can enter the text/DOCX fast lane. It measures structural candidate extraction, not canonical publication coverage.

### English

12 student/original DOCX papers were calibrated after the following real-source issues were fixed:

- section keywords inside question prompts no longer create fake sections;
- Arabic section headings such as "1. 单项选择" are accepted;
- papers with a missing first section heading can recover a long consecutive 1..N question run, but that inferred section remains needs_review;
- glued Word options such as A...B...C...D are parsed by ordered labels rather than whitespace.

Current structural result:

- 12/12 papers produce 56 candidate units each;
- 672 candidate units total;
- the expected common shape is 55 numbered items plus one writing task;
- choice-type parse status observed during private calibration:
  - 475 structurally complete;
  - 65 ambiguous and retained for review.

These counts are structural extraction evidence only. They do not mean all answers, formatting, scores, or chapter assignments have been verified.

### Politics

17 student/source-like DOCX papers were calibrated.

Current structural result:

- 558 candidate questions total;
- 15 papers produce 33 candidates;
- two outliers produce 32 and 31 candidates and remain review targets;
- choice-type parse status observed during private calibration:
  - 398 structurally complete;
  - 21 ambiguous;
  - 4 without a recognized full option set.

The outliers are not automatically fixed because the source itself may differ from the common 33-question structure.

## Safety interpretation

parsed means the source structure was read without ambiguity at the current parser layer.

It does not mean:

- canonical answer verified;
- teacher/student pairing verified;
- duplicate status resolved;
- chapter assignment approved;
- rich formatting guaranteed;
- ready for publication.

Any inferred missing heading, ambiguous option layout, unsupported rich node, or source-count anomaly stays in a review queue.

## Next production step

Use the candidate bank as input to a teacher/solution evidence bank, then apply Pairing v2 and answer-conflict checks before promoting anything into the Canonical Question Bank.

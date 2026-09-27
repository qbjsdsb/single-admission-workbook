# Grouped Canonical Questions v0.1

English cloze and reading exercises are not collections of detached questions. Their shared passage is part of the exercise identity and must survive every production gate.

The Candidate Bank already records:

- group ID and kind;
- shared material;
- ordered child candidate IDs;
- per-child source locators.

This gate promotes a group atomically only when every child has:

1. verified answer;
2. usable score;
3. assigned classification;
4. supported canonical structure.

If one child is unresolved, the group is unresolved. Children do not fall back to detached publication because that would lose or duplicate the shared material.

Canonical representation:

- top-level kind: cloze_group or reading_group;
- top-level stem: shared passage, rendered once;
- top-level score: sum of child scores;
- top-level answer: ordered child-answer list;
- children: ordered child questions with their own score, stem, options, answer, analysis and notes.

All children in v0.1 must share one public chapter/section placement. This matches the current safe cloze classification route; semantic reading sub-skill classification remains deferred.

The renderer prints the shared passage once and then numbers each child in the normal global workbook sequence. Student and teacher editions therefore share exactly the same group structure while teacher answers/analysis remain child-local.

Exact duplicate fingerprints include shared material and child exercise content, but deliberately exclude answers and explanations.

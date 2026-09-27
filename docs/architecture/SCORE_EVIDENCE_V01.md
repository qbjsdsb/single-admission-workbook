# Score Evidence v0.1

Question scores must come from source evidence or explicit editorial approval. They are not filled from generic subject assumptions.

For each Candidate Bank section, the parser extracts:

- declared question count;
- per-question score;
- section full score.

It then checks source consistency.

Examples:

- "共20小题，每小题2分，满分40分" is usable.
- "共20小题，每小题2分，满分30分" is a conflict.
- "共10小题，满分20分" remains incomplete because equal per-question scoring is not stated.
- "书面表达（满分10分）" may assign 10 points when that section contains one candidate.
- a multi-question section with only a total score and no trustworthy equal-per-question rule remains unresolved unless derivation is mathematically and semantically justified by the heading.

A source count that disagrees with the parsed candidate count is also a conflict.

Score Evidence remains private derived data for real source documents.

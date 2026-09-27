# Canonical Promotion v0.1

This is the boundary between verified source candidates and the publication-facing Canonical Question schema.

Promotion is fail-closed. A candidate is promoted only when all required upstream facts already exist:

1. answer verification completed;
2. positive score assigned from source score evidence or explicit editorial approval;
3. chapter and section assignment recorded in a Classification Manifest;
4. candidate kind is supported by the current canonical adapter;
5. required options exist for choice questions.

The promotion layer does not infer curriculum placement, score, answer, or difficulty.

Classification Manifest is an editorial decision artifact. It records the chapter/section/tags/difficulty to use for a candidate. A decision may be deferred instead of guessed.

Optional Teacher Enrichment can attach already-reviewed analysis or teacher notes. It never changes the verified answer.

Canonical IDs are stable hashes of the private candidate IDs with a public subject prefix. This prevents private source paths/IDs from leaking into publication while keeping rebuilds deterministic.

The resulting Canonical Draft is suitable for private sample rendering after schema validation. It is not whole-corpus release approval.

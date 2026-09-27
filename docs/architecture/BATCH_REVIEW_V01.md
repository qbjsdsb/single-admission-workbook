# Batch Pair Review v0.1

This command turns the existing private intake cache into a subject-wide review run without reopening every source file.

Input:

- `sources.private.json`;
- `pairs.private.json`;
- `cache/<cache_key>.json` Document AST results.

For each student/original source, the pipeline:

1. loads its cached Document AST once;
2. reuses all exact companion pairs already discovered by intake;
3. builds one Candidate Bank;
4. builds one Evidence Bank and Pairing Review per companion source;
5. aggregates answer evidence across companions;
6. extracts score evidence and safe classification proposals;
7. merges teacher enrichment only when prose is unambiguous across sources;
8. builds one Editorial Queue.

The output contains per-source private review folders plus a subject-wide UTF-8-BOM CSV and aggregate summary.

Different teacher-analysis variants are not silently concatenated or ranked. They remain unresolved for editorial choice.

This stage never writes a Verification Manifest and never grants publication approval. Its purpose is to make a whole subject reviewable in one command while reusing the expensive intake cache.

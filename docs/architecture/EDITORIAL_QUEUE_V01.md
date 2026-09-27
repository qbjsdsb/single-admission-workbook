# Unified Editorial Review Queue v0.1

The project has several fail-closed gates. This queue combines their unresolved work so a human or future agent does not need to inspect separate JSON files.

Priority order:

0. answer conflicts and score conflicts;
1. candidate structure ambiguity and answer verification gaps;
2. missing or incomplete score evidence and taxonomy classification;
3. missing trusted teacher analysis.

A candidate with no outstanding issues becomes ready_for_sample.

The queue outputs JSON for automation and UTF-8-BOM CSV for convenient manual review. It does not modify source evidence or approve anything by itself.

This is a coordination layer over existing gates, not a second source of truth.

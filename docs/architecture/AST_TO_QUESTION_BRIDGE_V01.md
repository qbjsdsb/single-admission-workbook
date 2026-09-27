# Document AST -> question segmentation bridge v0.1

This bridge makes source provenance survive question splitting.

## Guarantees

- Every candidate paragraph keeps its source locator.
- PDF candidates can keep their page number.
- Section-first splitting is retained so numbered exam instructions do not become questions.
- English cloze/reading groups keep shared material separate from child questions.
- Writing tasks can remain unnumbered composition candidates.
- Any unresolved table, OCR page, OMML math or image reference blocks segmentation in strict mode.

## Why fail closed

The project prefers a visible review queue over silently producing a malformed question. Once a verified adapter for a rich feature exists, that feature can move from a blocker into the safe segmentation view.

## Next

The next adapter should convert located candidates into Canonical Question objects while preserving:
- occurrence/source locator;
- rich inline formatting;
- option structure;
- answer-evidence linkage.

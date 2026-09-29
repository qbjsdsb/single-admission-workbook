# AI Editorial Production Loop v0.1

## Purpose

The project is no longer optimized around completing a general-purpose automatic
workbook platform before real books can be produced.

The primary production unit is now a **small, publication-shaped editorial batch**
(usually about 4-10 final pages). AI/human editorial judgment may directly resolve
question boundaries, chapter placement, ordering, answer/analysis quality, visual
asset handling and page density. Code exists to remove repetitive work and enforce
important publication safeguards.

## Preferred production path

1. Read the real source page/document and its paired answer/teacher source.
2. Resolve the question content editorially.
3. Put a small ordered set of already-reviewed Canonical Question payloads into a
   private editorial batch.
4. Attach at least one verified source occurrence/locator to every batch question.
5. Run:

   ```bash
   python scripts/editorial_batch.py build/private/batch.json \
     --out build/private/editorial/english-batch-001 \
     --compile
   ```

6. Inspect every PNG under `visual-review/`.
7. Fix content/layout at the question or template level.
8. Only after visual acceptance, merge the accepted question/occurrence records into
   the subject-level book and final occurrence ledger.

The batch renderer preserves the explicit editorial question order and generates the
student and teacher editions from the same question objects.

## What remains mandatory

The simplified path does **not** relax the final-book quality rules:

- every published question retains source provenance;
- student and teacher editions use the same ordered question set;
- fixed-answer questions need an answer and real analysis;
- grouped reading/cloze children need answer and analysis;
- student output must not contain teacher-only answer/analysis commands;
- compiled pages must be A4, non-empty, without missing glyphs or overfull boxes;
- final full-book release still requires corpus-level occurrence accounting so source
  material cannot disappear silently.

## What is now optional

Candidate Bank, Evidence Bank, Pairing Review, Verification aggregation,
Classification proposals, Canonical promotion and Editorial Queue remain useful
automation for clean/high-volume sources.

They are no longer mandatory prerequisites for producing an editorial batch when an
editor can directly inspect and resolve the source reliably.

## Difficult visual material

Do not block the whole subject on one difficult page.

- reuse clean source text when reliable;
- retain a clear source figure as an image when that is the safest faithful result;
- redraw only when the source visual is unsuitable for publication and the geometry
  can be verified;
- do not guess unclear symbols, formula signs, labels or missing text;
- keep the difficult item deferred while independent clean batches continue.

## Repository role

GitHub is a publishing toolbelt and quality safety net, not the product.

Do not add databases, web dashboards, services or abstraction layers unless they
directly make the eight target books faster to finish, harder to break, or easier to
review.

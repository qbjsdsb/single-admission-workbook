# Private Sample Selection v0.1

A private sample is a publication rehearsal, not a partial claim that the whole corpus is complete.

The selector consumes only Canonical Draft questions. By default a question is eligible only when:

- it validates against the Canonical Question schema;
- a verified answer exists;
- reviewed teacher analysis exists;
- its chapter/section exists in the supplied curriculum;
- it is not part of an unresolved exact-duplicate cluster.

Every exclusion is recorded with a reason.

The same selected question IDs generate two Book Manifests:

- student sample;
- teacher sample.

Both reuse the production A4 layout and table-of-contents structure. The selector itself does not bypass whole-corpus release gates and does not alter source coverage ledgers.

Real sample content and selection output remain private derived artifacts.

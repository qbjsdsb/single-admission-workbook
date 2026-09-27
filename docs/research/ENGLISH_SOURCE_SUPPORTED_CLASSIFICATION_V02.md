# English source-supported classification v0.2

Date: 2026-09-28

This is a private-corpus calibration note. No raw question text, source filename,
source path, answer payload, or private identifier is committed.

## Problem

The first real English run deliberately deferred 540 of 672 candidate units
because the classifier refused to guess grammar, vocabulary, or reading
semantics from question numbers alone.

That conservative boundary was correct, but the paired teacher sources already
contain trusted, strongly bound explanation prose for most of those questions.
Ignoring that evidence would turn a source-supported editorial decision into
unnecessary manual classification work.

## Rule

Classification may now use teacher prose only after Teacher Enrichment has
established a trustworthy candidate/evidence binding.

For single-choice questions, explicit teacher phrases such as noun/article/
pronoun/adjective/adverb/preposition/conjunction, verb/tense/non-finite forms,
clauses/syntax, fixed phrases, verb phrases, or situational communication map to
the existing source-derived English taxonomy.

For reading questions, explicit labels for detail, inference, main idea, and
word/phrase guessing map directly. Older teacher prose that cites an exact
paragraph/sentence cue without a named question type may map only to the broad
detail category.

If trusted prose does not expose a safe subtype, the system does not invent one.
It uses a broad source-section bucket instead:

- single choice -> 单项选择综合训练;
- reading -> 阅读理解综合训练;
- word spelling -> 单词拼写专项训练.

These three broad buckets are added to the source-derived draft taxonomy.

## Private 12-document preflight

Among the 540 candidates that were previously deferred:

- 233 single-choice questions can receive a finer placement from trusted teacher
  explanation wording;
- 165 reading questions can receive a finer placement from trusted teacher
  explanation wording;
- 7 single-choice questions contain only sentence-level explanation and remain
  in the broad single-choice bucket;
- 15 reading questions lack source analysis and remain in the broad reading
  bucket;
- all 120 word-spelling questions stay together in the source-section spelling
  bucket.

Therefore all 540 previously deferred candidates have a source-supported
publication placement without asking AI to guess a semantic subtype.

This is a placement preflight, not publication approval. Answer verification,
score evidence, source structure, duplicate handling, and teacher-analysis
requirements remain independent gates.

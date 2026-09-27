# Teacher / Solution Evidence Bank v0.1

Evidence Bank is the private boundary for teacher editions, solution documents and answer-only sources.

It deliberately separates two things:

1. question records that contain enough prompt content for Pairing v2;
2. answer / analysis / teacher-note evidence that may exist even when the source contains no prompt.

This prevents answer summaries from being mistaken for verified question identity.

## Supported fast lane

English:
- numbered prompt + choices;
- 答案：X;
- 解析：... .

Politics:
- numbered 答案 entries with or without colon;
- 答案汇总 rows;
- 题干核心;
- 解析;
- compact fill-answer rows;
- numbered long-answer rows.

## Promotion rule

Extracted evidence is not automatically verified evidence.

Before a teacher answer can become canonical:

- the source document must be paired to the intended student/original source;
- prompt-bearing records should use Pairing v2;
- summary-only evidence may use section + number only as a weaker corroborating signal;
- conflicting values remain separate evidence and must block publication;
- no parser is allowed to overwrite a conflict by source priority alone.

All real evidence banks remain private derived data.

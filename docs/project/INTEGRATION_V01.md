# Production baseline integration v0.1

This branch consolidates the validated workbook pipeline work into one review target for main.

Included:
- resumable corpus intake and cache;
- eight-book orchestration;
- coverage ledger;
- content-aware pairing and answer conflict checks;
- duplicate detection;
- Document AST v1;
- DOCX rich formatting, images, and embedded equation capture;
- PDF page and bounding-box preservation;
- A4 XeLaTeX rendering;
- environment-aware PDF cache;
- Golden Benchmark;
- tested publication Docker image foundation.

This baseline is infrastructure only. It does not claim that the eight real books are finished.

Remaining production gates include verified equation/image conversion, real-source benchmark coverage, corpus-scale question segmentation, chapter classification, editorial ordering, long-form real sample books, and final visual review.

Before integration, all current CI checks must pass and the public repository must contain only code, schemas, synthetic fixtures, and aggregate research data.

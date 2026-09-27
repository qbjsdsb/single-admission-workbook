#!/usr/bin/env python3
from pathlib import Path
import sys

FORBIDDEN = (
    "source_id",
    "question_id",
    "parser_confidence",
    "review_status",
    "copyright_status",
    "GitHub",
    "commit SHA",
    "公开模板示例",
    "本地整理稿",
    "待审核",
    "内部ID",
)

if len(sys.argv) != 2:
    raise SystemExit("usage: check_publication_text.py <extracted-text-file>")

text = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
hits = [token for token in FORBIDDEN if token.lower() in text.lower()]
if hits:
    raise SystemExit("publication purity check failed: " + ", ".join(hits))
print("publication purity check passed")

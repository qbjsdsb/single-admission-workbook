# English teacher-analysis evidence calibration v0.2

Date: 2026-09-28

This is a private-corpus calibration note. No raw source text, filenames, paths,
answers, or private identifiers are committed.

## Finding

The first 12-pair English business run recovered teacher-analysis evidence for
581 of 660 numbered items and left 79 items without source analysis.

A focused audit of the four missing items inside otherwise fully explained mock
papers found one exact formatting defect: the source contains a numbered detail
heading with its closing Chinese bracket but the opening bracket is missing.

The four affected numbered detail headings occur in three teacher documents.
The detailed explanation text immediately follows each malformed heading.

## Narrow parser fix

The Evidence Bank now accepts both:

- a normal heading shaped like an opening bracket + number + “题详解” + closing
  bracket; and
- the same heading when only the opening bracket is missing.

The closing bracket remains mandatory. Bare prose such as “21题详解” without the
closing bracket is not accepted, so the parser does not broaden this into a
general guess.

Existing pending-detail logic then attaches the following paragraph as analysis
evidence exactly as it already does for well-formed headings.

## Private corpus effect

With this one formatting recovery, the four parser-caused omissions are
recoverable. The expected English teacher-analysis evidence count therefore
moves from 581/660 to 585/660 when the full private pipeline is rerun.

The remaining 75 missing analyses are concentrated in older source material and
are not treated as parser failures. They must stay visibly missing until a
separate generated-analysis workflow creates clearly labeled draft explanations
and those drafts are reviewed.

This note does not claim publication approval or academic verification of the
source explanations.

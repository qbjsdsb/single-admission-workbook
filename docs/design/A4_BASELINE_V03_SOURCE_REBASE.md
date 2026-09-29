# A4 design baseline v0.3 - source rebase

This revision treats the supplied `四科样张.tex` as the authoritative layout source and the supplied `sample-v4.pdf` as the rendered visual target.

## What the source clarified

The original source already encodes the core visual language well:

- A4 page geometry: 18 mm left, 16 mm right, 16 mm top, 20 mm bottom.
- Font roles: SimSun body, SimHei structural labels, KaiTi literary title/brand, Times New Roman Latin text.
- The upper-right label and the open-book ornament are a single header system.
- Chinese emphasis uses semantic under-dots.
- Mathematics uses native TeX math.
- The footer uses separate brand type treatments for “青云阁” and “教育”.

The source is therefore retained as the visual baseline. v0.3 is a refactor of the source, not a visual redesign.

## Differences between source v3 and rendered v4 / current requirements

1. The source footer hard-coded “2024年题选 · 本地整理稿”; publication output now uses a quotation only.
2. The source tied question-counter reset to `pagehead`; v0.3 decouples numbering from page chrome.
3. The source loaded `needspace` but did not use it; v0.3 adds minimum keep-together guards.
4. Source options used the full text width and started at the page text edge; current requirement aligns option labels with the score rail.
5. Source math sub-parts were plain paragraphs; current requirement aligns `（1）` / `（2）` with the score rail.
6. Source long question continuation returned to the page text edge; v0.3 aligns continuation to the stem rail.
7. Source header relied on `\hfill`; v0.3 reserves a fixed right rail so long titles cannot displace the label/icon.

## Horizontal grid

The reference PDF places the text edge at 18 mm and its score at approximately 24 mm. The current requirement asks for the score closer to the question number without moving the stem.

v0.3 therefore uses:

- number start: 18 mm
- score / option / sub-question start: 23 mm
- stem start: about 39.05 mm on the first line
- wrapped stem continuation: 23 mm, aligned to the score rail
- choice labels: 23 mm, aligned to the score rail
- math/material sub-question markers: visually aligned to the 23 mm score rail

This preserves the original first-line stem position while tightening number-to-score spacing by about 1 mm. Continuation lines intentionally return to the score rail instead of the stem rail.

## Font profiles

The public repository does not distribute SimSun, SimHei, KaiTi, or Times New Roman.

The renderer therefore has two runtime profiles:

- Windows publish profile: if the standard Windows font files exist, use them directly from `C:/Windows/Fonts`.
- Open CI profile: fall back to Noto Serif CJK SC, Noto Sans CJK SC, AR PL KaitiM GB, and Tinos.

The content/layout API is identical in both profiles.

## Publication cleanliness

Student/teacher publication pages must not render source IDs, parser confidence, GitHub/build text, copyright audit state, or other engineering metadata. Provenance remains internal data only.

## Next gate

Before restructuring the full repository, approve the following baseline properties:

- header geometry and right-side icon/label;
- footer brand/quote/page-number geometry;
- Chinese font role hierarchy;
- question number / score / stem rails;
- option and math sub-question alignment;
- page-break guards.

After approval, content will be separated from the renderer and the chapter/question schema will be introduced.


## Geometry regression gate

The GitHub workflow extracts PDF bounding boxes after compilation and checks representative coordinates, not only whether XeLaTeX exits successfully. In the baseline sample it asserts that:

- the wrapped second line of the long politics choice stem begins on the score rail;
- politics choice label A begins on the score rail;
- the first mathematics sub-question marker begins on the score rail.

This protects the layout contract from later macro/font refactors that would otherwise look valid to ordinary compilation tests.

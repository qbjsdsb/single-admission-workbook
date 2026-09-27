# Eight-book quality hardening v0.1

This layer sits on top of the Astra eight-book pipeline. It does not replace the intake or renderer.

## Release-safety changes

1. **Compile cache is environment-sensitive.**
   A PDF cache key must include the source build ID plus an XeLaTeX/font environment fingerprint. A TeX/font upgrade therefore forces recompilation.

2. **Answer evidence is explicit.**
   Multiple answer sources are normalized and compared. Conflicts are release blockers; a teacher/solution file is evidence, not automatic truth.

3. **Option parsing fails closed.**
   Common Word forms (one-line A/B/C/D and one-option-per-paragraph) are parsed. Ambiguous wrapped options are marked ambiguous instead of silently attaching text to the wrong option.

4. **Rich DOCX adaptation fails closed.**
   Verified text styles such as emphasis dots and underline can become canonical rich-text nodes. OMML, images and table blocks remain explicit blockers until dedicated adapters are verified.

5. **Golden benchmark.**
   Public synthetic cases run in CI. A larger private benchmark derived from the supplied corpus should be maintained outside Git and must gate production parser upgrades.

## Still not solved by this PR

- verified OMML -> canonical math conversion;
- image/table placement conversion;
- real-corpus question-level golden truth;
- semantic chapter classification;
- near-duplicate detection;
- editorial ordering across hundreds of pages.

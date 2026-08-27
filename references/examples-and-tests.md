# Examples and tests

## Contents

1. Gold-standard example
2. Normal test
3. Boundary test
4. Non-trigger test

## 1. Gold-standard example

Prompt:

> Build chapters 1–5 from sequential official JPG files into independent 690px global-Y streams. Use 6000px non-overlapping cores, 3000px context, 12000px scans, preserve all pages, create a direct-source extractor, test every JPG boundary, and prove deterministic reruns.

Expected behavior:

- Preflight all five chapters before writing.
- Enforce `.jpg`, numeric continuity, 690px strict width, and chapters 1–5 only.
- Produce root scripts and per-chapter `scans/`, `stream-map.json`, `scan-index.json`, and `validation.json`.
- Preserve warning, credit, and end pages.
- Delete zero rows unless exact informative duplicates exist.
- Test all `input_count - 1` boundaries through the extractor.
- Report objective per-chapter results and PASS only after a matching rerun hash.

Use `assets/gold-standard/expected-summary.json` as the artifact-level oracle.

## 2. Normal test

Input fixture:

- Three `RGB` PNG files named `001.png`, `002.png`, `003.png`.
- Width 64; heights 40, 50, and 30.
- No repeated boundary rows.
- `CORE_HEIGHT=60`, `CONTEXT=20`, `VIEW_HEIGHT=100`.

Expected:

- Stream size `64x120`.
- Source ranges `[0,40)`, `[40,90)`, `[90,120)`.
- Two cores: `[0,60)` and `[60,120)`.
- Two scans, each `64x100`, with declared edge padding.
- Two boundary tests pass; zero rows deleted.
- A region `[y=35,95)` crosses all three sources and matches direct decoded pixels.

## 3. Boundary test

Input fixture:

- `001.png` height 80.
- `002.png` begins with an exact, informative 16-row copy of the bottom of `001.png`, followed by 50 new rows.
- Configure the conservative minimum to 16 for this synthetic test only.

Expected:

- Delete exactly 16 rows from the top of `002.png` after full RGB equality.
- Stream height is `80 + 50 = 130`.
- Record the decision evidence and deleted height.
- Extraction across global y 76–84 contains no gap and no duplicate.

Also test an all-white 16-row match. Expected deletion is zero because it is uninformative.

## 4. Non-trigger test

Prompt:

> Read these comic pages, summarize the plot, select dramatic panels, and write a short-video script.

Expected:

- Do not trigger this skill. The task is semantic analysis and creative selection, not source canonicalization or global-coordinate extraction.

# Coordinate-stream specification

## Contents

1. Contract and invariants
2. Input and normalization
3. Exact overlap decisions
4. Coordinate and scan contracts
5. Mapping schemas
6. Extraction contract
7. Validation contract
8. Failure-derived safeguards

## 1. Contract and invariants

The content stream is a logical sequence of decoded RGB rows. It need not exist as one tall file.

Never vary these invariants:

- Treat source and read-only reference directories as immutable.
- Sort by numeric filename stem; reject gaps, duplicates, and nonnumeric stems.
- Use zero-based, half-open global and local intervals.
- Keep source ranges contiguous with no gap and no overlap after declared deduplication.
- Perform no OCR, panel detection, plot interpretation, or content removal.
- Preserve non-story pages unless removal is a separate explicit task.
- Delete no row on perceptual similarity alone.
- Keep cores disjoint and exhaustive.
- Use scans only for reading and location.
- Generate final pixels from mapped source files, never from scans.
- Declare PASS only after pixel comparison and a deterministic rerun.

## 2. Input and normalization

Preflight every file before cleaning an existing output. Record original path, size, mode, orientation result, ICC presence, standardized size, and normalization operation.

Supported width policies:

- `strict`: require every oriented decoded width to equal the requested width. Preserve row pixels except for necessary deterministic color conversion.
- `fit-without-upscale`: downscale wider images proportionally; center-pad narrower images without scaling. Never stretch.

Do not select a width from one sample. Inspect the full chapter. A user-specified native width overrides a modal-width guess and must be enforced.

Convert color deterministically. Embed a stable sRGB ICC profile in generated PNGs. Normalize nondeterministic ICC creation timestamps or use fixed profile bytes.

## 3. Exact overlap decisions

For adjacent standardized images A and B, find the longest suffix of A whose rows equal a prefix of B. Use row hashes only as a search accelerator; confirm the complete RGB region with a full pixel comparison.

Delete B's prefix only when all conditions pass:

1. The full decoded RGB pixels match.
2. The region exceeds a conservative minimum height.
3. The region has enough tonal and row variation to rule out coincidental blank margins.
4. The decision is recorded as high confidence with evidence.

If a match is short, blank, uniform, perceptual, or otherwise ambiguous, preserve it. Zero deletion is a valid and often correct result.

## 4. Coordinate and scan contracts

For retained source `i`:

```text
global_y_start[i] = global_y_end[i-1]  # first source starts at 0
global_y_end[i] = global_y_start[i] + retained_height[i]
```

For scan index `k >= 0`:

```text
core_start = k * CORE_HEIGHT
core_end = min(core_start + CORE_HEIGHT, chapter_height)
view_start = core_start - CONTEXT
view_end = view_start + VIEW_HEIGHT
padding_top = max(0, -view_start)
padding_bottom = max(0, view_end - chapter_height)
```

Require `VIEW_HEIGHT >= CORE_HEIGHT + 2 * CONTEXT` when the requested view must contain the entire core plus symmetric context. Reject contradictory parameters instead of inventing irregular windows.

The anchor ownership rule is:

```text
anchor_y = (global_y0 + global_y1) / 2
owner_k = floor(anchor_y / CORE_HEIGHT)
```

Clamp only the final core end to chapter height. Never overlap cores.

## 5. Mapping schemas

`stream-map.json` must include:

- chapter identifier and coordinate convention;
- global width, height, mode, color space, and ICC identity;
- input and output roots;
- normalization and overlap policies;
- per source: path, original/oriented/standardized sizes, deleted rows, retained source start, global start/end, and decision evidence;
- every source boundary and its global Y.

`scan-index.json` must include:

- `CORE_HEIGHT`, `CONTEXT`, and `VIEW_HEIGHT`;
- ownership and final-extraction warnings;
- per scan: ID, relative path, view start/end, core start/end, top padding, and bottom padding.

`validation.json` must contain named Boolean checks, objective counts, boundary-test details, deterministic hashes, and a final top-level `PASS` or `FAIL`. A new output may use transient `PENDING_RERUN`; it cannot be reported as complete until an identical second run changes it to `PASS`.

## 6. Extraction contract

Validate `0 <= x0 < x1 <= stream_width` and `0 <= y0 < y1 <= chapter_height`. Iterate all source ranges intersecting `[y0, y1)`, translate global Y into retained source-local Y, crop decoded sources, and paste contributions consecutively. Reject any gap, overlap, size drift, missing source, or non-PNG output.

An extracted region may cross any number of sources. Preserve exact output dimensions `(x1-x0, y1-y0)` and embed sRGB.

## 7. Validation contract

Mandatory checks:

1. Input numbering is continuous and processed count matches discovered count.
2. Source coordinate ranges cover `[0, chapter_height)` exactly once.
3. No deletion lacks exact high-confidence evidence.
4. Cores cover `[0, chapter_height)` exactly once.
5. Every boundary is crossed by an actual extractor request.
6. Every extracted boundary result equals independently assembled decoded pixels.
7. All scans are openable PNG/RGB/sRGB with configured width and view height.
8. Scan padding and any shared view content are pixel-consistent.
9. A second full run produces the same payload-tree hash.
10. No incomplete marker or temporary cache remains.

Hash the deterministic payload, excluding only explicitly runtime diagnostic files. On the final run, record both hashes and equality.

## 8. Failure-derived safeguards

- Fixed overlapping chunks plus a larger safe margin were mathematically incompatible. Use unique cores for ownership; do not add boundary-specific windows.
- A chapter-one-only script blocked later chapters. Parameterize the chapter and enforce an explicit scope allowlist.
- Assuming 720px damaged a later 690px native edition. Inspect all files and enforce the requested width policy; never upscale implicitly.
- Comparing a newly generated ICC byte hash failed because the profile header contained the current time. Freeze nondeterministic metadata before hashing.
- A self-authored validation can reproduce its own bug. Add an independent pixel assembly or hash check outside the production path.
- Broad recursive cleanup may be blocked or unsafe. Resolve targets first and clean only generated files inside the exact output chapter.
- Bytecode and temporary caches polluted final structures. Disable bytecode during subprocess extraction and verify no temporary artifacts remain.
- Changing WebP to official JPG was an edition change, not a trivial extension change. Treat extension, native width, output root, and source edition as a new immutable profile.

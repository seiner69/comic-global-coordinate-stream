---
name: comic-global-coordinate-stream
description: Build, rebuild, validate, or extract from a deterministic global-Y coordinate stream made from sequential comic/webtoon image slices (JPG, JPEG, PNG, or WebP), including fixed non-overlapping ownership cores, overlapping reading scans, conservative exact-pixel boundary deduplication, source maps, and cross-source region extraction. Use for comic source canonicalization, continuous chapter coordinates, scan generation, or final crops spanning source files. Do not use for OCR, plot analysis, scriptwriting, panel selection, subtitles, video editing, generative image work, or an isolated ordinary image edit.
---

# Comic Global Coordinate Stream

Treat source images as one logical pixel stream. Keep reading views separate from content ownership and final extraction.

## Required resources

- Read [references/specification.md](references/specification.md) before changing coordinate, overlap, width, cleanup, or validation behavior.
- Read [references/examples-and-tests.md](references/examples-and-tests.md) when selecting defaults, reviewing a result, or writing tests.
- Copy `scripts/canonicalize_chapter.py` and `scripts/extract_global_region.py` together into the requested output root when the deliverable requires local rerunnable scripts.
- Use `scripts/audit_output.py` for an independent decoded-pixel audit; use `scripts/make_test_fixture.py` for deterministic smoke fixtures.
- Start from [assets/config.template.json](assets/config.template.json) when several chapters share one profile.
- Compare a completed result with [assets/gold-standard/expected-summary.json](assets/gold-standard/expected-summary.json).

## Workflow

1. Freeze the task contract.
   - Resolve input, output, read-only reference directories, chapter allowlist, extension, expected width, width policy, and scan parameters.
   - Use half-open coordinates `[start, end)` and zero-based global Y.
   - Refuse an output path equal to or nested inside an input or read-only reference path.

2. Preflight without writing.
   - Discover only the requested extension.
   - Require numeric stems and a continuous sequence starting at `001`.
   - Inspect every decoded size, mode, orientation, and ICC profile.
   - Stop on missing input, mixed naming, unsupported width, or ambiguous policy. Do not silently repair.

3. Select width behavior explicitly.
   - Use `strict` when native pixels must be preserved. Reject any decoded width mismatch.
   - Use `fit-without-upscale` only when authorized: proportionally downscale wider sources and center-pad narrower sources without scaling. Never stretch horizontally or upscale a narrow source.

4. Build the logical stream.
   - Decode in numeric order and normalize orientation/color deterministically.
   - Delete following-source top rows only after full decoded RGB equality and conservative informativeness checks. Preserve every uncertain row.
   - Assign contiguous source ranges. Require each `global_y_start` to equal the prior `global_y_end`.
   - Keep warning pages, credits, advertisements, and end pages unless the user explicitly supplies a separate content-removal task.

5. Build unique ownership cores and reading scans.
   - Compute `core_start = k * CORE_HEIGHT` and `core_end = min(core_start + CORE_HEIGHT, chapter_height)`.
   - Compute `view_start = core_start - CONTEXT` and `view_end = view_start + VIEW_HEIGHT`.
   - Pad outside chapter bounds; do not shift cores or insert irregular safety windows.
   - Assign content once using `anchor_y = (global_y0 + global_y1) / 2` and the unique half-open core containing the anchor.

6. Enforce source-based final extraction.
   - Use `extract_global_region.py` with chapter, X interval, global Y interval, and PNG output.
   - Re-decode mapped sources and stitch every intersecting source directly.
   - Never crop a final shot from a scan.

7. Validate before reporting PASS.
   - Test every source boundary through the extractor.
   - Compare extracted RGB pixels with an independently assembled decoded-source expectation.
   - Validate core coverage, scan size/format/color, edge padding, and source-map continuity.
   - Run the full chapter build again and compare a deterministic payload-tree hash.
   - Report FAIL if any mandatory check is false or unavailable.
   - Run `audit_output.py` independently after the canonicalizer's own validation.

8. Report only objective results: per-chapter input count, stream dimensions, scan count, boundary-test count, deleted duplicate count/rows, deterministic-rerun result, output path, and PASS/FAIL.

## Missing-input behavior

Stop before cleanup when any required input or policy is missing. Ask only when the missing choice materially changes pixels or output scope; otherwise derive stable facts by inspection and record them. Never infer permission to modify a source or reference directory.

## Script usage

Run one chapter:

```powershell
python canonicalize_chapter.py --chapter ch_001 --input-dir ./examples/input/ch_001 --output-root ./work/canonical --extension .jpg --width 690 --width-policy strict --core-height 6000 --context 3000 --view-height 12000
```

Run the identical command twice on a new output. The first run must remain `PENDING_RERUN`; only a matching second payload may become `PASS`.

Extract a final region:

```powershell
python extract_global_region.py --canonical-root ./work/canonical --chapter ch_001 --x0 0 --x1 690 --global-y0 12000 --global-y1 18000 --output ./work/shots/shot.png
```

Use `--help` for the complete interface.

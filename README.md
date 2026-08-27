# Comic Global Coordinate Stream

A Codex skill and Python toolkit for turning sequential comic or webtoon image slices into one deterministic global-Y coordinate system.

It keeps three concerns separate:

- immutable source-image ownership;
- overlapping reading scans for inspection;
- exact final extraction from the mapped source pixels.

## Why it exists

Long comic chapters are commonly stored as hundreds of numbered images. Downstream editing becomes fragile when every crop is tied to a particular file. This project builds a continuous coordinate space across those files while preserving a source map, validating every boundary, and proving deterministic reruns.

## Highlights

- Strict numeric source discovery with gap detection
- Optional width normalization without upscaling
- Conservative exact-pixel boundary deduplication
- Non-overlapping ownership cores plus contextual reading scans
- Cross-source extraction using half-open global coordinates
- Independent decoded-pixel audit
- Deterministic synthetic smoke fixtures

## Requirements

- Python 3.10 or newer
- Pillow with ImageCms support

Install the dependency:

```bash
python -m pip install -r requirements.txt
```

## Use as a Codex skill

Clone or copy this repository into your personal Codex skills directory under the name `comic-global-coordinate-stream`, then invoke:

```text
$comic-global-coordinate-stream
```

Read `SKILL.md` for the complete agent workflow and `references/specification.md` for the invariants.

## Direct script usage

Build a chapter twice. The first run is expected to report `PENDING_RERUN`; the identical second run must report `PASS`.

```bash
python scripts/canonicalize_chapter.py \
  --chapter ch_001 \
  --input-dir ./examples/input/ch_001 \
  --output-root ./work/canonical \
  --extension .jpg \
  --width 690 \
  --width-policy strict \
  --core-height 6000 \
  --context 3000 \
  --view-height 12000
```

Extract a region that may span multiple source files:

```bash
python scripts/extract_global_region.py \
  --canonical-root ./work/canonical \
  --chapter ch_001 \
  --x0 0 --x1 690 \
  --global-y0 12000 --global-y1 18000 \
  --output ./work/shots/shot.png
```

Run the independent audit:

```bash
python scripts/audit_output.py \
  --canonical-root ./work/canonical \
  --chapter ch_001
```

## Test

```bash
python -m unittest -v tests.test_smoke
```

The smoke test creates synthetic images in a temporary directory, performs two canonicalization runs, and finishes with the independent pixel audit.

## Repository structure

```text
agents/       Codex skill metadata
assets/       Reusable configuration and gold-standard summary
references/   Coordinate and validation contracts
scripts/      Canonicalizer, extractor, audit, and fixture generator
tests/        End-to-end deterministic smoke test
SKILL.md      Codex skill instructions
```

## Known limits

- This project does not perform OCR, panel detection, plot analysis, or content selection.
- Exact decoded-pixel comparison is intentionally conservative and may preserve uncertain duplicated rows.
- Large chapters require enough local storage for generated scans and temporary normalized images.
- The gold-standard summary records expected metrics but does not include copyrighted source images.

## Provenance

Created from a Codex-assisted workflow on 2026-08-19 and prepared as a clean public snapshot on 2026-08-27. Private inputs, generated comic images, machine-specific paths, and conversation history are not included.

## License

No open-source license has been granted for this repository yet. The absence of a license means normal copyright restrictions apply.

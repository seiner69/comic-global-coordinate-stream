#!/usr/bin/env python3
"""Independently audit canonical comic outputs against decoded source pixels."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageChops, ImageCms, ImageOps


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_rgb(image: Image.Image) -> str:
    return hashlib.sha256(image.convert("RGB").tobytes()).hexdigest()


def load_standardized(entry: dict) -> Image.Image:
    with Image.open(entry["source_path"]) as raw:
        raw.load()
        embedded = raw.info.get("icc_profile")
        oriented = ImageOps.exif_transpose(raw)
        if embedded:
            source_profile = ImageCms.ImageCmsProfile(io.BytesIO(embedded))
            image = ImageCms.profileToProfile(oriented, source_profile, ImageCms.createProfile("sRGB"), outputMode="RGB")
        elif oriented.mode in {"RGBA", "LA"} or "transparency" in oriented.info:
            rgba = oriented.convert("RGBA")
            white = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
            white.alpha_composite(rgba)
            image = white.convert("RGB")
        else:
            image = oriented.convert("RGB")
    operation = entry["normalization"]["operation"]
    target = entry["standardized_size"]
    if operation == "none":
        result = image
    elif operation == "proportional_downscale":
        result = image.resize((target["width"], target["height"]), Image.Resampling.LANCZOS)
    elif operation == "center_pad_without_upscale":
        result = Image.new("RGB", (target["width"], target["height"]), "white")
        result.paste(image, (entry["normalization"]["padding_left"], 0))
    else:
        raise ValueError(f"Unsupported normalization operation: {operation}")
    if list(result.size) != [target["width"], target["height"]]:
        raise ValueError(f"Standardized size mismatch for {entry['source_file']}")
    if sha256_rgb(result) != entry["decoded_rgb_sha256"]:
        raise ValueError(f"Decoded source hash mismatch for {entry['source_file']}")
    return result


def region(entries: list[dict], images: dict[int, Image.Image], width: int, x0: int, x1: int, y0: int, y1: int) -> Image.Image:
    out = Image.new("RGB", (x1 - x0, y1 - y0))
    filled = 0
    for entry in entries:
        start, end = entry["global_y_start"], entry["global_y_end"]
        top, bottom = max(y0, start), min(y1, end)
        if top >= bottom:
            continue
        source = images[entry["source_index"]]
        source_y0 = entry["retained_source_y_start"] + top - start
        piece = source.crop((x0, source_y0, x1, source_y0 + bottom - top))
        out.paste(piece, (0, top - y0))
        filled += bottom - top
    if filled != y1 - y0:
        raise ValueError(f"Region [{y0}, {y1}) has a gap or overlap")
    return out


def same_pixels(a: Image.Image, b: Image.Image) -> bool:
    return a.mode == b.mode and a.size == b.size and ImageChops.difference(a, b).getbbox() is None


def audit(canonical_root: Path, chapter: str) -> dict:
    chapter_dir = canonical_root / "chapters" / chapter
    stream = load_json(chapter_dir / "stream-map.json")
    scan_index = load_json(chapter_dir / "scan-index.json")
    entries = stream["sources"]
    width = stream["global_stream"]["width"]
    height = stream["global_stream"]["height"]
    images = {entry["source_index"]: load_standardized(entry) for entry in entries}

    cursor = 0
    stream_contiguous = True
    for entry in entries:
        stream_contiguous &= entry["global_y_start"] == cursor
        cursor = entry["global_y_end"]
    stream_contiguous &= cursor == height

    core_cursor = 0
    cores_cover_once = True
    scans_match = True
    view_height = scan_index["parameters"]["VIEW_HEIGHT"]
    for scan in scan_index["scans"]:
        cores_cover_once &= scan["core_global_start"] == core_cursor
        core_cursor = scan["core_global_end"]
        path = chapter_dir / scan["scan_path"]
        with Image.open(path) as opened:
            actual = opened.convert("RGB")
            scans_match &= opened.format == "PNG" and opened.mode == "RGB" and opened.size == (width, view_height)
        expected = Image.new("RGB", (width, view_height), "white")
        y0 = max(0, scan["view_global_start"])
        y1 = min(height, scan["view_global_end"])
        if y0 < y1:
            expected.paste(region(entries, images, width, 0, width, y0, y1), (0, scan["padding_top"]))
        scans_match &= same_pixels(actual, expected)
    cores_cover_once &= core_cursor == height

    extractor = Path(__file__).with_name("extract_global_region.py")
    boundary_results = []
    with tempfile.TemporaryDirectory(prefix="comic-stream-audit-") as temporary:
        for boundary in stream["boundaries"]:
            global_y = boundary["global_y"]
            y0, y1 = max(0, global_y - 7), min(height, global_y + 7)
            output = Path(temporary) / f"boundary_{boundary['boundary_index']:05d}.png"
            subprocess.run(
                [sys.executable, "-B", str(extractor), "--canonical-root", str(canonical_root), "--chapter", chapter,
                 "--x0", "0", "--x1", str(width), "--global-y0", str(y0), "--global-y1", str(y1), "--output", str(output)],
                check=True, capture_output=True, text=True,
            )
            with Image.open(output) as opened:
                actual = opened.convert("RGB")
            expected = region(entries, images, width, 0, width, y0, y1)
            boundary_results.append(same_pixels(actual, expected))

    checks = {
        "decoded_sources_match_map": True,
        "global_stream_contiguous": stream_contiguous,
        "cores_cover_once": cores_cover_once,
        "scans_match_source_pixels": scans_match,
        "all_boundary_extractions_match": all(boundary_results),
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "metrics": {"source_count": len(entries), "boundary_count": len(boundary_results)},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical-root", type=Path, required=True)
    parser.add_argument("--chapter", required=True)
    args = parser.parse_args()
    report = audit(args.canonical_root.resolve(), args.chapter)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

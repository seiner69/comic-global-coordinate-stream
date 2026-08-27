#!/usr/bin/env python3
"""Create one deterministic comic global-Y stream and fixed-core reading scans."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageCms, ImageOps, ImageStat


_profile_bytes = bytearray(ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes())
struct.pack_into(">6H", _profile_bytes, 24, 2020, 1, 1, 0, 0, 0)
SRGB_ICC = bytes(_profile_bytes)
SRGB_PROFILE = ImageCms.ImageCmsProfile(io.BytesIO(SRGB_ICC))
SRGB_SHA256 = hashlib.sha256(SRGB_ICC).hexdigest()


def canonical_chapter_id(value: str) -> str:
    lowered = value.strip().lower()
    numeric = lowered[3:] if lowered.startswith("ch_") else lowered
    if not numeric.isdigit() or int(numeric) < 1:
        raise ValueError(f"Invalid chapter: {value!r}")
    return f"ch_{int(numeric):03d}"


def convert_srgb(image: Image.Image) -> Image.Image:
    embedded = image.info.get("icc_profile")
    if embedded:
        source_profile = ImageCms.ImageCmsProfile(io.BytesIO(embedded))
        return ImageCms.profileToProfile(image, source_profile, SRGB_PROFILE, outputMode="RGB")
    if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
        rgba = image.convert("RGBA")
        white = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        white.alpha_composite(rgba)
        return white.convert("RGB")
    return image.convert("RGB")


def decode_source(path: Path, width: int, width_policy: str) -> tuple[Image.Image, dict[str, Any]]:
    with Image.open(path) as opened:
        opened.load()
        original_size = opened.size
        original_mode = opened.mode
        had_icc = bool(opened.info.get("icc_profile"))
        oriented = ImageOps.exif_transpose(opened)
        oriented.load()
        oriented_size = oriented.size
        rgb = convert_srgb(oriented)
    operation = "none"
    scale = 1.0
    left = right = 0
    if width_policy == "strict":
        if rgb.width != width:
            raise RuntimeError(f"{path.name}: decoded width {rgb.width} != required {width}")
        normalized = rgb.copy()
    elif width_policy == "fit-without-upscale":
        if rgb.width > width:
            height = max(1, int(round(rgb.height * width / rgb.width)))
            normalized = rgb.resize((width, height), Image.Resampling.LANCZOS)
            operation = "proportional_downscale"
            scale = width / rgb.width
        elif rgb.width < width:
            left = (width - rgb.width) // 2
            right = width - rgb.width - left
            normalized = Image.new("RGB", (width, rgb.height), (255, 255, 255))
            normalized.paste(rgb, (left, 0))
            operation = "center_pad_without_upscale"
        else:
            normalized = rgb.copy()
    else:
        raise ValueError(f"Unknown width policy: {width_policy}")
    return normalized, {
        "original_size": {"width": original_size[0], "height": original_size[1]},
        "oriented_size": {"width": oriented_size[0], "height": oriented_size[1]},
        "original_mode": original_mode,
        "had_embedded_icc_profile": had_icc,
        "standardized_size": {"width": normalized.width, "height": normalized.height},
        "standardized_mode": "RGB",
        "normalization": {
            "width_policy": width_policy,
            "operation": operation,
            "scale": scale,
            "padding_left": left,
            "padding_right": right,
        },
        "decoded_rgb_sha256": hashlib.sha256(normalized.tobytes()).hexdigest(),
    }


def discover(input_dir: Path, extension: str) -> list[tuple[int, Path]]:
    if not input_dir.is_dir():
        raise FileNotFoundError(f"Missing input directory: {input_dir}")
    extension = extension.lower()
    paths = [p for p in input_dir.iterdir() if p.is_file() and p.suffix.lower() == extension]
    if not paths:
        raise RuntimeError(f"No {extension} files in {input_dir}")
    invalid = sorted(p.name for p in paths if not p.stem.isdigit())
    if invalid:
        raise RuntimeError(f"Nonnumeric source filename(s): {invalid}")
    numbered = sorted(((int(p.stem), p.resolve()) for p in paths), key=lambda item: item[0])
    numbers = [number for number, _ in numbered]
    expected = list(range(1, numbers[-1] + 1))
    if numbers != expected or len(numbers) != len(set(numbers)):
        raise RuntimeError(f"Source sequence must be exactly 001..{numbers[-1]:03d}")
    return numbered


def row_hashes(image: Image.Image, count: int, bottom: bool) -> list[bytes]:
    raw = image.tobytes()
    stride = image.width * 3
    first = image.height - count if bottom else 0
    return [
        hashlib.blake2b(raw[(first + i) * stride : (first + i + 1) * stride], digest_size=16).digest()
        for i in range(count)
    ]


def prefix_suffix_length(pattern: list[bytes], text: list[bytes]) -> int:
    sentinel = object()
    sequence: list[Any] = [*pattern, sentinel, *text]
    prefix = [0] * len(sequence)
    for i in range(1, len(sequence)):
        candidate = prefix[i - 1]
        while candidate and sequence[i] != sequence[candidate]:
            candidate = prefix[candidate - 1]
        if sequence[i] == sequence[candidate]:
            candidate += 1
        prefix[i] = candidate
    return int(prefix[-1])


def exact_overlap(previous: Image.Image, following: Image.Image, minimum: int) -> dict[str, Any]:
    maximum = min(previous.height, following.height)
    previous_rows = row_hashes(previous, maximum, True)
    following_rows = row_hashes(following, maximum, False)
    candidate = prefix_suffix_length(following_rows, previous_rows)
    result: dict[str, Any] = {
        "candidate_exact_rows": candidate,
        "deleted_rows": 0,
        "confidence": "none",
        "full_pixel_equality_verified": False,
        "informative_region_verified": False,
        "reason": "no_exact_duplicate_rows",
    }
    if not candidate:
        return result
    a = previous.crop((0, previous.height - candidate, previous.width, previous.height))
    b = following.crop((0, 0, following.width, candidate))
    exact = ImageChops.difference(a, b).getbbox() is None
    result["full_pixel_equality_verified"] = exact
    if not exact or candidate < minimum:
        result["reason"] = "failed_full_pixel_or_minimum_height_check"
        return result
    gray = b.convert("L")
    stats = ImageStat.Stat(gray)
    low, high = gray.getextrema()
    distinct_rows = len(set(following_rows[:candidate]))
    informative = stats.stddev[0] >= 3.0 and high - low >= 16 and distinct_rows >= min(12, max(4, candidate // 8))
    result["informative_region_verified"] = informative
    result["evidence"] = {
        "grayscale_standard_deviation": round(float(stats.stddev[0]), 6),
        "grayscale_range": [int(low), int(high)],
        "distinct_rows": distinct_rows,
    }
    if informative:
        result.update({"deleted_rows": candidate, "confidence": "high", "reason": "exact_informative_RGB_duplicate"})
    else:
        result["reason"] = "exact_but_uninformative_rows_preserved"
    return result


def write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def payload_hash(chapter_dir: Path) -> str | None:
    files = [chapter_dir / "stream-map.json", chapter_dir / "scan-index.json"]
    scans = sorted((chapter_dir / "scans").glob("scan_*.png"))
    if any(not p.is_file() for p in files) or not scans:
        return None
    lines = [
        f"{p.relative_to(chapter_dir).as_posix()}:{hashlib.sha256(p.read_bytes()).hexdigest()}"
        for p in [*files, *scans]
    ]
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def prior_hash(chapter_dir: Path) -> str | None:
    validation = chapter_dir / "validation.json"
    if (chapter_dir / ".canonicalize.incomplete").exists() or not validation.is_file():
        return None
    try:
        status = json.loads(validation.read_text(encoding="utf-8")).get("status")
    except Exception:
        return None
    return payload_hash(chapter_dir) if status in {"PASS", "PENDING_RERUN"} else None


def plan_scans(height: int, core: int, context: int, view: int) -> list[dict[str, Any]]:
    scans = []
    for k in range(math.ceil(height / core)):
        core_start = k * core
        core_end = min(core_start + core, height)
        view_start = core_start - context
        view_end = view_start + view
        scans.append({
            "scan_id": f"scan_{k + 1:04d}",
            "scan_path": f"scans/scan_{k + 1:04d}.png",
            "view_global_start": view_start,
            "view_global_end": view_end,
            "core_global_start": core_start,
            "core_global_end": core_end,
            "padding_top": max(0, -view_start),
            "padding_bottom": max(0, view_end - height),
        })
    return scans


def paste_cache(canvas: Image.Image, destination_y: int, y0: int, y1: int, records: list[dict[str, Any]]) -> int:
    covered = 0
    for record in records:
        a = max(y0, record["global_y_start"])
        b = min(y1, record["global_y_end"])
        if a >= b:
            continue
        source_y = record["retained_source_y_start"] + a - record["global_y_start"]
        with Image.open(record["_cache_path"]) as image:
            image.load()
            region = image.crop((0, source_y, image.width, source_y + b - a))
        canvas.paste(region, (0, destination_y + a - y0))
        covered += b - a
    return covered


def safe_clean(chapter_dir: Path) -> tuple[Path, Path]:
    chapter_dir.mkdir(parents=True, exist_ok=True)
    scans = (chapter_dir / "scans").resolve()
    if scans.parent != chapter_dir.resolve():
        raise RuntimeError("Unsafe scans cleanup target")
    if scans.exists():
        shutil.rmtree(scans)
    scans.mkdir()
    for name in ("stream-map.json", "scan-index.json", "validation.json", ".canonicalize.incomplete"):
        path = chapter_dir / name
        if path.exists():
            path.unlink()
    marker = chapter_dir / ".canonicalize.incomplete"
    marker.write_text("generation in progress\n", encoding="utf-8")
    return scans, marker


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chapter", required=True)
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--extension", required=True)
    parser.add_argument("--width", required=True, type=int)
    parser.add_argument("--width-policy", choices=("strict", "fit-without-upscale"), required=True)
    parser.add_argument("--core-height", type=int, default=6000)
    parser.add_argument("--context", type=int, default=3000)
    parser.add_argument("--view-height", type=int, default=12000)
    parser.add_argument("--minimum-exact-duplicate-height", type=int, default=48)
    parser.add_argument("--chapter-allowlist", default=None, help="Comma-separated chapter ids")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    chapter = canonical_chapter_id(args.chapter)
    if args.chapter_allowlist:
        allowlist = {canonical_chapter_id(item) for item in args.chapter_allowlist.split(",")}
        if chapter not in allowlist:
            raise RuntimeError(f"{chapter} is outside the chapter allowlist")
    extension = args.extension.lower()
    if not extension.startswith("."):
        extension = "." + extension
    if args.width < 1 or args.core_height < 1 or args.context < 0 or args.view_height < args.core_height + 2 * args.context:
        raise ValueError("Invalid width/core/context/view parameters")
    input_dir = args.input_dir.resolve()
    output_root = args.output_root.resolve()
    if output_root == input_dir or output_root.is_relative_to(input_dir):
        raise RuntimeError("Output root may not equal or be nested inside input")
    numbered = discover(input_dir, extension)
    chapter_dir = output_root / "chapters" / chapter
    previous = prior_hash(chapter_dir)

    with tempfile.TemporaryDirectory(prefix=f"comic_stream_{chapter}_") as temp_name:
        cache = Path(temp_name)
        records: list[dict[str, Any]] = []
        previous_image: Image.Image | None = None
        for source_index, path in numbered:
            image, metadata = decode_source(path, args.width, args.width_policy)
            cache_path = cache / f"{source_index:05d}.png"
            image.save(cache_path, format="PNG", compress_level=1)
            overlap = (
                {"candidate_exact_rows": 0, "deleted_rows": 0, "confidence": "not_applicable", "full_pixel_equality_verified": False, "informative_region_verified": False, "reason": "first_source"}
                if previous_image is None
                else exact_overlap(previous_image, image, args.minimum_exact_duplicate_height)
            )
            if previous_image is not None:
                previous_image.close()
            record = {
                "source_index": source_index,
                "source_file": path.name,
                "source_path": str(path),
                **metadata,
                "preceding_boundary_overlap": overlap,
                "deleted_duplicate_rows": overlap["deleted_rows"],
                "_cache_path": cache_path,
            }
            records.append(record)
            previous_image = image
        if previous_image is not None:
            previous_image.close()

        global_y = 0
        for record in records:
            removed = record["deleted_duplicate_rows"]
            retained = record["standardized_size"]["height"] - removed
            record.update({
                "retained_source_y_start": removed,
                "retained_height": retained,
                "global_y_start": global_y,
                "global_y_end": global_y + retained,
            })
            global_y += retained
        chapter_height = global_y

        scans_dir, marker = safe_clean(chapter_dir)
        serializable = [{k: v for k, v in r.items() if k != "_cache_path"} for r in records]
        boundaries = [
            {"boundary_index": i, "previous_file": a["source_file"], "following_file": b["source_file"], "global_y": a["global_y_end"]}
            for i, (a, b) in enumerate(zip(records, records[1:]), start=1)
        ]
        stream_map = {
            "schema_version": 1,
            "chapter": chapter,
            "coordinate_convention": "zero-based half-open [start, end)",
            "input_directory": str(input_dir),
            "global_stream": {"width": args.width, "height": chapter_height, "mode": "RGB", "color_space": "sRGB", "icc_profile_sha256": SRGB_SHA256},
            "normalization_policy": {"extension": extension, "width": args.width, "width_policy": args.width_policy},
            "overlap_policy": {"minimum_exact_rows": args.minimum_exact_duplicate_height, "uncertain_matches": "preserved"},
            "sources": serializable,
            "boundaries": boundaries,
        }
        write_json(chapter_dir / "stream-map.json", stream_map)
        scans = plan_scans(chapter_height, args.core_height, args.context, args.view_height)
        for scan in scans:
            canvas = Image.new("RGB", (args.width, args.view_height), (255, 255, 255))
            y0 = max(0, scan["view_global_start"])
            y1 = min(chapter_height, scan["view_global_end"])
            destination = y0 - scan["view_global_start"]
            if paste_cache(canvas, destination, y0, y1, records) != y1 - y0:
                raise RuntimeError(f"Scan coverage failed: {scan['scan_id']}")
            canvas.save(scans_dir / f"{scan['scan_id']}.png", format="PNG", compress_level=6, icc_profile=SRGB_ICC)
        scan_index = {
            "schema_version": 1,
            "chapter": chapter,
            "chapter_height": chapter_height,
            "parameters": {"CORE_HEIGHT": args.core_height, "CONTEXT": args.context, "VIEW_HEIGHT": args.view_height},
            "ownership_rule": {"anchor_formula": "(global_y0 + global_y1) / 2", "scan_usage": "reading only; final extraction uses source map"},
            "scans": scans,
        }
        write_json(chapter_dir / "scan-index.json", scan_index)

        extractor = Path(__file__).resolve().with_name("extract_global_region.py")
        requests = []
        for boundary in boundaries:
            y = boundary["global_y"]
            requests.append({
                "id": f"boundary_{boundary['boundary_index']:05d}",
                "x0": 0,
                "x1": args.width,
                "global_y0": max(0, y - 32),
                "global_y1": min(chapter_height, y + 32),
                "output": str(cache / f"boundary_{boundary['boundary_index']:05d}.png"),
            })
        batch = cache / "batch.json"
        batch.write_text(json.dumps({"chapter": chapter, "regions": requests}), encoding="utf-8")
        completed = subprocess.run([sys.executable, "-B", str(extractor), "--canonical-root", str(output_root), "--batch-json", str(batch)], capture_output=True, text=True)
        boundary_details = []
        boundary_pass = completed.returncode == 0
        for request in requests:
            actual_path = Path(request["output"])
            passed = False
            if boundary_pass and actual_path.is_file():
                expected = Image.new("RGB", (args.width, request["global_y1"] - request["global_y0"]), (255, 255, 255))
                covered = paste_cache(expected, 0, request["global_y0"], request["global_y1"], records)
                with Image.open(actual_path) as actual:
                    actual.load()
                    passed = covered == expected.height and actual.size == expected.size and ImageChops.difference(actual, expected).getbbox() is None
            boundary_pass = boundary_pass and passed
            boundary_details.append({"id": request["id"], "passed": passed})

        core_pass = scans[0]["core_global_start"] == 0 and scans[-1]["core_global_end"] == chapter_height and all(a["core_global_end"] == b["core_global_start"] for a, b in zip(scans, scans[1:]))
        stream_pass = records[0]["global_y_start"] == 0 and records[-1]["global_y_end"] == chapter_height and all(a["global_y_end"] == b["global_y_start"] for a, b in zip(records, records[1:]))
        scan_pass = True
        for scan in scans:
            with Image.open(scans_dir / f"{scan['scan_id']}.png") as image:
                image.load()
                scan_pass = scan_pass and image.format == "PNG" and image.mode == "RGB" and image.size == (args.width, args.view_height) and bool(image.info.get("icc_profile"))
        current = payload_hash(chapter_dir)
        deterministic = previous is not None and current == previous
        no_unsafe_delete = all(r["deleted_duplicate_rows"] == 0 or r["preceding_boundary_overlap"]["confidence"] == "high" for r in records)
        checks = {
            "input_sequence_continuous": True,
            "global_stream_contiguous": stream_pass and no_unsafe_delete,
            "cores_cover_once": core_pass,
            "all_boundaries_extract_and_match": boundary_pass,
            "scans_match_profile": scan_pass,
            "payload_matches_previous_run_when_available": deterministic,
        }
        static_checks_pass = all(value for key, value in checks.items() if key != "payload_matches_previous_run_when_available")
        status = "PASS" if static_checks_pass and deterministic else ("PENDING_RERUN" if static_checks_pass and previous is None else "FAIL")
        validation = {
            "status": status,
            "checks": checks,
            "metrics": {
                "input_count": len(numbered),
                "stream_width": args.width,
                "stream_height": chapter_height,
                "scan_count": len(scans),
                "boundary_tests_passed": sum(d["passed"] for d in boundary_details),
                "boundary_count": len(boundary_details),
                "deleted_duplicate_boundaries": sum(r["deleted_duplicate_rows"] > 0 for r in records),
                "deleted_duplicate_rows": sum(r["deleted_duplicate_rows"] for r in records),
            },
            "deterministic_rerun": {"previous_available": previous is not None, "previous_sha256": previous, "current_sha256": current, "matches": deterministic},
            "boundary_tests": boundary_details,
        }
        write_json(chapter_dir / "validation.json", validation)
        if validation["status"] == "FAIL":
            raise RuntimeError(f"Validation failed: {chapter_dir / 'validation.json'}")
        marker.unlink(missing_ok=True)
        print(json.dumps({"chapter": chapter, **validation["metrics"], "status": validation["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

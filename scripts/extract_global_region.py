#!/usr/bin/env python3
"""Extract one or many PNG regions directly from a mapped comic source stream."""

from __future__ import annotations

import argparse
import json
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any

from PIL import Image

sys.dont_write_bytecode = True

from canonicalize_chapter import SRGB_ICC, canonical_chapter_id, decode_source


class Loader:
    def __init__(self, maximum: int = 8) -> None:
        self.maximum = maximum
        self.images: OrderedDict[str, Image.Image] = OrderedDict()

    def get(self, path: Path, width: int, policy: str) -> Image.Image:
        key = str(path.resolve())
        if key in self.images:
            image = self.images.pop(key)
            self.images[key] = image
            return image
        image, _ = decode_source(path, width, policy)
        self.images[key] = image
        while len(self.images) > self.maximum:
            _, old = self.images.popitem(last=False)
            old.close()
        return image

    def close(self) -> None:
        for image in self.images.values():
            image.close()
        self.images.clear()


def load_map(root: Path, chapter: str) -> dict[str, Any]:
    path = root.resolve() / "chapters" / chapter / "stream-map.json"
    if not path.is_file():
        raise FileNotFoundError(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("chapter") != chapter:
        raise RuntimeError(f"Chapter mismatch in {path}")
    return data


def extract(data: dict[str, Any], x0: int, x1: int, y0: int, y1: int, loader: Loader) -> Image.Image:
    stream = data["global_stream"]
    width, height = int(stream["width"]), int(stream["height"])
    if not 0 <= x0 < x1 <= width or not 0 <= y0 < y1 <= height:
        raise ValueError("Requested region is outside the global stream")
    policy = data["normalization_policy"]["width_policy"]
    output = Image.new("RGB", (x1 - x0, y1 - y0), (255, 255, 255))
    expected = y0
    contributing = []
    for source in sorted(data["sources"], key=lambda item: item["global_y_start"]):
        a = max(y0, int(source["global_y_start"]))
        b = min(y1, int(source["global_y_end"]))
        if a >= b:
            continue
        if a != expected:
            raise RuntimeError(f"Source-map gap or overlap at global y={expected}")
        image = loader.get(Path(source["source_path"]), width, policy)
        if list(image.size) != [source["standardized_size"]["width"], source["standardized_size"]["height"]]:
            raise RuntimeError(f"Decoded size drift: {source['source_file']}")
        source_y = int(source["retained_source_y_start"]) + a - int(source["global_y_start"])
        output.paste(image.crop((x0, source_y, x1, source_y + b - a)), (0, a - y0))
        contributing.append(source["source_file"])
        expected = b
    if expected != y1:
        raise RuntimeError(f"Source map ended at {expected}; expected {y1}")
    output.info["contributing_sources"] = contributing
    return output


def save(image: Image.Image, output: Path) -> None:
    if output.suffix.lower() != ".png":
        raise ValueError("Output must use .png")
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="PNG", compress_level=6, icc_profile=SRGB_ICC)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canonical-root", required=True, type=Path)
    parser.add_argument("--chapter")
    parser.add_argument("--x0", type=int)
    parser.add_argument("--x1", type=int)
    parser.add_argument("--global-y0", type=int)
    parser.add_argument("--global-y1", type=int)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--batch-json", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    loader = Loader()
    results = []
    try:
        if args.batch_json:
            payload = json.loads(args.batch_json.read_text(encoding="utf-8"))
            chapter = canonical_chapter_id(str(payload["chapter"]))
            data = load_map(args.canonical_root, chapter)
            requests = payload["regions"]
        else:
            required = [args.chapter, args.x0, args.x1, args.global_y0, args.global_y1, args.output]
            if any(value is None for value in required):
                raise ValueError("Single extraction requires chapter, x0, x1, global-y0, global-y1, and output")
            chapter = canonical_chapter_id(args.chapter)
            data = load_map(args.canonical_root, chapter)
            requests = [{
                "id": "single",
                "x0": args.x0,
                "x1": args.x1,
                "global_y0": args.global_y0,
                "global_y1": args.global_y1,
                "output": str(args.output),
            }]
        for request in requests:
            image = extract(data, int(request["x0"]), int(request["x1"]), int(request["global_y0"]), int(request["global_y1"]), loader)
            output = Path(request["output"])
            sources = list(image.info.get("contributing_sources", []))
            save(image, output)
            results.append({"id": request.get("id"), "output": str(output.resolve()), "size": list(image.size), "contributing_sources": sources})
    finally:
        loader.close()
    print(json.dumps({"chapter": chapter, "region_count": len(results), "results": results}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

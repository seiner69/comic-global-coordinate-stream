#!/usr/bin/env python3
"""Create deterministic synthetic image sequences for skill smoke tests."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


def patterned(width: int, height: int, seed: int) -> Image.Image:
    image = Image.new("RGB", (width, height))
    pixels = image.load()
    for y in range(height):
        for x in range(width):
            pixels[x, y] = (
                (x * 17 + y * 11 + seed * 29) % 256,
                (x * 7 + y * 19 + seed * 43) % 256,
                (x * 23 + y * 5 + seed * 61) % 256,
            )
    return image


def save_normal(chapter_dir: Path) -> None:
    for index, height in enumerate((40, 50, 30), start=1):
        patterned(64, height, index).save(chapter_dir / f"{index:03d}.png")


def save_fit(chapter_dir: Path) -> None:
    for index, (width, height) in enumerate(((80, 40), (64, 50), (48, 30)), start=1):
        patterned(width, height, index + 30).save(chapter_dir / f"{index:03d}.png")


def save_overlap(chapter_dir: Path, low_information: bool) -> None:
    first = patterned(64, 80, 11)
    second_tail = patterned(64, 50, 23)
    if low_information:
        blank = Image.new("RGB", (64, 16), "white")
        first.paste(blank, (0, 64))
        second = Image.new("RGB", (64, 66))
        second.paste(blank, (0, 0))
    else:
        second = Image.new("RGB", (64, 66))
        second.paste(first.crop((0, 64, 64, 80)), (0, 0))
    second.paste(second_tail, (0, 16))
    first.save(chapter_dir / "001.png")
    second.save(chapter_dir / "002.png")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--case", choices=("normal", "fit", "overlap", "white"), required=True)
    args = parser.parse_args()

    chapter_dir = args.root.resolve() / "ch_001"
    chapter_dir.mkdir(parents=True, exist_ok=False)
    if args.case == "normal":
        save_normal(chapter_dir)
    elif args.case == "fit":
        save_fit(chapter_dir)
    else:
        save_overlap(chapter_dir, low_information=args.case == "white")
    print(chapter_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

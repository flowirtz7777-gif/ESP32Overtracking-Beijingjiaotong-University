"""Crop the bottom footnote band from copied figures.

The source figures carry a one-line footer beginning with
"中期答辩临时训练：基于接触标签..." which must not appear on slides.
This script removes the footer by finding, from the bottom upward, the first
all-white separator row directly above it, then cropping there.

Reads and rewrites files only inside ./img. Originals are untouched.
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
IMG = HERE / "img"
WHITE = 250          # pixel value treated as white
MIN_GAP = 3          # rows of near-blank needed to be a separator
MAX_CROP_FRAC = 0.12  # never crop more than 12% of the height


def row_is_blank(arr, row, tol=WHITE):
    return bool(np.all(arr[row] >= tol))


def find_crop_row(im):
    """Return the row index where the footer band starts, or None."""
    arr = np.asarray(im.convert("RGB"))
    h, w, _ = arr.shape
    limit = int(h * MAX_CROP_FRAC)
    # Walk upward from the bottom; the footer sits in the last few percent.
    # Find a run of blank rows that separates content from footer.
    bottom = h - 1
    # skip trailing blank rows
    while bottom > h - limit and row_is_blank(arr, bottom):
        bottom -= 1
    if bottom <= h - limit:
        return None
    # now bottom is the last non-blank row (inside footer text)
    # find the blank separator above the footer block
    row = bottom
    while row > h - limit and not row_is_blank(arr, row):
        row -= 1
    # row is now a blank separator (or we hit the limit)
    if row <= h - limit:
        return None
    # move to the top of that blank run
    top = row
    while top > 0 and row_is_blank(arr, top):
        top -= 1
    # require a real gap, otherwise this is just inter-word whitespace
    if row - top < MIN_GAP:
        return None
    return top + 1


def main():
    report = []
    for path in sorted(IMG.glob("*.png")):
        im = Image.open(path)
        crop_row = find_crop_row(im)
        if crop_row is None:
            report.append((path.name, im.size, "kept", ""))
            continue
        new = im.crop((0, 0, im.width, crop_row))
        new.save(path, optimize=True)
        report.append((path.name, im.size, "cropped", f"{im.height}->{new.height}"))
    for name, size, action, detail in report:
        print(f"{name:30s} {size[0]:5d}x{size[1]:5d}  {action:8s} {detail}")


if __name__ == "__main__":
    main()

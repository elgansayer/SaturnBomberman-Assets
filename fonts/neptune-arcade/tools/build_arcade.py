#!/usr/bin/env python3
"""Build the original Neptune Arcade TrueType font without external font inputs.

Requires fonttools==4.61.1. Glyph source is a human-editable pixel grid; outlines
are exact rectangles, so 8px and integer multiples land on the grid. No raster
art from a commercial game is an input. The file is reproducible byte for byte.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import unicodedata

from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen

ROOT = Path(__file__).resolve().parents[1]
EPOCH = 3876211200  # 2026-10-30 00:00:00, in the OpenType 1904 epoch.


def glyph_name(character: str) -> str:
    return f"uni{ord(character):04X}"


def pixels(rows: str, top: int = 7) -> set[tuple[int, int]]:
    result: set[tuple[int, int]] = set()
    for y, row in enumerate(rows.split("/")):
        if len(row) != 7 or set(row) - {".", "#"}:
            raise ValueError(f"Expected a seven-column pixel row, got {row!r}")
        result.update((x, top - y - 1) for x, ink in enumerate(row) if ink == "#")
    return result


def outline(ink: set[tuple[int, int]], unit: int):
    """Combine vertical runs into rectangles for small, exact-grid outlines."""
    pen = TTGlyphPen(None)
    for x in range(7):
        remaining = sorted(y for px, y in ink if px == x)
        while remaining:
            low = high = remaining.pop(0)
            while remaining and remaining[0] == high + 1:
                high = remaining.pop(0)
            left, right = x * unit, (x + 1) * unit
            bottom, top = low * unit, (high + 1) * unit
            pen.moveTo((left, bottom))
            pen.lineTo((left, top))
            pen.lineTo((right, top))
            pen.lineTo((right, bottom))
            pen.closePath()
    return pen.glyph()


def build(source: Path, destination: Path) -> dict:
    data = json.loads(source.read_text(encoding="utf-8"))
    unit = int(data["grid"]["units_per_pixel"])
    em = int(data["grid"]["units_per_em"])
    advance = int(data["grid"]["advance_pixels"]) * unit
    originals = {ch: pixels(rows) for ch, rows in data["glyphs"].items()}
    originals["\u00a0"] = set()  # A real non-breaking space, with the same advance.
    marks = data["marks"]
    all_ink = dict(originals)
    # Combining marks retain zero advance and GPOS anchors. Their local origin
    # is the baseline; the base anchor positions them above/below the base ink.
    for ch, mark in marks.items():
        all_ink[ch] = pixels(mark["rows"], len(mark["rows"].split("/")))

    composed_count = 0
    for codepoint in [*range(0xA0, 0x250), *range(0x1E00, 0x1F00)]:
        ch = chr(codepoint)
        decomposition = unicodedata.normalize("NFD", ch)
        if ch in all_ink or len(decomposition) < 2:
            continue
        base, *accents = decomposition
        if base not in originals or not all(accent in marks for accent in accents):
            continue
        # An accented i/j replaces its tittle, as in the GPOS/ccmp path below.
        ink = set(originals[base])
        if base in "ij" and any(marks[a]["position"] == "top" for a in accents):
            ink = {(x, y) for x, y in ink if y < 6}
        upper = max((y for _, y in ink), default=0) + 2
        lower = min((y for _, y in ink), default=0) - 1
        for accent in accents:
            mark = marks[accent]
            accent_ink = all_ink[accent]
            height = len(mark["rows"].split("/"))
            if mark["position"] == "top":
                ink.update((x, y + upper) for x, y in accent_ink)
                upper += height + 1
            elif mark["position"] == "bottom":
                ink.update((x, y + lower - height) for x, y in accent_ink)
                lower -= height + 1
            else:
                ink.update((x, y + 5) for x, y in accent_ink)
        all_ink[ch] = ink
        composed_count += 1

    chars = sorted(all_ink, key=ord)
    names = [".notdef", *(glyph_name(ch) for ch in chars), "dotlessj"]
    shapes = {glyph_name(ch): outline(all_ink[ch], unit) for ch in chars}
    shapes[".notdef"] = outline(pixels("#######/#.....#/#.#.#.#/#..#..#/#.#.#.#/#.....#/#######"), unit)
    shapes["dotlessj"] = outline({p for p in originals["j"] if p[1] < 6}, unit)
    metrics = {name: (advance, 0) for name in names}
    for ch in marks:
        metrics[glyph_name(ch)] = (0, 0)

    fb = FontBuilder(em, isTTF=True)
    fb.setupGlyphOrder(names)
    fb.setupCharacterMap({ord(ch): glyph_name(ch) for ch in chars})
    fb.setupGlyf(shapes)
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=1000, descent=-300, lineGap=0)
    fb.setupNameTable({
        "familyName": "Neptune Arcade",
        "styleName": "Regular",
        "uniqueFontIdentifier": "NeptuneArcade-Regular-1.000",
        "fullName": "Neptune Arcade Regular",
        "psName": "NeptuneArcade-Regular",
        "version": "Version 1.000",
        "copyright": "Copyright 2026 Neptune Arcade contributors.",
        "description": "Original stepped arcade display font inspired by 1990s console menus. Native grid: 8px. Not an extracted or official game font.",
        "licenseDescription": "This Font Software is licensed under the SIL Open Font License, Version 1.1. No Reserved Font Names.",
        "licenseInfoURL": "https://openfontlicense.org/",
    })
    # Windows clipping extents include the complete composed repertoire. The
    # hhea/typographic line metric stays compact for ordinary game UI; very tall
    # stacked accents need additional line spacing in a multiline control.
    highest = max(y for ink in all_ink.values() for _, y in ink) + 1
    lowest = min(y for ink in all_ink.values() for _, y in ink)
    fb.setupOS2(sTypoAscender=1000, sTypoDescender=-300, sTypoLineGap=0,
                usWinAscent=highest * unit, usWinDescent=-lowest * unit,
                sxHeight=500, sCapHeight=700, usWeightClass=700,
                fsSelection=0x40, fsType=0)
    fb.setupPost(isFixedPitch=1)
    fb.setupMaxp()
    font = fb.font
    font["head"].created = EPOCH
    font["head"].modified = EPOCH
    font.recalcTimestamp = False

    feature_lines = ["languagesystem DFLT dflt;", "languagesystem latn dflt;"]
    for ch, mark in marks.items():
        position = mark["position"]
        anchor_y = len(mark["rows"].split("/")) * unit if position == "bottom" else 0
        feature_lines.append(f"markClass {glyph_name(ch)} <anchor 350 {anchor_y}> @MC_{position};")
    # Above marks remove the i/j tittle before positioning, preserving NFD text.
    top_marks = " ".join(glyph_name(ch) for ch, mark in marks.items() if mark["position"] == "top")
    feature_lines.extend([
        f"@TOP = [{top_marks}];",
        "feature ccmp {",
        f"sub {glyph_name('i')}' @TOP by {glyph_name('ı')};",
        f"sub {glyph_name('j')}' @TOP by dotlessj;",
        "} ccmp;",
        "feature mark {",
    ])
    for ch, ink in all_ink.items():
        if not ink or ch in marks:
            continue
        top = (max(y for _, y in ink) + 2) * unit
        bottom = (min(y for _, y in ink) - 1) * unit
        feature_lines.append(f"pos base {glyph_name(ch)} <anchor 350 {top}> mark @MC_top <anchor 350 {bottom}> mark @MC_bottom <anchor 350 500> mark @MC_horn;")
    feature_lines.append("pos base dotlessj <anchor 350 600> mark @MC_top <anchor 350 -400> mark @MC_bottom <anchor 350 500> mark @MC_horn;")
    feature_lines.append("} mark;")
    # Position later marks relative to a previous mark of the same class.
    feature_lines.append("feature mkmk {")
    for ch, mark in marks.items():
        position = mark["position"]
        if position == "horn":
            continue
        height = len(mark["rows"].split("/")) * unit
        y = height + unit if position == "top" else -unit
        feature_lines.append(f"pos mark {glyph_name(ch)} <anchor 350 {y}> mark @MC_{position};")
    feature_lines.append("} mkmk;")
    addOpenTypeFeaturesFromString(font, "\n".join(feature_lines))

    destination.parent.mkdir(parents=True, exist_ok=True)
    font.save(destination)
    return {
        "path": str(destination),
        "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        "encoded_characters": len(chars),
        "composed_characters": composed_count,
        "glyphs": len(names),
        "units_per_em": em,
        "native_pixel_size": em // unit,
        "highest_pixel": highest,
        "lowest_pixel": lowest,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "source/arcade_glyphs.json")
    parser.add_argument("--output", type=Path, default=ROOT / "dist/NeptuneArcade.ttf")
    parser.add_argument("--check", action="store_true", help="Rebuild into a temporary directory and fail if the checked-in output differs; never overwrites it.")
    args = parser.parse_args()
    if args.check:
        if not args.output.is_file():
            parser.exit(1, f"Missing checked-in font: {args.output}\n")
        with tempfile.TemporaryDirectory(prefix="neptune-arcade-check-") as temporary:
            rebuilt = Path(temporary) / "NeptuneArcade.ttf"
            report = build(args.source, rebuilt)
            if rebuilt.read_bytes() != args.output.read_bytes():
                parser.exit(1, "Font is stale: rebuild with tools/build_arcade.py\n")
            report.update(path=str(args.output), reproducible=True)
    else:
        report = build(args.source, args.output)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

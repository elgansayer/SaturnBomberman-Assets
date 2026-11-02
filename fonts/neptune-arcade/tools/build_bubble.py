#!/usr/bin/env python3
"""Build Neptune Bubble from original curved skeletons, with no font inputs.

Dependencies: fonttools==4.61.1, Pillow==12.3.0, numpy==2.3.5,
contourpy==1.3.3. The raster union resolves intersecting inflated strokes;
contours are simplified, fitted with closed cubic splines, and converted to
real TrueType quadratic curves. No raster artwork is used as an input.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import tempfile
import unicodedata

import contourpy
import numpy as np
from PIL import Image, ImageDraw
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.ttGlyphPen import TTGlyphPen

ROOT = Path(__file__).resolve().parents[1]
EPOCH = 3876211200
RASTER_STEP = 2.0


def name(ch):
    return f"uni{ord(ch):04X}"


def paths(text):
    tokens = re.findall(r"[MLQCZ]|-?\d+(?:\.\d+)?", text)
    result, points = [], []
    index = 0
    def point():
        nonlocal index
        p = np.array([float(tokens[index]), float(tokens[index + 1])])
        index += 2
        return p
    while index < len(tokens):
        command = tokens[index]
        index += 1
        if command == "M":
            if points:
                result.append(points)
            points = [point()]
        elif command == "L":
            points.append(point())
        elif command in {"Q", "C"}:
            start = points[-1]
            if command == "Q":
                control, end = point(), point()
                for t in np.linspace(0, 1, 35)[1:]:
                    points.append((1-t)**2*start + 2*(1-t)*t*control + t*t*end)
            else:
                control1, control2, end = point(), point(), point()
                for t in np.linspace(0, 1, 45)[1:]:
                    points.append((1-t)**3*start + 3*(1-t)**2*t*control1 + 3*(1-t)*t*t*control2 + t**3*end)
        elif command == "Z":
            points.append(points[0])
        else:
            raise ValueError(f"Unknown skeleton command {command}")
    if points:
        result.append(points)
    return result


def rdp(points, epsilon=2.1):
    """Remove raster stair steps before fitting the smooth closed contour."""
    if len(points) < 3:
        return points
    start, end = points[0], points[-1]
    delta = end - start
    length = float(np.linalg.norm(delta))
    if length < 1e-9:
        distances = np.linalg.norm(points - start, axis=1)
    else:
        distances = np.abs(delta[0]*(start[1]-points[:, 1]) - delta[1]*(start[0]-points[:, 0]))/length
    farthest = int(np.argmax(distances))
    if distances[farthest] > epsilon:
        return np.vstack([rdp(points[:farthest+1], epsilon)[:-1], rdp(points[farthest:], epsilon)])
    return np.array([start, end])


def render_outline(spec, default_width):
    strokes = [p for text in spec["strokes"] for p in paths(text)]
    if not strokes:
        return TTGlyphPen(None).glyph(), (0, 0, 0, 0)
    width = spec.get("width", default_width)
    points = np.vstack(strokes)
    padding = width/2 + 10
    xmin, ymin = np.floor((np.min(points, axis=0)-padding)/RASTER_STEP)*RASTER_STEP
    xmax, ymax = np.ceil((np.max(points, axis=0)+padding)/RASTER_STEP)*RASTER_STEP
    bitmap = Image.new("L", (int((xmax-xmin)/RASTER_STEP)+1, int((ymax-ymin)/RASTER_STEP)+1))
    draw = ImageDraw.Draw(bitmap)
    radius = width/RASTER_STEP/2
    for stroke in strokes:
        image_points = [((x-xmin)/RASTER_STEP, (ymax-y)/RASTER_STEP) for x, y in stroke]
        # Explicit overlapping discs form a robust union, including tight
        # curved joins; polygonal wide-line joins can introduce tiny internal
        # wedges which would otherwise become unwanted outline contours.
        for start, end in zip(image_points, image_points[1:]):
            distance = math.hypot(end[0]-start[0], end[1]-start[1])
            for t in np.linspace(0, 1, max(2, math.ceil(distance/2))):
                x, y = start[0]+t*(end[0]-start[0]), start[1]+t*(end[1]-start[1])
                draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=255)
    generator = contourpy.contour_generator(z=np.asarray(bitmap, dtype=float)/255)
    boundaries = generator.lines(0.5)
    pen = TTGlyphPen(None)
    curved = Cu2QuPen(pen, max_err=0.9, reverse_direction=False)
    total_bounds = []
    for boundary in boundaries:
        vertices = np.column_stack([xmin+boundary[:, 0]*RASTER_STEP, ymax-boundary[:, 1]*RASTER_STEP])
        if np.linalg.norm(vertices[0]-vertices[-1]) < 0.01:
            vertices = vertices[:-1]
        # Split a closed loop at the point furthest from its start, simplifying
        # each arc independently so the repeated endpoint cannot collapse it.
        farthest = int(np.argmax(np.linalg.norm(vertices-vertices[0], axis=1)))
        simplified = np.vstack([rdp(vertices[:farthest+1])[:-1], rdp(np.vstack([vertices[farthest:], vertices[:1]]))[:-1]])
        if len(simplified) < 3:
            continue
        total_bounds.extend(simplified)
        curved.moveTo(tuple(simplified[0]))
        count = len(simplified)
        for i in range(count):
            previous = simplified[(i-1) % count]
            current = simplified[i]
            following = simplified[(i+1) % count]
            after = simplified[(i+2) % count]
            curved.curveTo(tuple(current+(following-previous)/6), tuple(following-(after-current)/6), tuple(following))
        curved.closePath()
    if not total_bounds:
        raise ValueError("Skeleton produced no contour")
    bounds = np.array(total_bounds)
    bbox = (*np.min(bounds, axis=0), *np.max(bounds, axis=0))
    return pen.glyph(), tuple(int(round(v)) for v in bbox)


def build(source, output):
    data = json.loads(source.read_text(encoding="utf-8"))
    originals = data["glyphs"]
    marks = data["marks"]
    shapes, boxes, metrics, cmap = {}, {}, {}, {}
    for ch, spec in originals.items():
        glyph = name(ch)
        shapes[glyph], boxes[glyph] = render_outline(spec, data["stroke_width"])
        metrics[glyph] = (spec["advance"], boxes[glyph][0])
        cmap[ord(ch)] = glyph
    for ch, spec in marks.items():
        glyph = name(ch)
        shapes[glyph], boxes[glyph] = render_outline(spec, spec["width"])
        metrics[glyph] = (0, boxes[glyph][0])
        cmap[ord(ch)] = glyph
    shapes[".notdef"], boxes[".notdef"] = render_outline({"width": 110, "strokes": ["M150 100 L150 600 L600 600 L600 100 Z", "M260 230 L490 470", "M260 470 L490 230"]}, 110)
    metrics[".notdef"] = (750, boxes[".notdef"][0])
    dotlessj = dict(originals["j"], strokes=originals["j"]["strokes"][:1])
    shapes["dotlessj"], boxes["dotlessj"] = render_outline(dotlessj, data["stroke_width"])
    metrics["dotlessj"] = (dotlessj["advance"], boxes["dotlessj"][0])

    def composite(glyph, components, advance):
        pen = TTGlyphPen(shapes)
        xmins, ymins, xmaxs, ymaxs = [], [], [], []
        for base, x, y in components:
            pen.addComponent(base, (1, 0, 0, 1, x, y))
            xmin, ymin, xmax, ymax = boxes[base]
            xmins.append(xmin+x); ymins.append(ymin+y)
            xmaxs.append(xmax+x); ymaxs.append(ymax+y)
        shapes[glyph] = pen.glyph()
        boxes[glyph] = (min(xmins), min(ymins), max(xmaxs), max(ymaxs))
        metrics[glyph] = (advance, min(xmins))

    composite(name("\u00a0"), [(name(" "), 0, 0)], originals[" "]["advance"])
    cmap[0xA0] = name("\u00a0")
    for char, base in [("¡", "!"), ("¿", "?")]:
        glyph = name(char)
        pen = TTGlyphPen(shapes)
        advance = originals[base]["advance"]
        pen.addComponent(name(base), (-1, 0, 0, -1, advance, 700))
        shapes[glyph] = pen.glyph()
        xmin, ymin, xmax, ymax = boxes[name(base)]
        boxes[glyph] = (advance-xmax, 700-ymax, advance-xmin, 700-ymin)
        metrics[glyph] = (advance, boxes[glyph][0])
        cmap[ord(char)] = glyph

    composed_count = 0
    for codepoint in [*range(0xA0, 0x250), *range(0x1E00, 0x1F00)]:
        char = chr(codepoint)
        decomposition = unicodedata.normalize("NFD", char)
        if codepoint in cmap or len(decomposition) < 2:
            continue
        base, *accents = decomposition
        if base not in originals or not all(a in marks for a in accents):
            continue
        glyphbase = name(base)
        if base in "ij" and any(marks[a]["position"] == "top" for a in accents):
            glyphbase = name("ı") if base == "i" else "dotlessj"
        advance = originals[base]["advance"]
        components = [(glyphbase, 0, 0)]
        top, bottom = boxes[glyphbase][3]+35, boxes[glyphbase][1]-35
        for accent in accents:
            glyphmark = name(accent)
            xmin, ymin, xmax, ymax = boxes[glyphmark]
            position = marks[accent]["position"]
            if position == "top":
                x, y = advance//2, top-ymin
                top = y+ymax+35
            elif position == "bottom":
                x, y = advance//2, bottom-ymax
                bottom = y+ymin-35
            else:
                x, y = advance-125, boxes[glyphbase][3]-85
            components.append((glyphmark, x, y))
        composite(name(char), components, advance)
        cmap[codepoint] = name(char)
        composed_count += 1

    order = [".notdef", *sorted((g for g in shapes if g != ".notdef"))]
    fb = FontBuilder(data["units_per_em"], isTTF=True)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap(cmap)
    fb.setupGlyf(shapes)
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=1000, descent=-300, lineGap=0)
    fb.setupNameTable({
        "familyName": "Neptune Bubble", "styleName": "Regular",
        "uniqueFontIdentifier": "NeptuneBubble-Regular-1.000",
        "fullName": "Neptune Bubble Regular", "psName": "NeptuneBubble-Regular",
        "version": "Version 1.000", "copyright": data["copyright"],
        "description": "Original inflated cartoon display lettering with smooth quadratic curves. Inspired by the friendly bubble lettering of 1990s console games; not an official or extracted game font.",
        "licenseDescription": "This Font Software is licensed under the SIL Open Font License, Version 1.1. No Reserved Font Names.",
        "licenseInfoURL": "https://openfontlicense.org/",
    })
    fb.setupOS2(sTypoAscender=1000, sTypoDescender=-300, sTypoLineGap=0,
                usWinAscent=max(b[3] for b in boxes.values()),
                usWinDescent=-min(b[1] for b in boxes.values()),
                sxHeight=500, sCapHeight=700, usWeightClass=800, fsSelection=0x40, fsType=0)
    fb.setupPost(isFixedPitch=0)
    fb.setupMaxp()
    font = fb.font
    font["head"].created = EPOCH
    font["head"].modified = EPOCH
    font.recalcTimestamp = False

    features = ["languagesystem DFLT dflt;", "languagesystem latn dflt;"]
    for ch, mark in marks.items():
        glyph = name(ch)
        position = mark["position"]
        anchor = boxes[glyph][1] if position == "top" else boxes[glyph][3] if position == "bottom" else 0
        features.append(f"markClass {glyph} <anchor 0 {anchor}> @MC_{position};")
    topmarks = " ".join(name(ch) for ch, mark in marks.items() if mark["position"] == "top")
    features.extend([f"@TOP = [{topmarks}];", "feature ccmp {", f"sub {name('i')}' @TOP by {name('ı')};", f"sub {name('j')}' @TOP by dotlessj;", "} ccmp;", "feature mark {"])
    for glyph in order:
        if glyph in {name(ch) for ch in marks} or glyph == ".notdef":
            continue
        xmin, ymin, xmax, ymax = boxes[glyph]
        advance = metrics[glyph][0]
        features.append(f"pos base {glyph} <anchor {advance//2} {ymax+35}> mark @MC_top <anchor {advance//2} {ymin-35}> mark @MC_bottom <anchor {advance-125} {ymax-85}> mark @MC_horn;")
    features.extend(["} mark;", "feature mkmk {"])
    for ch, mark in marks.items():
        position = mark["position"]
        if position == "horn":
            continue
        glyph = name(ch)
        anchor = boxes[glyph][3]+35 if position == "top" else boxes[glyph][1]-35
        features.append(f"pos mark {glyph} <anchor 0 {anchor}> mark @MC_{position};")
    features.append("} mkmk;")
    addOpenTypeFeaturesFromString(font, "\n".join(features))
    output.parent.mkdir(parents=True, exist_ok=True)
    font.save(output)
    return {"path": str(output), "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "encoded_characters": len(cmap), "composed_characters": composed_count,
            "glyphs": len(order), "units_per_em": 1000, "cap_height": 700,
            "source": "original curved skeletons; inflated round strokes; quadratic contours"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT/"source/bubble_glyphs.json")
    parser.add_argument("--output", type=Path, default=ROOT/"dist/NeptuneBubble.ttf")
    parser.add_argument("--check", action="store_true", help="Rebuild temporarily; compare without overwriting the checked-in font")
    args = parser.parse_args()
    if args.check:
        if not args.output.is_file():
            parser.exit(1, f"Missing checked-in font: {args.output}\n")
        with tempfile.TemporaryDirectory(prefix="neptune-bubble-check-") as temporary:
            rebuilt = Path(temporary)/"NeptuneBubble.ttf"
            report = build(args.source, rebuilt)
            if rebuilt.read_bytes() != args.output.read_bytes():
                parser.exit(1, "Bubble font is stale: rebuild with tools/build_bubble.py\n")
            report.update(path=str(args.output), reproducible=True)
    else:
        report = build(args.source, args.output)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

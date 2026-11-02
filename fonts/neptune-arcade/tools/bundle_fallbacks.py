#!/usr/bin/env python3
"""Copy unmodified OFL Noto fallbacks and record deterministic Unicode coverage.

Requires fonttools. Build from installed Noto files, or pass --source-dir,
--cjk-path, --core-license and --cjk-license for a saved upstream source set.
--check verifies the bundled bytes and manifests without system fonts or network.
The original custom display face is built separately by build_arcade.py.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import unicodedata

from fontTools.ttLib import TTCollection, TTFont


PACKAGE = Path(__file__).resolve().parents[1]
SCRIPTS = [
    "Arabic", "Hebrew", "Armenian", "Georgian", "Ethiopic",
    "Devanagari", "Bengali", "Gujarati", "Gurmukhi", "Oriya", "Tamil",
    "Telugu", "Kannada", "Malayalam", "Sinhala", "Thai", "Lao", "Khmer",
    "Myanmar", "Mongolian", "Syriac", "Thaana", "NKo", "Tifinagh", "Cherokee",
    "CanadianAboriginal", "Adlam", "Vai", "Bamum", "Lisu", "Yi", "Javanese",
    "Sundanese", "Balinese", "Batak", "Buginese", "Cham", "MeeteiMayek",
    "OlChiki", "HanifiRohingya", "TaiTham", "TaiViet", "NewTaiLue", "Miao",
]
CORE_FILES = (
    ["NotoSans-Regular.ttf"]
    + [f"NotoSans{script}-Regular.ttf" for script in SCRIPTS]
    + ["NotoSerifTibetan-Regular.ttf", "NotoSansSymbols-Regular.ttf",
       "NotoSansSymbols2-Regular.ttf", "NotoSansMath-Regular.ttf"]
)
CJK_FILE = "NotoSansCJK-Bold.ttc"
FONT_FILES = CORE_FILES + [CJK_FILE]
CJK_FACES = {"ja": 0, "ko": 1, "zh_Hans": 2, "zh_Hant": 3, "zh_HK": 4}
LICENSE_FILES = ["Noto-core-copyright.txt", "Noto-CJK-copyright.txt", "OFL-1.1.txt", "NOTICE.txt"]


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def fingerprint(path: Path) -> dict:
    data = path.read_bytes()
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def face_metadata(font: TTFont, index: int) -> tuple[dict, set[int]]:
    names = font["name"]
    chars = {cp for cp, glyph in font.getBestCmap().items() if glyph != ".notdef"}
    return ({
        "index": index,
        "family": names.getDebugName(1),
        "style": names.getDebugName(2),
        "version": names.getDebugName(5),
        "copyright": names.getDebugName(0),
        "trademark": names.getDebugName(7),
        "license_description": names.getDebugName(13),
        "license_url": names.getDebugName(14),
        "mapped_codepoints": len(chars),
    }, chars)


def analyze_font(path: Path) -> tuple[list[dict], set[int]]:
    faces, chars = [], set()
    if path.suffix == ".ttc":
        collection = TTCollection(path, lazy=True)
        try:
            for i, font in enumerate(collection.fonts):
                metadata, mapped = face_metadata(font, i)
                faces.append(metadata)
                chars.update(mapped)
        finally:
            collection.close()
    else:
        with TTFont(path, lazy=True) as font:
            metadata, chars = face_metadata(font, 0)
            faces.append(metadata)
    return faces, chars


def ranges(codepoints: set[int]) -> list[str]:
    result = []
    first = previous = None
    for cp in sorted(codepoints):
        if first is None:
            first = previous = cp
        elif cp == previous + 1:
            previous = cp
        else:
            result.append(f"U+{first:04X}" if first == previous else f"U+{first:04X}-U+{previous:04X}")
            first = previous = cp
    if first is not None:
        result.append(f"U+{first:04X}" if first == previous else f"U+{first:04X}-U+{previous:04X}")
    return result


def derive_manifests(package: Path) -> tuple[dict, dict]:
    entries, combined = [], set()
    for filename in FONT_FILES:
        path = package / "fallbacks" / filename
        faces, chars = analyze_font(path)
        is_cjk = filename == CJK_FILE
        entries.append({
            "path": f"fallbacks/{filename}",
            **fingerprint(path),
            "license": "OFL-1.1",
            "upstream": "https://github.com/notofonts/noto-cjk" if is_cjk else "https://github.com/notofonts/noto-fonts",
            "license_notice": "licenses/Noto-CJK-copyright.txt" if is_cjk else "licenses/Noto-core-copyright.txt",
            "modifications": "None; byte-for-byte source copy, with OpenType shaping tables intact.",
            "faces": faces,
        })
        combined.update(chars)
    samples = json.loads((package / "sample-texts.json").read_text(encoding="utf-8"))
    sample_results = []
    for sample in samples["samples"]:
        # Formatting controls (e.g. ZWJ in Sinhala) affect shaping but have no ink.
        # Retain them in sample text while excluding them from cmap requirements.
        required = {ord(char) for char in sample["text"] if unicodedata.category(char) not in {"Cc", "Cf"}}
        missing = required - combined
        if missing:
            raise ValueError(f"{sample['locale']} sample lacks glyphs: {ranges(missing)}")
        sample_results.append({"locale": sample["locale"], "required_codepoints": len(required), "missing_codepoints": []})
    font_bytes = sum(entry["bytes"] for entry in entries)
    sources = {
        "schema_version": 1,
        "scope": "Unmodified bundled fallback font files only; the original display font has separate build provenance.",
        "reference_source_distribution": "Debian fonts-noto-core 20201225-2 and fonts-noto-cjk 1:20240730+repack1-1. When rebuilding from other directories, the actual file hashes and internal versions below identify the inputs.",
        "font_file_count": len(entries),
        "font_bytes": font_bytes,
        "cjk_face_indices": CJK_FACES,
        "fonts": entries,
        "license_files": [{"path": f"licenses/{name}", **fingerprint(package / "licenses" / name)} for name in LICENSE_FILES],
        "sample_texts": {"path": "sample-texts.json", **fingerprint(package / "sample-texts.json")},
    }
    coverage = {
        "schema_version": 1,
        "coverage_type": "Union of mapped codepoints in the bundled fallback fonts; not a claim of complete language or Unicode support.",
        "all_unicode": False,
        "codepoint_count": len(combined),
        "font_file_count": len(entries),
        "font_bytes": font_bytes,
        "script_families": ["Latin", "Greek", "Cyrillic", "Han", "Hiragana", "Katakana", "Hangul"] + SCRIPTS + ["Tibetan", "Symbols", "Mathematical symbols"],
        "cjk_face_indices": CJK_FACES,
        "limitations": [
            "Unicode is an encoding, not a single language. This bounded bundle does not cover every Unicode character or language.",
            "Script-family labels indicate included font families, not exhaustive coverage of every character assigned to each script.",
            "Newer Unicode additions, some rare CJK ideographs, historical scripts, color emoji and emoji sequences may be absent.",
            "Cmap presence does not prove correct shaping, positioning, line breaking, translation quality or suitable size; review rendered samples in Godot.",
            "Han glyph forms must be selected by locale; use JP/SC/TC/KR/HK faces of the shared TTC rather than inferring a region from codepoints.",
            "No system font fallback is needed for the sample strings. Additional text must be checked against these ranges and rendered before shipping.",
        ],
        "sample_count": len(sample_results),
        "samples": sample_results,
        "unicode_ranges": ranges(combined),
    }
    return sources, coverage


def license_text(notice: str) -> str:
    for paragraph in notice.split("\n\n"):
        if paragraph.startswith("License: OFL-1.1\n "):
            body = "\n".join("" if line == " ." else line[1:] for line in paragraph.splitlines()[1:])
            return "SIL OPEN FONT LICENSE Version 1.1 - 26 February 2007\n\n" + body + "\n"
    raise ValueError("Full OFL-1.1 text not found in the supplied core license notice")


def bundle(args: argparse.Namespace) -> None:
    package = args.output
    for source in [args.source_dir / filename for filename in CORE_FILES] + [args.cjk_path, args.core_license, args.cjk_license]:
        if not source.is_file():
            raise ValueError(f"Required source file is absent: {source}")
    (package / "fallbacks").mkdir(parents=True, exist_ok=True)
    (package / "licenses").mkdir(parents=True, exist_ok=True)
    if package.resolve() != PACKAGE:
        shutil.copyfile(PACKAGE / "sample-texts.json", package / "sample-texts.json")
    for filename in CORE_FILES:
        shutil.copyfile(args.source_dir / filename, package / "fallbacks" / filename)
    shutil.copyfile(args.cjk_path, package / "fallbacks" / CJK_FILE)
    shutil.copyfile(args.core_license, package / "licenses" / "Noto-core-copyright.txt")
    shutil.copyfile(args.cjk_license, package / "licenses" / "Noto-CJK-copyright.txt")
    core_notice = args.core_license.read_text(encoding="utf-8")
    (package / "licenses" / "OFL-1.1.txt").write_text(license_text(core_notice), encoding="utf-8")
    notice_lines = [
        "Bundled Noto fallback fonts are unmodified and licensed under SIL OFL 1.1.",
        "The full license and upstream package notices accompany this file.",
        "Debian packaging-specific GPL sections concern packaging, not the font files.",
        "The following copyright notices are copied from each bundled font's name table.",
        "Embedded font names and notices remain intact. No upstream endorsement is implied.", "",
    ]
    for filename in FONT_FILES:
        faces, _ = analyze_font(package / "fallbacks" / filename)
        notice_lines.append(filename)
        for copyright_notice in dict.fromkeys(face["copyright"] for face in faces):
            notice_lines.append(copyright_notice or "See embedded font name table and upstream package notice.")
        notice_lines.append("")
    (package / "licenses" / "NOTICE.txt").write_text("\n".join(notice_lines), encoding="utf-8")
    sources, coverage = derive_manifests(package)
    (package / "sources.json").write_bytes(json_bytes(sources))
    (package / "coverage.json").write_bytes(json_bytes(coverage))
    print(f"Bundled {sources['font_file_count']} files, {sources['font_bytes']:,} bytes; {coverage['codepoint_count']:,} mapped codepoints, {coverage['sample_count']} sample strings.")


def check(package: Path) -> None:
    expected_sources = json.loads((package / "sources.json").read_text(encoding="utf-8"))
    actual_fonts = {path.name for path in (package / "fallbacks").iterdir() if path.suffix.lower() in {".ttf", ".ttc", ".otf"}}
    if actual_fonts != set(FONT_FILES):
        raise ValueError("Fallback directory differs from the expected bounded font set")
    # Check fingerprints first, so changes cannot silently regenerate their own pins.
    for entry in expected_sources["fonts"] + expected_sources["license_files"] + [expected_sources["sample_texts"]]:
        actual = fingerprint(package / entry["path"])
        if any(actual[key] != entry[key] for key in ("bytes", "sha256")):
            raise ValueError(f"Pinned file differs: {entry['path']}")
    sources, coverage = derive_manifests(package)
    if sources != expected_sources:
        raise ValueError("sources.json disagrees with bundled font metadata or the expected file list")
    if coverage != json.loads((package / "coverage.json").read_text(encoding="utf-8")):
        raise ValueError("coverage.json disagrees with bundled character coverage or samples")
    print(f"PASS: {sources['font_file_count']} fallback fingerprints, licenses and metadata; {coverage['codepoint_count']:,} codepoints; {coverage['sample_count']} sample strings.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=Path("/usr/share/fonts/truetype/noto"))
    parser.add_argument("--cjk-path", type=Path, default=Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"))
    parser.add_argument("--core-license", type=Path, default=Path("/usr/share/doc/fonts-noto-core/copyright"))
    parser.add_argument("--cjk-license", type=Path, default=Path("/usr/share/doc/fonts-noto-cjk/copyright"))
    parser.add_argument("--output", type=Path, default=PACKAGE)
    parser.add_argument("--check", action="store_true", help="Verify shipped artifacts without reading the source font directories")
    args = parser.parse_args()
    try:
        check(args.output) if args.check else bundle(args)
    except (OSError, ValueError, KeyError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

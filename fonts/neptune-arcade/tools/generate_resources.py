#!/usr/bin/env python3
"""Generate portable Godot font resources and reproducible import settings.

Copy the package to res://fonts/neptune-arcade, then import it in Godot. The
resource files themselves use relative paths; pass --resource-prefix when
relocating the folder so its generated .import source paths match the project.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


REGIONS = {
    "ja": (0, "JP"),
    "ko": (1, "KR"),
    "zh_Hans": (2, "SC"),
    "zh_Hant": (3, "TC"),
    "zh_HK": (4, "HK"),
}


def resource_uid(source: str) -> str:
    """Godot's positive 63-bit ResourceUID encoded with its base-34 alphabet."""
    value = int.from_bytes(hashlib.sha256(source.encode("utf-8")).digest()[:8], "big") & ((1 << 63) - 1)
    alphabet = "abcdefghijklmnopqrstuvwxy012345678"
    digits = ""
    while value:
        value, digit = divmod(value, len(alphabet))
        digits = alphabet[digit] + digits
    return "uid://" + (digits or "a")


def import_settings(relative: str, prefix: str, *, pixel: bool) -> str:
    source = prefix.rstrip("/") + "/" + relative
    digest = hashlib.md5(source.encode("utf-8")).hexdigest()
    imported = f"res://.godot/imported/{Path(relative).name}-{digest}.fontdata"
    return f'''[remap]

importer="font_data_dynamic"
type="FontFile"
uid="{resource_uid(source)}"
path="{imported}"

[deps]

source_file="{source}"
dest_files=["{imported}"]

[params]

Rendering=null
antialiasing={0 if pixel else 1}
generate_mipmaps=false
disable_embedded_bitmaps=true
multichannel_signed_distance_field=false
msdf_pixel_range=8
msdf_size=48
allow_system_fallback=false
force_autohinter=false
modulate_color_glyphs=false
hinting={0 if pixel else 1}
subpixel_positioning=0
keep_rounding_remainders=true
oversampling=1.0
Fallbacks=null
fallbacks=[]
Compress=null
compress=true
preload=[]
language_support={{}}
script_support={{}}
opentype_features={{}}
'''


def generated_files(package: Path, prefix: str) -> dict[str, str]:
    primary = "dist/NeptuneBubble.ttf"
    pixel = "dist/NeptuneArcade.ttf"
    cjk = "fallbacks/NotoSansCJK-Bold.ttc"
    common = "fallbacks/NotoSans-Regular.ttf"
    if not all((package / path).is_file() for path in (primary, pixel, cjk, common)):
        raise ValueError("Build the bubble and optional pixel fonts, then bundle Noto fallbacks first")
    scripts = sorted(path.relative_to(package).as_posix()
                     for path in (package / "fallbacks").glob("*.ttf")
                     if path.name != "NotoSans-Regular.ttf")
    if not scripts:
        raise ValueError("No bundled script fallbacks found")
    fonts = [primary, pixel, common, cjk, *scripts]
    result = {path + ".import": import_settings(path, prefix, pixel=path == pixel)
              for path in fonts}

    resources = [common, *scripts]
    lines = [f'[gd_resource type="FontVariation" load_steps={len(resources) + 1} format=3]', ""]
    for i, path in enumerate(resources):
        lines.append(f'[ext_resource type="FontFile" path="{path}" id="font_{i}"]')
    lines.extend(["", "[resource]", 'resource_name = "Neptune Unicode Fallbacks"',
                  'base_font = ExtResource("font_0")',
                  "fallbacks = Array[Font]([" + ", ".join(
                      f'ExtResource("font_{i}")' for i in range(1, len(resources))) + "])", ""])
    result["common_fallbacks.tres"] = "\n".join(lines)

    for locale, (face_index, region) in REGIONS.items():
        result[f"cjk_{locale}.tres"] = f'''[gd_resource type="FontVariation" load_steps=2 format=3]

[ext_resource type="FontFile" path="{cjk}" id="cjk"]

[resource]
resource_name = "CJK_{region}"
base_font = ExtResource("cjk")
variation_face_index = {face_index}
'''
        root = f'''[gd_resource type="FontVariation" load_steps=4 format=3]

[ext_resource type="FontFile" path="{primary}" id="arcade"]
[ext_resource type="FontVariation" path="common_fallbacks.tres" id="common"]
[ext_resource type="FontVariation" path="cjk_{locale}.tres" id="cjk"]

[resource]
resource_name = "Neptune Bubble {region}"
base_font = ExtResource("arcade")
fallbacks = Array[Font]([ExtResource("common"), ExtResource("cjk")])
'''
        result[f"neptune_arcade_{locale}.tres"] = root
        if locale == "ja":
            result["neptune_arcade.tres"] = root
    result["neptune_pixel.tres"] = f'''[gd_resource type="FontVariation" load_steps=4 format=3]

[ext_resource type="FontFile" path="{pixel}" id="pixel"]
[ext_resource type="FontVariation" path="common_fallbacks.tres" id="common"]
[ext_resource type="FontVariation" path="cjk_ja.tres" id="cjk"]

[resource]
resource_name = "Neptune Pixel HUD"
base_font = ExtResource("pixel")
fallbacks = Array[Font]([ExtResource("common"), ExtResource("cjk")])
'''
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    package_candidate = Path(__file__).resolve().parents[1]
    default_package = (package_candidate if (package_candidate / "dist").is_dir()
                       else Path(__file__).resolve().parents[2] / "fonts/neptune-arcade")
    parser.add_argument("--package", type=Path,
                        default=default_package)
    parser.add_argument("--resource-prefix", default="res://fonts/neptune-arcade")
    parser.add_argument("--check", action="store_true", help="Fail if generated files differ")
    args = parser.parse_args()
    try:
        if not args.resource_prefix.startswith("res://"):
            raise ValueError("--resource-prefix must begin with res://")
        files = generated_files(args.package, args.resource_prefix)
        changed = []
        for relative, content in files.items():
            target = args.package / relative
            if not target.is_file() or target.read_text(encoding="utf-8") != content:
                changed.append(relative)
                if not args.check:
                    target.write_text(content, encoding="utf-8")
        if args.check and changed:
            print("FAIL: stale/missing generated resources: " + ", ".join(changed))
            return 1
        print(f"PASS: {len(files)} Godot resources/import settings "
              f"{'verified' if args.check else 'generated'}")
        return 0
    except (OSError, ValueError) as error:
        print(f"FAIL: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

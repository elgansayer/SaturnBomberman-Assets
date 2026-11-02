#!/usr/bin/env python3
"""Independently check published FILM PCM and packet maps against local sources.

This stdlib validator does not import the Neptune extractor or rerun FFmpeg.
Recorded frame hashes/repeatability remain declarations from that experiment.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import tempfile
import wave

ROOT = Path(__file__).resolve().parents[1]
SOURCE_REVISION = "445114300594db707c1085d8b6b33d50218cd582"
PUBLIC = {"audio.wav", "report.json", "sample-table.json", "video-run1.framehash"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path, limit):
    require(not any(p.is_symlink() for p in (path, *path.parents)), "Symlink paths unsupported")
    require(path.is_file() and path.stat().st_size <= limit, "Missing or over-budget artifact")
    with path.open("rb") as stream:
        result = stream.read(limit + 1)
    require(len(result) <= limit, "Artifact exceeded read budget")
    return result


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "Duplicate JSON key")
        result[key] = value
    return result


def document(path):
    return json.loads(read(path, 4 * 1024**2), object_pairs_hook=unique)


def fraction(value):
    return {"numerator": value.numerator, "denominator": value.denominator}


def source_model(data):
    """Derive fields directly; no extractor implementation is imported."""
    require(len(data) >= 80 and data[:4] == b"FILM" and data[8:16] == b"1.04\0\0\0\0", "Unsupported FILM header")
    header = struct.unpack_from(">I", data, 4)[0]
    require(data[16:24] == b"FDSC\0\0\0\x20" and data[24:28] == b"cvid", "Unsupported FDSC")
    height, width = struct.unpack_from(">II", data, 28)
    bpp, channels, bits, compression = data[36:40]
    rate = struct.unpack_from(">H", data, 40)[0]
    require((bpp, channels, bits, compression, rate) == (24, 2, 8, 0, 22050), "Unsupported measured audio/video subset")
    require(0 < width <= 4096 and 0 < height <= 4096 and data[42:48] == bytes(6), "Invalid dimensions/reserved fields")
    require(data[48:52] == b"STAB", "Missing STAB")
    table_size, clock, count = struct.unpack_from(">III", data, 52)
    require(0 < count <= 100000 and clock == 600 and table_size == 16 + count * 16
            and header == 48 + table_size <= len(data), "Invalid sample table bounds")
    table, pcm, video = [], bytearray(), []
    expected_offset = header
    audio_frames = 0
    for index in range(count):
        relative, length, info, duration = struct.unpack_from(">4I", data, 64 + index * 16)
        offset = header + relative
        require(offset == expected_offset and 0 < length <= 8 * 1024**2 and offset + length <= len(data), "Invalid packet extent")
        expected_offset += length
        packet = data[offset:offset + length]
        row = {"index": index, "source_offset": offset, "bytes": length, "sha256": sha(packet)}
        if info == 0xffffffff:
            require(length % 2 == 0 and duration == 1, "Invalid PCM packet")
            row.update(kind="audio", start_sample_frame=audio_frames, sample_frames=length // 2)
            audio_frames += length // 2
            # Each packet contains its own complete L plane, then R plane.
            half = length // 2
            pcm.extend(v for pair in zip(packet[:half], packet[half:]) for v in pair)
        else:
            pts = info & 0x7fffffff
            require(duration == 24 and pts == len(video) * 24, "Video PTS/duration mismatch")
            require(video or not info & 0x80000000, "First video packet must be keyframe")
            row.update(kind="video", pts_ticks=pts, duration_ticks=duration, keyframe=not bool(info & 0x80000000))
            video.append((pts, duration))
        table.append(row)
    require(expected_offset == len(data) and video and audio_frames, "Incomplete source accounting")
    end = video[-1][0] + video[-1][1]
    return {"header": header, "width": width, "height": height, "rate": rate,
            "table": table, "pcm": bytes(pcm), "audio_frames": audio_frames,
            "video_frames": len(video), "video_end": end,
            "video_duration": Fraction(end, clock)}


def validate(directory, root=ROOT):
    publication = document(directory / "publication.json")
    require(publication["schema"] == "neptune.private-film-publication.v1", "Unsupported publication schema")
    source = publication["source"]
    require(source["repository"] == "elgansayer/SaturnBomberman-Assets"
            and source["revision"] == SOURCE_REVISION
            and source["lineage"] == "prior-assets-unresolved-release", "Invalid source declaration")
    require(re.fullmatch(r"audio/rips/BOMSS[1-3]\.CPK", source["path"]), "Source path outside supported selection")
    data = read(root / source["path"], 256 * 1024**2)
    require(len(data) == source["bytes"] and sha(data) == source["sha256"], "Source size/hash mismatch")
    require(set(publication["published"]) == PUBLIC, "Unexpected publication selection")
    files = {}
    for name in sorted(PUBLIC):
        raw = read(directory / name, 16 * 1024**2)
        declared = publication["published"][name]
        require(len(raw) == declared["bytes"] and sha(raw) == declared["sha256"], "Published artifact size/hash mismatch: " + name)
        files[name] = raw
    model = source_model(data)
    table = document(directory / "sample-table.json")
    # JSON spelling distinguishes booleans/floats from source-derived integers.
    require(json.dumps(table, sort_keys=True) == json.dumps(model["table"], sort_keys=True),
            "Source packet table mismatch")
    report = document(directory / "report.json")
    require(report["schema"] == "neptune.saturn-film-recovery.v1" and report["source"] == {
        "bytes": len(data), "sha256": sha(data), "lineage": "prior-assets-unresolved-release",
        "release_identity": "unresolved", "pinned_usa_or_japan_original": False}, "Extraction source identity mismatch")
    accounting = report["accounting"]
    require(accounting == {"header_bytes": model["header"], "packet_bytes": len(data) - model["header"],
        "packets": len(table), "unaccounted_bytes": 0,
        "packet_table_sha256": sha(files["sample-table.json"])}, "Source accounting mismatch")
    with wave.open(str(directory / "audio.wav"), "rb") as stream:
        require((stream.getnchannels(), stream.getsampwidth(), stream.getframerate(), stream.getnframes())
                == (2, 1, model["rate"], model["audio_frames"]), "WAV format/count mismatch")
        signed = bytes(value ^ 128 for value in stream.readframes(stream.getnframes()))
    require(signed == model["pcm"], "WAV samples differ from source planes")
    audio = report["audio"]
    require(audio["pcm_s8_sha256"] == sha(signed) and audio["pcm_bytes"] == len(signed)
            and audio["sample_frames"] == model["audio_frames"] and audio["channels"] == 2
            and audio["sample_rate_hz"] == model["rate"]
            and audio["source_format"] == "signed-8-planar-per-packet"
            and audio["recovered_format"] == "signed-8-interleaved"
            and audio["packets"] == sum(row["kind"] == "audio" for row in table)
            and audio["duration_seconds"] == fraction(Fraction(model["audio_frames"], model["rate"])), "Audio report mismatch")
    video = report["video"]
    require((video["width"], video["height"], video["frames"], video["clock_hz"], video["start_pts_ticks"], video["end_pts_ticks"])
            == (model["width"], model["height"], model["video_frames"], 600, 0, model["video_end"]), "Video report mismatch")
    require(video["duration_seconds"] == fraction(model["video_duration"])
            and video["average_frames_per_second"] == fraction(Fraction(25))
            and video["codec"] == "cvid" and video["bits_per_pixel"] == 24
            and video["compressed_packets_decoded_to_pixels"] is False
            and video["duration_ticks_histogram"] == {"24": model["video_frames"]}, "Video timing report mismatch")
    require(report["audio_minus_video_seconds"] == fraction(Fraction(model["audio_frames"], model["rate"]) - model["video_duration"]), "Audio/video duration delta mismatch")
    for name in ("audio.wav", "sample-table.json"):
        require(report["artifacts"][name]["sha256"] == sha(files[name]), "Extraction artifact digest mismatch")
    require(report["artifacts"]["audio.s8"] == {"bytes": len(signed), "sha256": sha(signed)}, "Private PCM declaration mismatch")
    recorded = publication["recorded_external_validation"]
    require(recorded["video_framehash_sha256"] == sha(files["video-run1.framehash"])
            and recorded["video_decoded_frames"] == model["video_frames"], "Recorded framehash/count mismatch")
    lines = files["video-run1.framehash"].decode("ascii").splitlines()
    require("#tb 0: 1/25" in lines and f"#dimensions 0: {model['width']}x{model['height']}" in lines, "Framehash header mismatch")
    rows = [line for line in lines if line and not line.startswith("#")]
    require(len(rows) == model["video_frames"], "Missing or excess framehash rows")
    for index, line in enumerate(rows):
        fields = [part.strip() for part in line.split(",")]
        require(len(fields) == 6 and tuple(map(int, fields[:5])) == (0, index, index, 1, model["width"] * model["height"] * 3)
                and re.fullmatch(r"[0-9a-f]{64}", fields[5]), "Malformed framehash row")
    require(recorded["first_frame"] == rows[0] and recorded["last_frame"] == rows[-1], "Recorded frame endpoints differ")
    return {"source": source["path"], "source_sha256": source["sha256"],
            "video_frames": model["video_frames"], "audio_sample_frames": model["audio_frames"],
            "native_pcm_sha256": sha(signed), "framehash_scope": "recorded decoder output checked; FFmpeg not rerun"}


def controls(directory, root=ROOT):
    """Actual accepted outputs remain unchanged; two damaged copies must fail."""
    with tempfile.TemporaryDirectory(prefix="film-publication-control-") as temporary:
        scratch = Path(temporary)
        bad = scratch / "changed-audio"
        bad.mkdir()
        for name in PUBLIC | {"publication.json"}:
            shutil.copyfile(directory / name, bad / name)
        raw = bytearray((bad / "audio.wav").read_bytes())
        raw[-1] ^= 1
        (bad / "audio.wav").write_bytes(raw)
        # Update the outer declaration so source comparison must detect this.
        manifest = document(bad / "publication.json")
        manifest["published"]["audio.wav"]["sha256"] = sha(raw)
        (bad / "publication.json").write_text(json.dumps(manifest))
        try:
            validate(bad, root)
        except ValueError as error:
            require(str(error) == "WAV samples differ from source planes", "Wrong audio rejection boundary")
        else:
            raise ValueError("Changed WAV sample was accepted")
        (bad / "publication.json").unlink()
        try:
            validate(bad, root)
        except ValueError:
            pass
        else:
            raise ValueError("Missing publication manifest was accepted")
    return {"changed_wav_sample_rejected": True, "missing_manifest_rejected": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--negative-controls", action="store_true")
    args = parser.parse_args()
    try:
        directories = sorted((args.root / "saturn/unresolved-release/film").glob("BOMSS*-*/publication.json"))
        require(len(directories) == 3, "Require the complete three-container publication")
        for manifest in directories:
            result = validate(manifest.parent, args.root)
            if args.negative_controls:
                result["negative_controls"] = controls(manifest.parent, args.root)
            print(json.dumps(result, sort_keys=True))
    except (ValueError, KeyError, TypeError, OSError, wave.Error, struct.error) as error:
        raise SystemExit("FILM publication validation failed: " + type(error).__name__) from None


if __name__ == "__main__":
    main()

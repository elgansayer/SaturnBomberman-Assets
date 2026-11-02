# Lossless PCM recovered from existing Saturn FILM containers

Research date: 2 November 2026. This private publication contains the complete
audio from the three existing `audio/rips/BOMSS*.CPK` files, their packet maps,
extraction reports and complete decoded-video frame hashes. It advances Neptune
[RSAT-012 / #489](https://github.com/elgansayer/Neptune-Bomberman/issues/489).
It does not complete the game's audio or movie reconstruction.

The source files already existed at assets revision
[`445114300594db707c1085d8b6b33d50218cd582`](https://github.com/elgansayer/SaturnBomberman-Assets/tree/445114300594db707c1085d8b6b33d50218cd582/audio/rips).
Their hashes differ from the separately supplied USA/Japan disc inventory. Their
release identity remains unresolved. All three have measured 25-fps video;
that alone does not establish PAL provenance. Preserve this namespace separately
from `usa-mk81070-v1003` and `japan-t14302g-v1000`.

| Container and publication | Video frames | Video duration | Stereo sample frames |
| --- | ---: | ---: | ---: |
| [BOMSS1](BOMSS1-c070db915f55/publication.json) | 2,504 | 100.16 s | 2,208,528 |
| [BOMSS2](BOMSS2-10f6edcdb395/publication.json) | 2,845 | 113.8 s | 2,509,292 |
| [BOMSS3](BOMSS3-d5325c7a0056/publication.json) | 3,319 | 132.76 s | 2,927,360 |

All sources are Sega `FILM` 1.04 with 320×160 Cinepak video and 22,050-Hz stereo
signed 8-bit PCM. The audio packets store a complete left plane followed by a
right plane **within each packet**. The extractor interleaves those planes
without resampling or changing samples. RIFF/WAV stores 8-bit PCM unsigned, so
each sample is XORed with `0x80`; the conversion is exactly reversible.
The three WAVs represent 15,290,360 native PCM bytes in total.

The STAB clock is 600 Hz, and every video packet lasts 24 ticks. BOMSS1 audio and
video end together. BOMSS2 and BOMSS3 each have two additional stereo sample
frames: an exact audio-minus-video duration of `1/11025` second. No samples were
trimmed to hide that source-container difference. Game playback synchronization
and trigger semantics were not observed by this experiment.

## Published artifacts and retained evidence

Each directory contains:

- `audio.wav`: complete, reversible unsigned-8 stereo PCM.
- `sample-table.json`: every source packet's index, absolute file span and hash;
  video PTS/duration/keyframe fields or cumulative audio sample-frame boundaries.
- `report.json`: original extraction report, including native PCM identity,
  exact rational durations, source identity and explicit limits.
- `video-run1.framehash`: one full FFmpeg RGB24 decode's frame hashes and times.
- `publication.json`: selected-file hashes, pinned source path/revision,
  executable/source identities and the recorded external-validation results.

The extraction report also names `audio.s8`. That redundant signed-8 stream and
the second video decode log remain private experiment artifacts. The WAV
represents exactly the same native samples, and publication intentionally selects
one frame-hash log. These omissions do not mean extraction terminated early.
Original CPK files stay in their existing location; no discs, BIOS, save states,
RAM/VRAM dumps or newly invented binary fixtures are added by this publication.

The extractor and detailed evidence are submitted in [Neptune PR #584](https://github.com/elgansayer/Neptune-Bomberman/pull/584),
commit `8e4b778e90bd2d2ac55d51e2a891571ea25e1bf3`. The retained Neptune experiment receipt is
[`docs/restart/evidence/2026-11-02-film-recovery.json`](https://github.com/elgansayer/Neptune-Bomberman/blob/8e4b778e90bd2d2ac55d51e2a891571ea25e1bf3/docs/restart/evidence/2026-11-02-film-recovery.json), SHA-256
`04ef09f4e8462753788f07ee1b38442c36d279a0589e2f3cb84fc2a01a619546`.
It records full PCM equality against FFmpeg, an exact WAV round trip, two
byte-identical complete video frame-hash runs (8,668 frames), packet timing and
keyframe comparisons against ffprobe, unchanged inputs, and negative controls.
This is a recorded local source-container experiment, not an authenticated
original-disc or emulator capture. Both video runs use the same FFmpeg decoder;
their agreement proves repeatability within that implementation.

FFmpeg 7.1.5's ffprobe reports misleading video stream durations equal to
`frame_count / 600` (4.173333, 4.741667 and 5.531667 seconds). Its packet PTS and
durations agree with STAB. Use the native packet clock and audio sample counts;
do not use the stream-duration field as the timing oracle.

## Independent publication validation

From this assets checkout:

```sh
python3 tools/validate_film_recovery.py --negative-controls
```

This separate stdlib implementation imports no Neptune decoder. It checks the
actual local CPK hashes, independently reads every packet and timestamp,
reconstructs the stereo PCM with a separate interleaver, compares all samples to
the WAV, checks packet maps and report fields, and verifies published frame-hash
identity/count/structure. Temporary changed-WAV and missing-manifest controls
must fail; accepted artifacts remain unchanged. It requires exactly the three
published containers and fails on missing or inconsistent files.

The publication validator **does not rerun FFmpeg**. It verifies the supplied
recorded frame-hash artifact; a hash does not authenticate the original capture
or prove independently correct video pixels.

## Regeneration

Use the Neptune `tools/saturn_film/` source identities and installed FFmpeg/ffprobe
identities in `publication.json`. The committed validator is
`tools/saturn_film/validate_real.py`; the source-container experiment receipt
retains exact sanitized commands. Resolve `NEPTUNE`, `ASSETS` and `PRIVATE`
to the actual checkouts and private output parent on the host, then choose a
fresh output directory:

```sh
python3 "$NEPTUNE/tools/saturn_film/validate_real.py" \
  --input "$ASSETS/audio/rips/BOMSS1.CPK" \
  --input "$ASSETS/audio/rips/BOMSS2.CPK" \
  --input "$ASSETS/audio/rips/BOMSS3.CPK" \
  --output "$PRIVATE/new-film-validation" --timeout-seconds 120
```

For one extraction without external video decoding:

```sh
python3 "$NEPTUNE/tools/saturn_film/cli.py" extract \
  --input "$ASSETS/audio/rips/BOMSS1.CPK" \
  --output "$PRIVATE/new-bomss1-extraction"
```

Keep the original inputs unchanged. Reproduce into new directories and compare
native PCM and source timing before accepting a different tool version. SCSP
samples/sequences, CD-DA track mapping, source-disc region identification, runtime
movie selection and exact Godot playback remain separate open work.

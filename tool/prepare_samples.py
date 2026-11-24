#!/usr/bin/env python3
"""Prepare the file format samples listed in formats/manifest.json.

Generated samples are encoded locally with ffmpeg from SMPTE bars and a 1 kHz
tone (both deterministic, so they carry no licensing questions); downloaded
samples must match their sha256; playlist samples are text files pointing at
another prepared sample. Every result is checked with ffprobe (the real
container/codecs, not the extension) and written to a resolved list that the
integration test (example/integration_test/formats_test.dart) reads.

Usage: prepare_samples.py --cache DIR --out FILE [--only ID[,ID...]]
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import pathlib
import shutil
import subprocess
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "formats" / "manifest.json"
SECONDS = 6
FPS = 25
TONE_HZ = 1000
DEFAULT_SIZE = "320x240"
# Reference frames and snapshots are compared on this grid (box-averaged).
GRID = (32, 24)
MAX_DOWNLOAD = 200 * 1024 * 1024


def run(cmd: list[str]) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"{cmd[0]} failed: {p.stderr.strip()[-600:]}")
    return p.stdout


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def generate(sample: dict, dest: pathlib.Path) -> None:
    size = sample.get("size", DEFAULT_SIZE)
    args = sample["generate"]
    inputs: list[str] = []
    maps: list[str] = []
    if not sample.get("audio_only"):
        inputs += ["-f", "lavfi", "-i", f"smptebars=size={size}:rate={FPS}:duration={SECONDS}"]
        maps += ["-map", f"{len(maps) // 2}:v"]
    if not sample.get("video_only"):
        inputs += ["-f", "lavfi", "-i", f"sine=frequency={TONE_HZ}:sample_rate=48000:duration={SECONDS}"]
        maps += ["-map", f"{len(maps) // 2}:a"]
        if "-ac" not in args:
            args = ["-ac", "2", *args]
    spec = json.dumps([inputs, maps, args])
    stamp = dest.with_name(dest.name + ".spec")
    if dest.exists() and stamp.exists() and stamp.read_text() == spec:
        return
    # Keep the extension last: ffmpeg picks the muxer from it.
    tmp = dest.with_name(f"{dest.stem}.part{dest.suffix}")
    tmp.unlink(missing_ok=True)
    run(["ffmpeg", "-nostdin", "-v", "error", "-y", *inputs, *maps, "-t", str(SECONDS), *args, str(tmp)])
    tmp.replace(dest)
    stamp.write_text(spec)


def download(sample: dict, dest: pathlib.Path) -> None:
    if dest.exists() and sha256(dest) == sample["sha256"]:
        return
    tmp = dest.with_name(dest.name + ".part")
    last: Exception | None = None
    for _ in range(3):
        try:
            with urllib.request.urlopen(sample["url"], timeout=60) as r, tmp.open("wb") as f:
                total = 0
                while chunk := r.read(1 << 20):
                    total += len(chunk)
                    if total > MAX_DOWNLOAD:
                        raise RuntimeError("download exceeds size limit")
                    f.write(chunk)
            break
        except Exception as e:  # retried below
            last = e
    else:
        raise RuntimeError(f"download failed: {last}")
    got = sha256(tmp)
    if got != sample["sha256"]:
        tmp.unlink()
        raise RuntimeError(f"sha256 mismatch: {got}")
    tmp.replace(dest)


def playlist(sample: dict, target: pathlib.Path, dest: pathlib.Path) -> None:
    uri = target.as_uri()
    text = {
        "pls": f"[playlist]\nFile1={uri}\nTitle1={target.stem}\nLength1=-1\nNumberOfEntries=1\nVersion=2\n",
        "m3u": f"#EXTM3U\n#EXTINF:-1,{target.stem}\n{target}\n",
        "asx": f'<asx version="3.0">\n  <entry>\n    <title>{target.stem}</title>\n    <ref href="{uri}"/>\n  </entry>\n</asx>\n',
        "cue": f'FILE "{target.name}" WAVE\n  TRACK 01 AUDIO\n    TITLE "{target.stem}"\n    INDEX 01 00:00:00\n',
    }[sample["ext"]]
    dest.write_text(text)


def probe(path: pathlib.Path) -> dict:
    data = json.loads(run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)]))
    video = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    audio = next((s for s in data["streams"] if s["codec_type"] == "audio"), None)
    duration = float(data["format"].get("duration") or (video or audio or {}).get("duration") or 0)
    return {
        "container": data["format"]["format_name"],
        "duration_ms": round(duration * 1000),
        "video_codec": video and video["codec_name"],
        "pix_fmt": video and video.get("pix_fmt"),
        "width": video and video["width"],
        "height": video and video["height"],
        "audio_codec": audio and audio["codec_name"],
        "channels": audio and audio.get("channels"),
        "sample_rate": audio and int(audio.get("sample_rate", 0)),
    }


def reference(size: str, refs: pathlib.Path) -> pathlib.Path:
    path = refs / f"smptebars-{size}-{GRID[0]}x{GRID[1]}.rgb"
    if not path.exists():
        run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", f"smptebars=size={size}:rate={FPS}",
             "-frames:v", "1", "-vf", f"scale={GRID[0]}:{GRID[1]}:flags=area", "-pix_fmt", "rgb24",
             "-f", "rawvideo", str(path)])
    return path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True, type=pathlib.Path)
    ap.add_argument("--out", required=True, type=pathlib.Path)
    ap.add_argument("--only", default="", help="comma-separated ids or glob patterns")
    a = ap.parse_args()
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            print(f"{tool} is required (brew install ffmpeg)", file=sys.stderr)
            return 2
    samples = json.loads(MANIFEST.read_text())["samples"]
    by_id = {s["id"]: s for s in samples}
    patterns = [p for p in a.only.split(",") if p]
    wanted = [s for s in samples if not patterns or any(fnmatch.fnmatch(s["id"], p) for p in patterns)]
    if not wanted:
        print(f"no sample matches {a.only!r}", file=sys.stderr)
        return 2
    media = a.cache / "media"
    refs = a.cache / "refs"
    media.mkdir(parents=True, exist_ok=True)
    refs.mkdir(parents=True, exist_ok=True)

    def prepare(s: dict) -> tuple[pathlib.Path, dict]:
        dest = media / f"{s['id']}.{s['ext']}"
        if "playlist" in s:
            target, info = prepare(by_id[s["playlist"]])
            playlist(s, target, dest)
            return dest, info
        if "generate" in s:
            generate(s, dest)
        else:
            download(s, dest)
        return dest, probe(dest)

    resolved = []
    for s in wanted:
        entry = {"id": s["id"], "ext": s["ext"], "linear": s.get("linear", []), "note": s.get("note")}
        try:
            path, info = prepare(s)
            target = by_id[s["playlist"]] if "playlist" in s else s
            expect = {
                "video": bool(info["video_codec"]),
                "audio": bool(info["audio_codec"]),
                "seek": True,
                "frame": None,
                "tone_hz": TONE_HZ if "generate" in target and info["audio_codec"] else None,
                # Generated samples have a known length; ffprobe only estimates
                # raw elementary streams.
                "duration_ms": SECONDS * 1000 if "generate" in target else info["duration_ms"] or None,
            }
            if "generate" in target and info["video_codec"]:
                expect["frame"] = str(reference(target.get("size", DEFAULT_SIZE), refs))
            expect.update(s.get("expect", {}))
            entry.update(status="ok", path=str(path), sha256=sha256(path), bytes=path.stat().st_size,
                         probe=info, expect=expect, grid=list(GRID))
        except Exception as e:
            entry.update(status="error", error=str(e))
        print(f"{entry['status']:5} {s['id']}" + (f"  {entry.get('error', '')}" if entry["status"] != "ok" else ""))
        resolved.append(entry)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps({"samples": resolved}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())

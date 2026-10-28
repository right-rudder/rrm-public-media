#!/usr/bin/env python3
"""Shrink this repo's videos for the web without visible quality loss, and make a .webp poster
for each one. Never touches the originals: everything is written to a separate output folder
that mirrors this repo's layout. See docs/optimization-plan.md.

    # 1. See what would happen (fast: reads metadata only, encodes nothing)
    python3 scripts/optimize_videos.py

    # 2. Try one folder
    python3 scripts/optimize_videos.py --apply --only skymates

    # 3. Everything
    python3 scripts/optimize_videos.py --apply

Per video:
  * longer side above --max-side (4K) is scaled down to it (1920 = 1080p);
  * re-encoded as H.264 MP4 (crf 23, preset slow), audio copied untouched;
  * the result is kept only if it is at least --min-saving % smaller AND its SSIM against the
    original is at least --min-ssim (0.98 = no visible difference). Otherwise the original is
    kept — remuxed losslessly with fast start if it was missing it, copied as-is if not;
  * .mov files come out as .mp4 (same streams);
  * a .webp poster from about 1 s in, at the output's size.

Writes <out>/report.csv with what happened to every file. Re-running skips files whose output
is already newer than the source, so an interrupted run can just be started again.

Needs only ffmpeg/ffprobe (with libx264 and libwebp) and Python 3.8+.
"""

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

REPO = Path(__file__).resolve().parent.parent
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v"}
REPORT_FIELDS = ["path", "output", "action", "before_mb", "after_mb", "saving_pct", "ssim",
                 "width", "height", "notes"]


@dataclass
class Video:
    path: Path              # relative to the source folder
    size: int
    width: int
    height: int
    duration: float
    has_audio: bool
    faststart: bool

    @property
    def long_side(self) -> int:
        return max(self.width, self.height)


@dataclass
class Outcome:
    video: Video
    output: Optional[Path] = None
    action: str = ""
    after: int = 0
    ssim: Optional[float] = None
    notes: List[str] = field(default_factory=list)

    def row(self) -> dict:
        before = self.video.size
        return {
            "path": str(self.video.path),
            "output": str(self.output or ""),
            "action": self.action,
            "before_mb": f"{before / 1e6:.1f}",
            "after_mb": f"{self.after / 1e6:.1f}" if self.after else "",
            "saving_pct": f"{100 - 100 * self.after / before:.0f}" if self.after and before else "",
            "ssim": f"{self.ssim:.4f}" if self.ssim is not None else "",
            "width": self.video.width,
            "height": self.video.height,
            "notes": "; ".join(self.notes),
        }


# --- reading -------------------------------------------------------------------------------

def find_videos(source: Path, only: Optional[str]) -> List[Path]:
    root = source / only if only else source
    if not root.is_dir():
        sys.exit(f"--only {only!r}: no folder {root} (expected a top-level school folder, e.g. skymates)")
    found = [p for p in root.rglob("*") if p.suffix.lower() in VIDEO_EXTENSIONS and ".git" not in p.parts]
    return sorted(p.relative_to(source) for p in found)


def probe(source: Path, relative: Path) -> Video:
    path = source / relative
    result = run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)])
    info = json.loads(result.stdout)
    streams = info.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video is None:
        raise ValueError(f"{relative}: ffprobe found no video stream (streams: {[s.get('codec_type') for s in streams]})")
    return Video(path=relative, size=path.stat().st_size, width=int(video["width"]), height=int(video["height"]),
                 duration=float(info.get("format", {}).get("duration") or 0),
                 has_audio=any(s.get("codec_type") == "audio" for s in streams),
                 faststart=moov_before_mdat(path))


def moov_before_mdat(path: Path) -> bool:
    """True when the index (moov) comes before the media (mdat), so browsers can start playing
    before the whole file has downloaded. Reads only the top-level box headers."""
    with path.open("rb") as handle:
        while True:
            header = handle.read(8)
            if len(header) < 8:
                return False
            size, kind = int.from_bytes(header[:4], "big"), header[4:]
            if kind in (b"moov", b"mdat"):
                return kind == b"moov"
            if size == 1:
                size = int.from_bytes(handle.read(8), "big") - 8
            elif size == 0:
                return False
            handle.seek(size - 8, os.SEEK_CUR)


# --- planning (dry run) ----------------------------------------------------------------------

def plan(video: Video, args: argparse.Namespace) -> List[str]:
    steps = ["re-encode H.264 crf %d" % args.crf]
    if video.long_side > args.max_side:
        steps.insert(0, f"scale {video.width}x{video.height} -> long side {args.max_side}")
    if not video.faststart:
        steps.append("add fast start")
    if video.path.suffix.lower() != ".mp4":
        steps.append("container -> .mp4")
    if not args.no_posters:
        steps.append("webp poster")
    return steps


# --- encoding --------------------------------------------------------------------------------

def scale_filter(max_side: int) -> str:
    # Only ever shrinks; -2 keeps the aspect ratio with an even dimension, as H.264 needs.
    return (f"scale='if(gt(iw,ih),min({max_side},iw),-2)':'if(gt(iw,ih),-2,min({max_side},ih))'")


def encode(source: Path, video: Video, target: Path, args: argparse.Namespace) -> None:
    command = ["ffmpeg", "-v", "error", "-y", "-i", str(source / video.path), "-map", "0:v:0", "-map", "0:a?",
               "-vf", scale_filter(args.max_side), "-c:v", "libx264", "-preset", args.preset, "-crf", str(args.crf),
               "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", "-threads", str(args.threads),
               str(target)]
    run(command)


def remux_faststart(source: Path, video: Video, target: Path) -> None:
    run(["ffmpeg", "-v", "error", "-y", "-i", str(source / video.path), "-map", "0", "-c", "copy",
         "-movflags", "+faststart", str(target)])


def ssim(original: Path, candidate: Path) -> float:
    """Structural similarity of the candidate to the original, compared at the candidate's size
    (1.0 = identical; above ~0.98 the difference is not visible)."""
    width, height = dimensions(candidate)
    result = run(["ffmpeg", "-nostats", "-i", str(candidate), "-i", str(original), "-lavfi",
                  f"[1:v]scale={width}:{height}:flags=bicubic[ref];[0:v][ref]ssim", "-f", "null", "-"])
    for line in reversed(result.stderr.splitlines()):
        if "All:" in line:
            return float(line.split("All:")[1].split()[0])
    raise RuntimeError(f"no SSIM in ffmpeg output for {candidate} (last lines: {result.stderr.splitlines()[-3:]})")


def dimensions(path: Path):
    out = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
               "-of", "csv=p=0", str(path)]).stdout.strip()
    width, height = out.split(",")[:2]
    return int(width), int(height)


def poster(video_path: Path, target: Path, duration: float) -> None:
    at = min(1.0, duration / 2) if duration else 0
    run(["ffmpeg", "-v", "error", "-y", "-ss", f"{at:.2f}", "-i", str(video_path), "-frames:v", "1",
         "-c:v", "libwebp", "-quality", "80", str(target)])


def output_path(out: Path, video: Video) -> Path:
    return (out / video.path).with_suffix(".mp4")


def up_to_date(target: Path, source_file: Path) -> bool:
    return target.exists() and target.stat().st_mtime >= source_file.stat().st_mtime


def optimize(source: Path, out: Path, video: Video, args: argparse.Namespace) -> Outcome:
    outcome = Outcome(video=video, output=output_path(out, video).relative_to(out))
    target = out / outcome.output
    if up_to_date(target, source / video.path):
        outcome.action, outcome.after = "skipped (already done)", target.stat().st_size
        return outcome

    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent) as scratch:
        candidate = Path(scratch) / target.name
        encode(source, video, candidate, args)
        decide(source, video, candidate, target, outcome, args)

    if not args.no_posters:
        poster(target, target.with_suffix(".webp"), video.duration)
    outcome.after = target.stat().st_size
    return outcome


def decide(source: Path, video: Video, candidate: Path, target: Path, outcome: Outcome,
           args: argparse.Namespace) -> None:
    saving = 100 - 100 * candidate.stat().st_size / video.size
    outcome.ssim = ssim(source / video.path, candidate)
    if saving >= args.min_saving and outcome.ssim >= args.min_ssim:
        shutil.move(str(candidate), target)
        outcome.action = "re-encoded" + (" + scaled" if video.long_side > args.max_side else "")
        return

    reason = f"re-encode saved {saving:.0f}%" if saving < args.min_saving else f"SSIM {outcome.ssim:.4f} below {args.min_ssim}"
    outcome.notes.append(f"kept original: {reason}")
    keep_original(source, video, target, outcome)


def keep_original(source: Path, video: Video, target: Path, outcome: Outcome) -> None:
    needs_remux = not video.faststart or video.path.suffix.lower() != ".mp4"
    if needs_remux:
        remux_faststart(source, video, target)
        outcome.action = "original, remuxed (lossless)"
    else:
        shutil.copy2(source / video.path, target)
        outcome.action = "original, copied"


# --- running ---------------------------------------------------------------------------------

def run(command: List[str]) -> subprocess.CompletedProcess:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"{command[0]} failed ({result.returncode}) on {command[-1]}: {result.stderr.strip()[-500:]}")
    return result


def safe_optimize(source: Path, out: Path, video: Video, args: argparse.Namespace) -> Outcome:
    try:
        outcome = optimize(source, out, video, args)
    except Exception as error:  # one bad file must not stop a 300-file run
        outcome = Outcome(video=video, action="FAILED", notes=[str(error)])
    print(f"{outcome.action:32} {video.path}", flush=True)
    return outcome


def dry_run(videos: List[Video], args: argparse.Namespace) -> None:
    for video in videos:
        print(f"{video.size / 1e6:7.1f} MB  {video.path}\n             {', '.join(plan(video, args))}")
    total = sum(v.size for v in videos)
    print(f"\n{len(videos)} videos, {total / 1e9:.2f} GB. "
          f"{sum(v.long_side > args.max_side for v in videos)} above {args.max_side}px, "
          f"{sum(not v.faststart for v in videos)} without fast start.")
    print("Nothing was written. Add --apply to encode (originals are never modified).")


def write_report(out: Path, outcomes: List[Outcome]) -> None:
    """Merges into <out>/report.csv by path, so runs with --only add up to one report."""
    report = out / "report.csv"
    rows = {}
    if report.exists():
        with report.open(newline="") as handle:
            rows = {row["path"]: row for row in csv.DictReader(handle)}
    # A file skipped as already done keeps the row from the run that actually did it.
    rows.update({str(o.video.path): o.row() for o in outcomes
                 if not (o.action.startswith("skipped") and str(o.video.path) in rows)})
    with report.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REPORT_FIELDS)
        writer.writeheader()
        writer.writerows(rows[path] for path in sorted(rows))
    print_summary(outcomes, report)


def print_summary(outcomes: List[Outcome], report: Path) -> None:
    before = sum(o.video.size for o in outcomes)
    after = sum(o.after for o in outcomes if o.after)
    failed = sum(o.action == "FAILED" for o in outcomes)
    print(f"\n{len(outcomes)} videos: {before / 1e6:,.1f} MB -> {after / 1e6:,.1f} MB "
          f"({100 - 100 * after / before if before else 0:.0f}% smaller). Report: {report}")
    if failed:
        print(f"{failed} FAILED — see the notes column in the report.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="encode for real (default: dry run, writes nothing)")
    parser.add_argument("--source", type=Path, default=REPO, help="folder to read (default: this repo)")
    parser.add_argument("--out", type=Path, default=REPO.parent / f"{REPO.name}-optimized",
                        help="where results go (default: a sibling folder, never inside the repo)")
    parser.add_argument("--only", help="one top-level folder, e.g. skymates")
    parser.add_argument("--max-side", type=int, default=1920, help="longest side in pixels (default 1920 = 1080p)")
    parser.add_argument("--crf", type=int, default=23, help="H.264 quality, lower = better and bigger (default 23)")
    parser.add_argument("--preset", default="slow", help="x264 preset (default slow)")
    parser.add_argument("--min-saving", type=float, default=10, help="keep the original unless at least this %% smaller (default 10)")
    parser.add_argument("--min-ssim", type=float, default=0.98, help="keep the original if SSIM falls below this (default 0.98)")
    parser.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) // 4), help="videos encoded at once")
    parser.add_argument("--threads", type=int, default=4, help="ffmpeg threads per video")
    parser.add_argument("--no-posters", action="store_true", help="skip the .webp poster images")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            sys.exit(f"{tool} not found on PATH — install it (sudo apt install ffmpeg) and try again")
    source, out = args.source.resolve(), args.out.resolve()
    if out == source or source in out.parents:
        sys.exit(f"--out {out} is inside the source {source}; pick a folder outside it so results are never committed by accident")

    videos = [probe(source, relative) for relative in find_videos(source, args.only)]
    if not args.apply:
        return dry_run(videos, args)

    out.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        outcomes = list(pool.map(lambda video: safe_optimize(source, out, video, args), videos))
    write_report(out, outcomes)


if __name__ == "__main__":
    main()

# Optimization plan: smaller videos, SEO names, one move to the CDN

Written 2026-10-28. What we found: [2026-10-28-media-audit.md](2026-10-28-media-audit.md). The
tool: [`scripts/optimize_videos.py`](../scripts/optimize_videos.py).

## The idea in one paragraph

Client websites embed these videos through jsDelivr URLs
(`cdn.jsdelivr.net/gh/…/rrm-public-media@…/<school>/<file>.mp4`). Any rename or re-encode in this
repo changes what those URLs serve, or breaks them. The media is moving to
`cdn.rightruddermarketing.com` (S3 + CloudFront, managed from the RRM portal's Media pages),
where every URL changes anyway. So we **compress and rename once, as part of that move**, and
update each website's links in the same pass. Until a school's site has moved over, **this repo
stays exactly as it is**.

## Goals

- **Smaller files, with no visible quality loss, staying MP4 (H.264).** It's video, not images, so
  WebP doesn't apply to the files themselves. WebM was considered and not chosen; see the end of
  this doc. Instead:
  - 4K → 1080p;
  - an efficient H.264 re-encode;
  - fast start, so playback begins before the file has fully downloaded.

  Each result is checked with SSIM against its original. Anything that isn't clearly smaller
  *and* visually identical keeps its original.
- **A `.webp` poster for every video**, for `<video poster="…">`, so pages show an image instead
  of a blank box while the video loads.
- **Descriptive, SEO-friendly names:** `<what-happens>-<aircraft/topic>-<school>-<city>.mp4`.
  The audit lists the bad names and suggests replacements.

## Steps

### 1. Dry run (minutes; writes nothing)

```bash
cd rrm-public-media
python3 scripts/optimize_videos.py
```

Lists every video and what would happen to it: scale, re-encode, fast start, `.mov` → `.mp4`,
poster.

### 2. Try one school, then look at the results

```bash
python3 scripts/optimize_videos.py --apply --only skymates
```

Results go to `../rrm-public-media-optimized/` (a **sibling** folder, never inside this repo, so
2 GB of output can't be committed by accident). Open a few videos next to their originals.
`report.csv` there says, per file:
- what was done;
- size before and after;
- SSIM: 1.0 is identical, and above 0.98 the difference can't be seen;
- why an original was kept, when it was.

### 3. Run everything

```bash
python3 scripts/optimize_videos.py --apply
```

This takes a while: re-encoding with `preset slow` runs at roughly real time per video on a
laptop. If it's interrupted, run the same command again; finished files are skipped. Useful knobs:

| Option | Default | Meaning |
|---|---|---|
| `--crf` | 23 | quality: lower is better and bigger (18–28 is the sensible range) |
| `--max-side` | 1920 | longest side in pixels (1920 = 1080p) |
| `--min-saving` | 10 | keep the original unless re-encoding saves at least this % |
| `--min-ssim` | 0.98 | keep the original if quality falls below this |
| `--no-posters` | off | skip the `.webp` posters |
| `--jobs` / `--threads` | CPU-based | how many videos at once / ffmpeg threads each |

### 4. Name the files (people, with the audit's list)

Work from the audit, school by school.
- The 153 Rocket City clips (`20260506-162502-1011.mp4`, …) have no descriptive names at all and
  need someone to look at them. A contact sheet (one frame per clip) speeds that up.
- Write the final names into a two-column sheet: `old path` → `new path`.
- Keep the poster's name in step with its video (`hero.mp4` ↔ `hero.webp`).

### 5. Move a school to the CDN, one school at a time

1. Upload that school's optimized and renamed files through the portal's **Media** page. They land
   in `cdn.rightruddermarketing.com/<school-folder>/…`.
2. Update the school's website to the new URLs, adding `poster="…webp"` to each `<video>`.
3. Check the site: videos play and the posters show.
4. Only then is this repo's copy for that school no longer needed. Leave it in place for a while
   anyway: old cached pages and social posts may still point at jsDelivr.

## What the script will and won't do

- **Never modifies this repo.** It refuses an output folder inside it.
- **Lossless where it doesn't re-encode.** A kept original is copied, or remuxed with
  `-c copy` (identical audio and video, only the container rewritten) when it needs fast start
  or is a `.mov`. Checked 2026-10-28: the stream hashes match the original's.
- **Audio is copied untouched** in every case.
- **One file failing doesn't stop the run.** It's marked FAILED in the report, with the reason.

## Trial results (2026-10-28)

| File | Before | After | Result |
|---|---:|---:|---|
| 4K simulator clip (`active-pilot/…/simulator-content-1.mp4`) | 22 MB | 7 MB | re-encoded + scaled, SSIM 0.990 |
| `skymates/gallery/aircraft-tour.mp4` | 14 MB | 7 MB | re-encoded, SSIM 0.990 |
| `hawkins/…rv-12…mp4` | 2.7 MB | 1.4 MB | re-encoded, SSIM 0.990 |
| `deaero/n5935g-take-off.mp4` | 10 MB | (14 MB) | already lean, so the original is kept |
| `m2a/*.mov`, `cirrus-aviation/*` | — | same size | original remuxed for fast start / `.mp4` |

The real total comes out of step 3's report. Don't extrapolate from five files.

## Considered and not chosen: WebM (VP9 / AV1)

WebM is the video counterpart of WebP. We tested it on 2026-10-28 with
`skymates/gallery/aircraft-tour.mp4`, 50 s, video track only:

| | Video size | SSIM vs original | Encode time |
|---|---:|---:|---:|
| H.264 MP4, crf 23 (what the script makes) | 6.4 MB | 0.990 | 13 s |
| VP9 WebM, crf 34 | 4.1 MB (37% smaller) | 0.987 | 45 s |

AV1 would be smaller still, but the AV1 encoder in our ffmpeg (4.4, libaom) is far too slow for
316 videos.

**Decision: MP4 only.** Safari/iPhone support for WebM came late and still depends on the device
and OS version, and a lot of flight-school traffic is on iPhones. Making WebM safe means shipping
both formats: a `<source>` for each, so three files per video counting the poster, and
3.5× the encode time. That isn't worth the risk and the work for now.

**Revisit if** page speed becomes a priority on specific heavy hero videos, or once WebM/AV1
plays reliably on the iPhones we see in traffic. The portal's Media library already accepts
`.webm`, so adding it later needs no app change.

## Requirements

`ffmpeg` and `ffprobe` with `libx264` and `libwebp` (Ubuntu: `sudo apt install ffmpeg`;
`ffmpeg -encoders | grep -E "libx264|libwebp"` should show both), and Python 3.8+. Nothing else.

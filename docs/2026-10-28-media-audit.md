# Media audit — 2026-10-28

What is in this repo (served to client websites through jsDelivr), how much it can be
compressed, and which file names are bad for SEO. Full per-file table:
[2026-10-28-media-inventory.csv](2026-10-28-media-inventory.csv). What to do about it:
[optimization-plan.md](optimization-plan.md).

## What's there

**316 videos, no images.** 314 `.mp4`, 2 `.mov`, 2.53 GB in total. All are H.264. 295 have AAC
audio and 21 have none. 247 are portrait (reels/shorts) and 69 landscape.

| Folder | Files | Size |
|---|---:|---:|
| rocket-city | 154 | 727 MB |
| deaero | 55 | 534 MB |
| skymates | 34 | 441 MB |
| active-pilot | 35 | 399 MB |
| vegas-aviation | 11 | 133 MB |
| blitz | 3 | 53 MB |
| m2a | 2 | 40 MB |
| rrm-2 | 3 | 35 MB |
| aviator-inc | 4 | 33 MB |
| mh | 4 | 32 MB |
| bird-dog, volair, wright-base, elevation-aviation, magnolia, truflight, cirrus-aviation, hawkins | 11 | 99 MB |

Resolution (long side): 201 files at 1080, 54 at 1920, 27 at 4K (3840), 27 at 1280, 7 other.
Bitrate: median 2.8 Mbps, p90 6.1 Mbps, max 13.4 Mbps. 17 files are above 8 Mbps.

## Compression

**WebP doesn't apply here.** WebP is an image format and there are no images in the repo. For
videos, the equivalent wins are:

1. **4K → 1080p for the web (27 files).** No website box shows 4K, and these are the heaviest
   files per second.
2. **Re-encode high-bitrate files**: H.264, `-crf 23 -preset slow`, keeping MP4. That container
   plays everywhere, and Safari/iOS still has gaps with WebM/AV1.
3. **`+faststart` on the 27 files without it.** The browser can start playing before the whole
   file has downloaded.
4. **Keep the original when re-encoding doesn't make it smaller.**
5. *(Optional)* drop the audio track from muted autoplay hero/background videos.
6. *(Where WebP does fit)* a **`.webp` poster frame per video**, for `<video poster=…>`. The page
   shows a light image instead of a blank box while the video loads, which helps LCP.

"Without losing anything": truly lossless re-encoding makes video files *bigger*, so the target is
**visually lossless**, measured with SSIM against the original.

**WebM (VP9/AV1) was considered and not chosen.** In our test it was 37% smaller than H.264, but
Safari/iPhone support is too uneven to rely on, and shipping both formats isn't worth it for now.
Details: [optimization-plan.md](optimization-plan.md#considered-and-not-chosen-webm-vp9--av1).

### Trial (3 files, 2026-10-28, on a laptop)

| File | Before | After | Change | SSIM vs original |
|---|---:|---:|---:|---:|
| active-pilot/simulator-content/videos/simulator-content-1.mp4 (4K, 13 Mbps) | 22 MB | 7 MB | −67% | 0.990 (compared at 1080p) |
| skymates/gallery/aircraft-tour.mp4 (608×1080) | 14 MB | 7 MB | −50% | 0.990 |
| deaero/n5935g-take-off.mp4 (1080p, already lean) | 10 MB | 14 MB | **+33%** | — keep original |

SSIM ≈ 0.99 is visually indistinguishable in practice. Three files aren't a forecast for 2.5 GB;
the script's dry run should report the real total.

## File names bad for SEO

How much file names matter: for video, Google relies far more on the page (title, surrounding
text, `VideoObject` schema, transcript) than on the file name. But a descriptive name is free and
also shows in the URL, so it's worth fixing **while moving to the CDN**. Renaming in the repo
breaks every live jsDelivr link, while moving to the CDN changes every URL anyway.

**Naming pattern:** `<what-happens>-<aircraft/topic>-<school>-<city-or-state>.mp4`, lowercase,
dashes, no workflow words. Examples: `first-solo-reaction-active-pilot-los-angeles.mp4`,
`cessna-150-takeoff-deaero.mp4`.

### 1. Meaningless names (no description at all)

- **rocket-city/photo-circle-media/ — 153 files** named like `20260506-162502-1011.mp4`
  (timestamp + hash). The biggest problem in the repo. The names say nothing about the content,
  so someone has to watch them, or I can pull a frame from each into a contact sheet to speed up
  naming.
- `active-pilot/social-media-content/videos/content.mp4`
- `active-pilot/simulator-content/videos/simulator-content-1.mp4` … `-4.mp4`
- `active-pilot/old-website/videos/landing-page-video.mp4`
- `magnolia/hero-video-horizontal.mp4`
- `wright-base/hero-video.mp4`
- `volair/old-website/hero-video-old-website.mp4`
- `skymates/hero-video-placeholder.mp4`
- `skymates/gallery/aircraft-tour.mp4`, `what-is-a-spin.mp4`, `jake-improv-interview.mp4` (no
  school name)
- `deaero/farm-wind-farm.mp4`

### 2. Typos (also wrong keywords)

| Now | Suggested |
|---|---|
| `blitz/bliz-new-piper-aircraft-videos-fpying-over-utah-and-ogden-city.mp4` | `new-piper-aircraft-flying-over-ogden-utah-blitz-aviation.mp4` |
| `active-pilot/checkrides/videos/michael-velasco-comm-multi-reacton.mp4` | `commercial-multi-engine-checkride-reaction-active-pilot.mp4` |
| `deaero/chmap-landing.mp4` | `champ-landing-deaero.mp4` |
| `deaero/flyinig-view-from-cockpit-1.mp4`, `-2.mp4` | `cockpit-view-in-flight-deaero-1.mp4`, `-2.mp4` |
| `deaero/fomation150-lead-close1.mp4` | `cessna-150-formation-flight-lead-close-deaero-1.mp4` |
| `hawkins/flying-over-chicago-with-new-rv-12-hawkings-flight-academy.mp4` | `rv-12-flying-over-chicago-hawkins-flight-academy.mp4` |
| `skymates/gallery/italian-pilots-share-why-they-chose-sky-maze-for-flight-training.mp4` | `italian-pilots-why-they-chose-skymates-flight-training.mp4` |
| `skymates/gallery/skymates-ths-is-your-sign-final.mp4` | `this-is-your-sign-to-become-a-pilot-skymates.mp4` |

### 3. Workflow words that leak into URLs

- **`-final`, 22 files in skymates/gallery**, e.g. `skymates-3-mistakes-final.mp4` →
  `3-mistakes-student-pilots-make-skymates.mp4`, `skymates-in-house-maintenance-final.mp4` →
  `in-house-aircraft-maintenance-skymates.mp4`.
- **`-compressed`**:
  - `mh/mh-aviation-hero-horizontal-compressed.mp4` and `…-vertical-compressed.mp4`, which also
    have uncompressed twins in the same folder. Keep one of each, e.g.
    `flight-training-mh-aviation-lancaster-ca-horizontal.mp4`.
  - `truflight/truflight-helicopter-flight-compressed.mp4`,
    `truflight-helicopter-training-compressed.mp4`.
- **Internal abbreviations:** `mbm-skymates-ben-math-reel.mp4`,
  `mbm-skymates-luca-reel-captioned.mp4`, `skymates-kate-reel2-final.mp4`,
  `skymates-brando-intv-final.mp4` **and** `skymates-brandon-intv-final.mp4` (a duplicate, or a
  typo of the same person?).
- **Underscores / copy suffix:** `active-pilot/social-media-content/videos/tj-solo-_3_.mp4`.
- **Uppercase:** `rrm-2/RRM-american-flag.mp4` (URLs are case-sensitive on S3).
- **`-pt-1`, `.mov`:** `m2a/m2a-alex-power-off-180.mov`, `m2a-short-field-pt-1.mov` → convert to
  `.mp4` and name e.g. `power-off-180-landing-m2a-pikeville-nc.mp4`.

### 4. Internal codes with no context (deaero, 55 files)

- **Tail numbers:** 31 files, e.g. `n5935g-flying-over-green-landscape-4.mp4`,
  `n5935g-flying-view-from-distance-top-view-3.mp4`, `n1059e-landing-at-ramp-view-from-inside.mp4`.
  A tail number means nothing to someone searching. Replace it with the aircraft type
  (e.g. `cessna-172-…`) + `deaero`.
- **`150-*` / `champ-*`:** `150-over-lake.mp4`, `150-pass-break2.mp4`, `champ-takeoff1.mp4`, … →
  `cessna-150-…`, `aeronca-champ-…`. Confirm the aircraft first.
- **`imcapproach.mp4`, `takeoff-into-imc.mp4`:** missing separators and jargon →
  `instrument-approach-in-clouds-deaero.mp4`.

### 5. Student names instead of the achievement (active-pilot, vegas-aviation)

e.g. `fisal-cfi.mp4`, `shayan-ppl-pass.mp4`, `peter-solo-testimony.mp4`. A first name isn't
searched; the achievement and school are. Suggested: `cfi-checkride-pass-active-pilot-los-angeles.mp4`.
Keep the name at the end only when it matters, and only with the student's consent.

### 6. Not ours to host — check first

- `rocket-city/placeholder-from-cirrus-youtube-sr20-features.mp4`: Cirrus's YouTube content.
  Rights and SEO both argue for replacing it rather than renaming it.

### Already fine (keep as they are, or with small touches)

- `vegas-aviation/shorts/*`
- `blitz/blitz-aviation-video-header-flight-training-school-ogden-salt-lake-city-utah.mp4`
- `blitz/from-zero-to-commercial-pilot-in-7-months-blitz-aviation-utah-testimonial.mp4`
- `cirrus-aviation/*`
- `bird-dog/video-of-bird-dog-flight-services-piper-warrior.mp4` (drop the `video-of-`)
- `aviator-inc/*` (add the school name)

## Locations known in the portal (for names)

Las Vegas, NV (Vegas Aviation) · Pikeville, NC (M2A) · Lancaster, CA (MH Aviation) ·
Los Angeles, CA (Active Pilot). From the existing file names: Ogden, UT (Blitz) · Riverview, FL
(Cirrus Aviation) · Chicago (Hawkins). Not set in the portal: DeAero, Skymates, Rocket City,
TruFlight, Elevation, Wright Base, Magnolia, Volair.

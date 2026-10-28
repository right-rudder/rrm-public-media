# rrm-public-media

Public videos for Right Rudder Marketing's flight school clients, one folder per school
(`skymates/`, `deaero/`, …), served to their websites through jsDelivr.

**Live URLs point at these files.** Renaming, moving or re-encoding anything here changes what
client websites show, or breaks it. Don't, until that school has moved to
`cdn.rightruddermarketing.com`; see the plan below.

- [docs/2026-10-28-media-audit.md](docs/2026-10-28-media-audit.md): what's here (316 videos,
  2.5 GB), how much it can shrink, and which file names are bad for SEO.
- [docs/2026-10-28-media-inventory.csv](docs/2026-10-28-media-inventory.csv): every file with
  size, resolution, bitrate, length, audio.
- [docs/optimization-plan.md](docs/optimization-plan.md): compress and rename once, while moving
  each school to the CDN.
- [scripts/optimize_videos.py](scripts/optimize_videos.py): the compression tool. A dry run by
  default; writes to `../rrm-public-media-optimized/`, never into this repo.

```bash
python3 scripts/optimize_videos.py                          # what would happen
python3 scripts/optimize_videos.py --apply --only skymates  # do one school
```

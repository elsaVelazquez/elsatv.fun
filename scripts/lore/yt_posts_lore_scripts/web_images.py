#!/usr/bin/env python3
"""
web_images.py — make the web-sized copy of the datestamped pictures.

    venv/bin/python scripts/lore/yt_posts_lore_scripts/web_images.py
    venv/bin/python scripts/lore/yt_posts_lore_scripts/web_images.py --limit 20
    venv/bin/python scripts/lore/yt_posts_lore_scripts/web_images.py --force

Reads  lore/YTelsaTVposts/datestamped/*        the 1,617 stamped originals
Writes lore/YTelsaTVposts/web/<same name>.webp  display copy (this is what R2 gets)

WHY
---
The stamped originals are 1.92 GB. That is the master: it stays on the external
drive, goes into the Internet Archive zip, and is never resized. R2 has 10 GB
free and would take 1.9 GB of it for one folder — so the files that get served
to a browser are a separate, smaller set. Same picture, same black date bar,
just encoded for a screen instead of for an archive.

What it does to each file:
  * rotates by EXIF if the camera wrote a rotation flag, so the readable copy
    is never sideways
  * shrinks so the longest side is at most MAX_SIDE (1600 px)
  * re-encodes as WebP at QUALITY (82) — typically 4–6x smaller than the JPEG
  * never touches the original in datestamped/

Resumable: a file already in web/ is skipped unless --force. Safe to interrupt
and re-run; an interrupted file is written to .tmp and renamed at the end.
"""
import argparse
import sys
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path('lore/YTelsaTVposts')
SRC = ROOT / 'datestamped'
OUT = ROOT / 'web'

MAX_SIDE = 1600     # px on the long edge — twice a phone screen, sharp on retina
QUALITY = 82        # WebP quality; 82 is where artefacts stop being visible


def convert(src, dest):
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)
        if im.mode not in ('RGB', 'RGBA'):
            im = im.convert('RGB')
        if max(im.size) > MAX_SIDE:
            im.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
        tmp = dest.with_suffix('.tmp')
        im.save(tmp, format='WEBP', quality=QUALITY, method=6)
    tmp.replace(dest)
    return dest.stat().st_size


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=0, help='stop after N files')
    ap.add_argument('--force', action='store_true',
                    help='redo files that exist')
    args = ap.parse_args()

    if not SRC.is_dir():
        raise SystemExit(f'no {SRC} — run stamp_images.py first')
    files = sorted(p for p in SRC.iterdir() if p.is_file())
    if not files:
        raise SystemExit(f'{SRC} is empty')

    OUT.mkdir(parents=True, exist_ok=True)
    before = sum(p.stat().st_size for p in files)
    print(f'→ {len(files):,} image(s), {before / 1e9:.2f} GB in {SRC}')

    done = 0
    after = 0
    skipped = 0
    for i, src in enumerate(files, 1):
        dest = OUT / (src.stem + '.webp')
        if dest.exists() and not args.force:
            after += dest.stat().st_size
            skipped += 1
            continue
        try:
            after += convert(src, dest)
            done += 1
        except Exception as e:
            print(f'  {src.name}: {e}')
        if i % 100 == 0 or i == len(files):
            print(f'   [{i}/{len(files)}] {after / 1e6:.0f} MB written')
        if args.limit and done >= args.limit:
            print(f'  --limit {args.limit} reached')
            break

    out_count = len(list(OUT.glob('*.webp')))
    print(f'\n→ {OUT}')
    print(f'  {done} converted, {skipped} already done, {out_count} in folder')
    if before:
        print(f'  {before / 1e9:.2f} GB → {after / 1e6:.0f} MB '
              f'({after / before * 100:.0f}% of the originals)')


if __name__ == '__main__':
    main()

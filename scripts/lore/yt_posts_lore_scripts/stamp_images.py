#!/usr/bin/env python3
"""
stamp_images.py — put the post's date across the TOP of a COPY of each image.

    venv/bin/python scripts/lore/yt_posts_lore_scripts/stamp_images.py --limit 3     # look at a sample
    venv/bin/python scripts/lore/yt_posts_lore_scripts/stamp_images.py               # all of them

Originals in lore/YTelsaTVposts/images/ are never touched. Stamped copies are
written to lore/YTelsaTVposts/datestamped/.

Design notes, because these are the bits you will want to change by hand:

  * The date goes in a BLACK BAR added above the photo (the canvas grows), so
    no part of the picture is covered. `PAD_ABOVE` controls the bar height.
  * Font size is computed from the image's SHORT edge, so it reads the same on
    a 1170-px screenshot and a 4032-px photo. `FONT_RATIO` is the knob.
  * Dates come from dates.json (Mountain time), keyed by post id. An image file
    is named "<postId>_<n>.jpg", so the post id is the filename before "_".
  * If a post has no date we fall back to the image's own XMP DateTimeOriginal,
    converted to Mountain time — better than nothing, clearly marked.
"""
import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont

ROOT = Path('lore/YTelsaTVposts')
SRC = ROOT / 'images'
DEST = ROOT / 'datestamped'
DATES = ROOT / 'dates.json'

TZ = ZoneInfo('America/Denver')

# --- the three knobs you are most likely to change ------------------------- #
PAD_ABOVE = 0.10      # bar height as a fraction of image width
FONT_RATIO = 0.045    # font size as a fraction of the image's short edge
MIN_FONT = 18
# --------------------------------------------------------------------------- #

BG = (0, 0, 0)
FG = (255, 255, 255)

FONT_CANDIDATES = [
    '/System/Library/Fonts/Supplemental/Arial Bold.ttf',
    '/System/Library/Fonts/Supplemental/Arial.ttf',
    '/System/Library/Fonts/Helvetica.ttc',
]


# --------------------------------------------------------------------------- #
def load_dates(dates_path=DATES):
    """{post_id: {'display': ..., 'date_key': ...}}"""
    if not dates_path.exists():
        return {}
    try:
        return json.loads(dates_path.read_text()).get('posts', {})
    except Exception:
        return {}


def post_id_of(filename):
    """'Ugkx…_1.jpg' -> 'Ugkx…'"""
    return Path(filename).stem.rsplit('_', 1)[0]


def date_from_xmp(path):
    """
    Fallback date straight out of the file's own metadata.

    Returns a display string in Mountain time, or '' when nothing usable.
    Phones write DateTimeOriginal with no timezone, so +00:00 is assumed; the
    value you archived matches the burned-in text, so treat it as UTC.
    """
    try:
        raw = path.read_bytes()[:80000]
    except Exception:
        return ''
    m = re.search(
        rb'exif:DateTimeOriginal="([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:]{8})', raw)
    if not m:
        return ''
    try:
        dt = datetime.fromisoformat(
            m.group(1).decode()).replace(tzinfo=ZoneInfo('UTC'))
        return dt.astimezone(TZ).strftime('%b %-d, %Y %-I:%M %p')
    except Exception:
        return ''


def display_for(filename, dates):
    """Best date label we can produce for one image."""
    rec = dates.get(post_id_of(filename)) or {}
    if rec.get('display'):
        return rec['display']
    return date_from_xmp(SRC / filename)


def pick_font(size):
    for cand in FONT_CANDIDATES:
        if Path(cand).exists():
            try:
                return ImageFont.truetype(cand, size)
            except Exception:
                continue
    return ImageFont.load_default()


def font_size_for(img):
    """Proportional to the short edge, so every image reads the same."""
    short = min(img.size)
    return max(MIN_FONT, int(short * FONT_RATIO))


def stamp_one(src_path, dest_path, label):
    """
    Add a black bar above the image and centre `label` in it, white on black.

    Returns (width, height, font_px) of the result. Overwrites dest_path.
    """
    with Image.open(src_path) as im:
        im = im.convert('RGB')
        w, h = im.size
        font_px = font_size_for(im)
        font = pick_font(font_px)
        pad = int(w * PAD_ABOVE)

        canvas = Image.new('RGB', (w, h + pad), BG)
        canvas.paste(im, (0, pad))

        draw = ImageDraw.Draw(canvas)
        box = draw.textbbox((0, 0), label, font=font)
        tw, th = box[2] - box[0], box[3] - box[1]
        # squeeze the font down if the label would overflow the width
        while tw > w - 20 and font_px > MIN_FONT:
            font_px = int(font_px * 0.9)
            font = pick_font(font_px)
            box = draw.textbbox((0, 0), label, font=font)
            tw, th = box[2] - box[0], box[3] - box[1]

        x = (w - tw) / 2
        y = (pad - th) / 2 - box[1]
        draw.text((x, y), label, font=font, fill=FG)

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(dest_path, quality=92)
        return canvas.size[0], canvas.size[1], font_px


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=0, help='first N images only')
    ap.add_argument('--src', default=str(SRC))
    ap.add_argument('--dest', default=str(DEST))
    args = ap.parse_args()

    src = Path(args.src)
    dest = Path(args.dest)
    dates = load_dates()

    files = sorted(src.glob('*.jpg'))
    if args.limit:
        files = files[:args.limit]
    print(f'→ stamping {len(files)} image(s) into {dest}')

    undated = 0
    for i, path in enumerate(files, 1):
        label = display_for(path.name, dates)
        if not label:
            undated += 1
            label = 'date unknown'
        out = dest / path.name
        w, h, fp = stamp_one(path, out, label)
        print(f'  [{i}/{len(files)}] {path.name[:34]:34} '
              f'{label:24} {w}x{h} font {fp}px')

    print(f'\n→ {dest}')
    print(f'  {len(files)} stamped, {undated} without a known date')


if __name__ == '__main__':
    main()

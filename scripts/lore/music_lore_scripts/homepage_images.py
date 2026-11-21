#!/usr/bin/env python3
"""homepage_images.py — pick the random album covers the homepage shows.

On every sync run this picks three released albums at random, copies their
covers to lore/covers/home_cover_1..3.jpg and stamps the choice into
lore/home_cover.json. index.html therefore never needs JavaScript: it just
points at the three fixed filenames, which get rewritten each run.
"""

import datetime
import io
import json
import os
import random
import re
import urllib.request

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
ALBUMS = os.path.join(ROOT, 'lore', 'albums.json')
COVERS = os.path.join(ROOT, 'lore', 'covers')
STAMP = os.path.join(ROOT, 'lore', 'home_cover.json')

# The homepage has room for three squares; the middle one is the big stack.
COUNT = 3

# Keep the previous pick when we cannot fetch a cover, so a failed run never
# leaves the homepage with a broken image.
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; elsatv.fun homepage picker)'}


def _cover_for(album):
    """Prefer the album's own cover, fall back to its first song's video still."""
    if album.get('cover_art'):
        return album['cover_art']
    for song in album.get('songs') or []:
        link = song.get('youtube_link') or ''
        if 'v=' in link:
            return f"https://i.ytimg.com/vi/{link.split('v=')[-1].split('&')[0]}/hqdefault.jpg"
    return ''


def _fetch(url, timeout=20):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _square_art(blob):
    """Cut the album art out of a YouTube thumbnail.

    i.ytimg.com only serves the 16:9 still for a release (the `-no-1` square
    variants answer 404), and the square sleeve is inset inside it: a typical
    frame is 480×360 with the art at x=120..360, i.e. flat padding on BOTH
    sides, at the top and at the bottom. Cropping from x=0 kept the left bar
    and cut the right of the art, so the picture sat right of centre in its
    card with a margin only on the left.

    Find the inset art (the region that is not flat padding), then crop a
    square that is centred on it — trimming never moves the art off centre.
    """
    try:
        im = Image.open(io.BytesIO(blob))
        im = im.convert('RGB')
        w, h = im.size
        if not (w and h):
            return blob

        box = _art_box(im)
        if box is None:
            # no padding found: a square needs no work, a still is cropped at
            # its left edge as before
            if w > h:
                im = im.crop((0, 0, h, h))
        else:
            left, top, right, bottom = box
            cx, cy = (left + right) / 2, (top + bottom) / 2
            side = min(right - left, bottom - top)
            side = max(1, side)
            x0 = int(round(cx - side / 2))
            y0 = int(round(cy - side / 2))
            x0 = max(0, min(w - side, x0))
            y0 = max(0, min(h - side, y0))
            im = im.crop((x0, y0, x0 + side, y0 + side))

        out = io.BytesIO()
        im.save(out, 'JPEG', quality=90)
        return out.getvalue()
    except Exception:
        return blob


def _art_box(im, tol=24):
    """Bounding box (left, top, right, bottom) of the artwork in a thumbnail.

    Padding is a bar of ONE colour the full length of its side — a black
    letterbox, or a single pixel of the cover stretched to fill the frame. It
    is not perfectly constant after JPEG, but it is far closer to its own edge
    colour than any column of real art is.

    So measure that instead of "is this line exactly flat": walk in from each
    edge while the line's colour stays within `tol` of the outermost line's
    colour. Never trim more than a third of a side, so a genuinely dark border
    on a cover is not eaten. Returns None if nothing is padding.
    """
    w, h = im.size
    px = im.load()
    sy = max(1, h // 48)
    sx = max(1, w // 48)

    def column_stats(x):
        vals = [px[x, y] for y in range(top, bottom, sy)]
        return (sum(v[0] for v in vals) / len(vals),
                sum(v[1] for v in vals) / len(vals),
                sum(v[2] for v in vals) / len(vals),
                max(max(v) for v in vals))

    def row_stats(y):
        vals = [px[x, y] for x in range(left, right, sx)]
        return (sum(v[0] for v in vals) / len(vals),
                sum(v[1] for v in vals) / len(vals),
                sum(v[2] for v in vals) / len(vals),
                max(max(v) for v in vals))

    left, right, top, bottom = 0, w, 0, h
    cap_x, cap_y = w // 3, h // 3

    # rows first: a letterbox bar is found across the FULL width
    def close(a, b):
        return (abs(a[0] - b[0]) + abs(a[1] - b[1]) + abs(a[2] - b[2])) <= tol

    base = row_stats(0)
    while top < cap_y and close(row_stats(top), base):
        top += 1
    base = row_stats(h - 1)
    while h - bottom < cap_y and close(row_stats(bottom - 1), base):
        bottom -= 1

    # then the side bars, measured within the surviving rows
    base = column_stats(0)
    while left < cap_x and close(column_stats(left), base):
        left += 1
    base = column_stats(w - 1)
    while w - right < cap_x and close(column_stats(right - 1), base):
        right -= 1

    if right - left < 8 or bottom - top < 8:
        return None
    if (left, top, right, bottom) == (0, 0, w, h):
        return None
    return left, top, right, bottom


def pick(count=COUNT, rng=None):
    """Choose `count` albums (no repeats), download their covers, stamp the run.

    Returns the list of stamped records. Raises nothing for a single bad
    cover — that slot is skipped — but raises FileNotFoundError when there is
    no lore/albums.json to read.
    """
    with open(ALBUMS, encoding='utf-8') as f:
        data = json.load(f)

    albums = [a for a in data.get('albums', []) if _cover_for(a)]
    if not albums:
        raise RuntimeError('no albums with cover art in albums.json')

    rng = rng or random.SystemRandom()
    chosen = rng.sample(albums, min(count, len(albums)))

    os.makedirs(COVERS, exist_ok=True)
    picked = []
    for i, album in enumerate(chosen, start=1):
        name = f'home_cover_{i}.jpg'
        path = os.path.join(COVERS, name)
        try:
            blob = _fetch(_cover_for(album))
            if not blob:
                raise ValueError('empty response')
        except Exception as exc:  # network hiccup: drop this slot's old file too
            print(f'  cover {i} failed ({album["album_name"]}): {exc}')
            if os.path.exists(path):
                os.remove(path)
            continue
        with open(path, 'wb') as f:
            f.write(_square_art(blob))
        picked.append({
            'slot': i,
            'file': f'lore/covers/{name}',
            'album_name': album.get('album_name', ''),
            'album_link': album.get('album_link') or album.get('youtube_link', ''),
            # the matching card id on kissingface.html, so the homepage cover can
            # deep-link to its own release instead of the top of the grid
            # same rule as _anchor() in FINAL_SYNC.py, which ids the cards
            'album_slug': re.sub(r'[^a-z0-9]+', '-',
                                 str(album.get('album_name', '')).lower()).strip('-'),
        })

    if not picked:
        raise RuntimeError('every cover download failed; leaving homepage as-is')

    stamp = {
        'picked_at': datetime.datetime.now(datetime.timezone.utc)
                       .strftime('%Y-%m-%dT%H:%M:%SZ'),
        'covers': picked,
    }
    with open(STAMP, 'w', encoding='utf-8') as f:
        json.dump(stamp, f, indent=2)
        f.write('\n')

    for p in picked:
        print(f"  home slot {p['slot']}: {p['album_name']}")

    _retarget_homepage(picked)
    return picked


HOME = os.path.join(ROOT, 'index.html')


def _retarget_homepage(picked):
    """Point index.html's three sleeves at the releases just picked.

    The images are overwritten in place, so without this the hrefs keep naming
    whatever release was chosen last run — the sleeve would show Bad Actor? and
    open Juicy Juice. Each slot's anchor and alt are rewritten to the stamp, so
    the link always names the artwork under it. Best effort: a missing index.html
    or a slot that is not found prints and leaves the file alone.
    """
    try:
        with open(HOME, encoding='utf-8') as f:
            html = f.read()
    except OSError as exc:
        print(f'  index.html not retargeted: {exc}')
        return

    for p in picked:
        n = p['slot']
        slug = p.get('album_slug') or ''
        name = p['album_name']
        if not slug:
            continue

        # the anchor: href + title on one opening tag, alt on the image
        pattern = re.compile(
            r'(<a class="lore-cover[^"]*" href="kissingface\.html#)[^"]*("'
            r' title=")[^"]*(">\s*<img src="lore/covers/home_cover_' + str(n) +
            r'\.jpg" alt=")[^"]*(")')
        new, count = pattern.subn(
            lambda m, s=slug, nm=name: (
                f'{m.group(1)}{s}{m.group(2)}{nm} — open this release in the '
                f'Kissing Face lore{m.group(3)}{nm} — open this release in the '
                f'Kissing Face lore{m.group(4)}'),
            html)
        if count:
            html = new
        else:
            print(f'  index.html slot {n} not found — href left as-is')

    try:
        with open(HOME, 'w', encoding='utf-8') as f:
            f.write(html)
    except OSError as exc:
        print(f'  index.html not retargeted: {exc}')


if __name__ == '__main__':
    pick()

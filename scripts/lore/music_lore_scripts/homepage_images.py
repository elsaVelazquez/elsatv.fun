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

    i.ytimg.com only serves the 16:9 still for a release: the square cover sits
    at the LEFT edge of that frame, with the title card and a blurred pillar
    filling the rest (the `-no-1` square variants answer 404). Cropping the
    leftmost 1:1 square is the actual sleeve; anything already square, or an
    image we cannot decode, is returned untouched.
    """
    try:
        im = Image.open(io.BytesIO(blob))
        im = im.convert('RGB')
        w, h = im.size
        if w and h and w > h:
            im = im.crop((0, 0, h, h))
        out = io.BytesIO()
        im.save(out, 'JPEG', quality=90)
        return out.getvalue()
    except Exception:
        return blob


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

#!/usr/bin/env python3
"""homepage_images.py — pick the random album covers the homepage shows.

On every sync run this picks three released albums at random, copies their
covers to lore/covers/home_cover_1..3.jpg and stamps the choice into
lore/home_cover.json. index.html therefore never needs JavaScript: it just
points at the three fixed filenames, which get rewritten each run.
"""

import datetime
import json
import os
import random
import urllib.request

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
            f.write(blob)
        picked.append({
            'slot': i,
            'file': f'lore/covers/{name}',
            'album_name': album.get('album_name', ''),
            'album_link': album.get('album_link') or album.get('youtube_link', ''),
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
    return picked


if __name__ == '__main__':
    pick()

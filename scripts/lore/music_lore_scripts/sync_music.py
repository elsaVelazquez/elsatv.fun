#!/usr/bin/env python3
"""
sync_music.py — the one command for the music page, end to end.

    venv/bin/python scripts/lore/music_lore_scripts/sync_music.py
    venv/bin/python scripts/lore/music_lore_scripts/sync_music.py --skip-links
    venv/bin/python scripts/lore/music_lore_scripts/sync_music.py --no-push

Same idea as sync_posts.py for the posts page: run the steps in order, skip
nothing that is overdue, rebuild only what changed, and say what is still
missing at the end.

WHY THIS EXISTS
---------------
FINAL_SYNC.py does NOT discover song links. It only *reads* them from
lore/music_links_enriched.json, and the script that writes that file is
collect_music_links.py — a separate step that was never in the routine. So for
a new release the card appeared with a tracklist whose song names were plain
text, and running FINAL_SYNC.py alone could never fix it, however many times it
ran.

WHAT IT DOES, IN ORDER
----------------------
  1. build_albums.py          ONCE -> lore/albums.json (tracklists)
  2. collect_music_links.py   albums.json -> lore/music_links_enriched.json
                              (the per-song YouTube Music links)
  3. FINAL_SYNC.py            -> kissingface.html + lore/songs.json
  4. reports any song name that still has no link

Step 2 is the one that takes minutes and does network lookups. It is skipped
with --skip-links when you only need the page rebuilt.

LINKS ADDED BY HAND ARE NEVER LOST
----------------------------------
collect_music_links.py rebuilds the enriched file from the catalogue, so a
search that fails on a rerun could in principle drop a link it found last time.
This script therefore merges: every song link already in the old file survives
unless the new file has a value for that same song. Nothing is deleted.

It does not commit or push (pass --push to do that too, staging every file the
music page is built from).
"""
import argparse
import json
import re
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path('.')
ALBUMS = ROOT / 'lore/albums.json'
ENRICHED = ROOT / 'lore/music_links_enriched.json'
PAGE = ROOT / 'kissingface.html'

PY = sys.executable
# Everything a music sync can change and that the next run needs.
STAGE = [
    'kissingface.html', 'lore/songs.json', 'lore/albums.json',
    'lore/music_links_enriched.json', 'lore/yt_link_cache.json',
    'lore/releases_cache.json', 'lore/release_dates.json',
]


def norm(s):
    """Same comparison as FINAL_SYNC.py: case, punctuation, spacing ignored."""
    s = unicodedata.normalize('NFKC', s or '').lower()
    s = re.sub(r'[\u200b-\u200f\ufeff]', '', s)
    return re.sub(r'[^0-9a-z]+', '', s)


def load(path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def song_links(doc):
    """{'<album>|<song>': link} for every non-empty song link in an enriched file."""
    out = {}
    for a in (doc or {}).get('albums') or []:
        album = norm(a.get('album_name') or '')
        for s in a.get('songs') or []:
            link = s.get('youtubemusic_song_link')
            if link:
                out[f"{album}|{norm(s.get('song_name') or '')}"] = link
    return out


def merge_links(old, new_path):
    """Put back any song link the new file lost, and report what was restored."""
    new = load(new_path, None)
    if not new or not isinstance(new.get('albums'), list):
        raise SystemExit(
            f'{new_path} is missing or unreadable after the lookups')
    before = song_links(old)
    after = song_links(new)
    lost = {k: v for k, v in before.items() if k not in after}
    if not lost:
        return 0
    for a in new['albums']:
        album = norm(a.get('album_name') or '')
        for s in a.get('songs') or []:
            key = f"{album}|{norm(s.get('song_name') or '')}"
            if not s.get('youtubemusic_song_link') and key in lost:
                s['youtubemusic_song_link'] = lost[key]
                s['restored'] = True
    new_path.write_text(json.dumps(new, indent=2, ensure_ascii=False),
                        encoding='utf-8')
    print(f'  kept {len(lost)} link(s) the lookup did not re-find this time')
    return len(lost)


def run(script, args=(), label=''):
    print(f'\n▸ {label or script}')
    print(f'  $ {PY} {HERE / script} {" ".join(args)}'.rstrip())
    t0 = time.time()
    r = subprocess.run([PY, str(HERE / script), *args], cwd=Path.cwd())
    if r.returncode != 0:
        print(f'  ✗ {script} exited {r.returncode} — stopping here.')
        return False
    print(f'  ✓ {script} ({time.time() - t0:.1f}s)')
    return True


def unlinked_songs(page):
    """Song names rendered as plain text (no <a>) — i.e. still without a link.

    The page marks a linked name with <a class="name" href=...> and an
    unlinked one with <span class="name">.
    """
    if not page.exists():
        return []
    html = page.read_text(encoding='utf-8')
    return [re.sub(r'<[^>]+>', '', m).strip()
            for m in re.findall(r'<span class="name">(.*?)</span>', html, re.S)]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--skip-links', action='store_true',
                    help='do not look up song links (fast: only rebuild the page)')
    ap.add_argument('--push', action='store_true',
                    help='commit the generated files and push to origin main')
    ap.add_argument('--no-push', action='store_true',
                    help='(default) leave the commit and push to you')
    args = ap.parse_args()

    if not args.skip_links:
        if not run('build_albums.py', (), '1/3 album tracklists from ONCE'):
            return 1
        old = load(ENRICHED, {})
        if not run('collect_music_links.py', (), '2/3 find the song links'):
            return 1
        merge_links(old, ENRICHED)

    if not run('FINAL_SYNC.py', (), '3/3 rebuild kissingface.html'):
        return 1

    missing = unlinked_songs(PAGE)
    print()
    if missing:
        print(f'⚠️  {len(missing)} song name(s) still have no link:')
        for name in missing[:20]:
            print(f'     - {name}')
        print('   These are songs the catalogue could not match. Pin them by hand\n'
              '   with add_link.py if the song is live on YouTube Music.')
    else:
        print('✅ every song name on the page is a link')

    if args.push:
        subprocess.run(['git', 'add', *STAGE], check=True)
        if subprocess.run(['git', 'diff', '--cached', '--quiet']).returncode == 0:
            print('nothing changed — nothing to commit')
            return 0
        subprocess.run(
            ['git', 'commit', '-m', 'Update music page'], check=True)
        subprocess.run(['git', 'push', 'origin', 'main'], check=True)
        print('pushed to origin main')
    else:
        print('\nnot committed. To publish:\n'
              f'  git add {" ".join(STAGE)}\n'
              '  git commit -m "Update music page" && git push origin main')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

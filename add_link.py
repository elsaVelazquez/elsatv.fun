#!/usr/bin/env python3
"""
add_link.py — add a hand-entered YouTube link to lore/manual_links.json.

These entries win over ONCE and the releases-page scrape, and FINAL_SYNC.py
never overwrites this file.

    venv/bin/python add_link.py "30 Degrees 3 Spaces Laticees" \
        "https://www.youtube.com/watch?v=z_e14ecs-KU&list=OLAK5uy_mSF01UaY0k8YpzHduBuVa53ZPwfe4pJ0I"

    venv/bin/python add_link.py --list          # show what's in there
    venv/bin/python add_link.py --missing       # show releases with no link
"""
import json
import re
import sys
from pathlib import Path

MANUAL = Path('lore/manual_links.json')
CACHE = Path('lore/yt_link_cache.json')


def load():
    if MANUAL.exists():
        try:
            return json.loads(MANUAL.read_text())
        except json.JSONDecodeError as e:
            raise SystemExit(f'{MANUAL} is not valid JSON: {e}')
    return {}


def playlist_from(url):
    m = re.search(r'[?&]list=(OLAK5uy_[A-Za-z0-9_-]+)', url)
    return (f'https://music.youtube.com/playlist?list={m.group(1)}' if m else '')


def main():
    args = sys.argv[1:]

    if args and args[0] == '--list':
        data = load()
        for k, v in data.items():
            if k.startswith('_'):
                continue
            print(f'{k}\n  {v.get("youtube_link", "")}\n  {v.get("album_link", "")}')
        return

    if args and args[0] == '--missing':
        cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
        blank = [v['title']
                 for v in cache.values() if not v.get('youtube_url')]
        print(f'{len(blank)} without a link:')
        for t in blank:
            print(' ', t)
        return

    if len(args) != 2:
        raise SystemExit(__doc__)

    name, url = args
    url = url.strip()
    if 'watch?v=' not in url and 'playlist?list=' not in url:
        raise SystemExit(
            'That does not look like a YouTube / YouTube Music URL')

    data = load()
    data[name] = {
        'youtube_link': url,
        'album_link': playlist_from(url),
    }
    MANUAL.parent.mkdir(parents=True, exist_ok=True)
    MANUAL.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n',
                      encoding='utf-8')
    print(f'saved {name}')


if __name__ == '__main__':
    main()

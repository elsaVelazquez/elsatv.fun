#!/usr/bin/env python3
"""
build_albums.py — album-level view of the discography.

Writes lore/albums.json:

    {
      "generated_at": "2026-11-13T…",
      "album_count": 78,
      "albums": [
        {
          "album_name": "Puppets",
          "date_published": "2026-10-24",
          "youtube_link": "https://www.youtube.com/watch?v=Zi0UoWCs9Qk&list=OLAK5uy_…",
          "album_link": "https://music.youtube.com/playlist?list=OLAK5uy_…",
          "cover_art": "https://i.ytimg.com/vi/Zi0UoWCs9Qk/hqdefault.jpg",
          "songs": [
            {"track_number": 1, "song_name": "Spiral's Lei Line Bend", "duration": "7:02"},
            …
          ]
        }
      ]
    }

Sources, same precedence as FINAL_SYNC.py:
    lore/manual_links.json   album_link (authoritative, has the OLAK5uy_ id)
    lore/yt_link_cache.json  track link + cover, already resolved
    ONCE  /releases/{id}     the tracklist
    scrape @elsavelaz/releases  album playlist for anything manual missed

    venv/bin/python build_albums.py
"""
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

MANUAL_FILE = Path('lore/manual_links.json')
CACHE_FILE = Path('lore/yt_link_cache.json')
TRACKS_FILE = Path('lore/tracks_cache.json')
OUT = Path('lore/albums.json')

RELEASES_URL = 'https://www.youtube.com/@elsavelaz/releases'
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0 Safari/537.36')


def load_env():
    if os.path.exists('.env'):
        with open('.env') as f:
            for line in f:
                if line.strip() and not line.startswith('#'):
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value


def norm(s):
    s = (s or '').replace('\u200b', '').replace(
        '\u200c', '').replace('\u200d', '')
    return re.sub(r'[^a-z0-9]', '', s.lower())


def video_id(url):
    m = re.search(r'[?&]v=([A-Za-z0-9_-]{11})', url or '')
    return m.group(1) if m else None


def playlist_id(url):
    m = re.search(r'[?&]list=(OLAK5uy_[A-Za-z0-9_-]+)', url or '')
    return m.group(1) if m else None


def as_album_url(url):
    """Turn any watch?v=…&list=OLAK5uy_… into the canonical playlist URL."""
    pid = playlist_id(url)
    return f'https://music.youtube.com/playlist?list={pid}' if pid else ''


def duration(seconds):
    if not seconds:
        return ''
    return f'{seconds // 60}:{seconds % 60:02d}'


def load_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


# --------------------------------------------------------------------------- #
def get_releases(pat):
    headers = {'Authorization': f'Bearer {pat}',
               'Content-Type': 'application/json'}
    out, offset = [], 0
    while True:
        r = requests.get(f'https://once.app/v1/releases?limit=100&offset={offset}',
                         headers=headers, timeout=60)
        r.raise_for_status()
        data = r.json()
        out.extend(data.get('releases') or [])
        if data.get('nextOffset') is None:
            break
        offset = data['nextOffset']
    return out


def get_tracks(release_id, pat, retries=4):
    """Tracklist for one release. Cached in lore/tracks_cache.json."""
    cache = load_json(TRACKS_FILE, {})
    cached = cache.get(release_id)
    # re-fetch only if the cached shape predates the per-song youtube_link
    if cached and all('youtube_link' in t for t in cached):
        return cached

    headers = {'Authorization': f'Bearer {pat}',
               'Content-Type': 'application/json'}
    for attempt in range(retries):
        try:
            r = requests.get(f'https://once.app/v1/releases/{release_id}',
                             headers=headers, timeout=60)
            if r.status_code == 429:
                time.sleep(15 * (attempt + 1))
                continue
            r.raise_for_status()
            tracks = []
            for t in (r.json().get('tracks') or []):
                vid = t.get('ytmusic_video_id')
                tracks.append({
                    'track_number': t.get('track_number') or 0,
                    'song_name': t.get('title') or '',
                    'duration': duration(t.get('duration')),
                    # direct link to this song, from ONCE's per-track video id
                    'youtube_link': (f'https://music.youtube.com/watch?v={vid}'
                                     if vid else ''),
                })
            tracks.sort(key=lambda t: t['track_number'])
            cache[release_id] = tracks
            TRACKS_FILE.parent.mkdir(parents=True, exist_ok=True)
            TRACKS_FILE.write_text(json.dumps(
                cache, indent=1, ensure_ascii=False))
            return tracks
        except Exception as e:
            if attempt == retries - 1:
                print(f'  ⚠️  tracklist failed for {release_id}: {e}')
            else:
                time.sleep(5 * (attempt + 1))
    return []


def scrape_albums():
    """{"normalised title": {"playlist_id": …}} from the public releases page."""
    try:
        r = requests.get(RELEASES_URL, headers={'User-Agent': UA}, timeout=60)
        r.raise_for_status()
    except Exception as e:
        print(f'  ⚠️  could not scrape releases page: {e}')
        return {}

    html = r.text
    found = {}

    def add(title, playlist):
        title = re.sub(r'\\u([0-9a-fA-F]{4})',
                       lambda m: chr(int(m.group(1), 16)), title)
        found[norm(title.replace('&amp;', '&'))] = playlist

    for card in html.split('<ytd-rich-item-renderer')[1:]:
        m = re.search(
            r'title="([^"]+)" href="[^"]*list=(OLAK5uy_[A-Za-z0-9_-]+)', card)
        if m:
            add(m.group(1), m.group(2))

    if not found:
        for chunk in html.split('"playlistRenderer":{')[1:]:
            pid = re.search(r'"playlistId":"(OLAK5uy_[A-Za-z0-9_-]+)"', chunk)
            name = re.search(r'"title":\{"simpleText":"([^"]+)"', chunk) or \
                re.search(r'"title":\{"runs":\[\{"text":"([^"]+)"', chunk)
            if pid and name:
                add(name.group(1), pid.group(1))

    print(f'  📄 releases page: {len(found)} albums')
    return found


# --------------------------------------------------------------------------- #
def main():
    load_env()
    pat = os.getenv('ONCE_PAT')
    if not pat:
        raise SystemExit('ONCE_PAT not found in .env')

    manual = {norm(k): v for k, v in load_json(MANUAL_FILE, {}).items()
              if not k.startswith('_')}
    cache = load_json(CACHE_FILE, {})

    releases = get_releases(pat)
    print(f'{len(releases)} releases on ONCE')

    scraped = scrape_albums()

    albums = []
    for i, rel in enumerate(releases, 1):
        rid, title = rel['id'], rel.get('title', '')
        known = cache.get(rid, {})
        over = manual.get(norm(title), {})

        # Album playlist: manual first, then the scraped page
        album_url = over.get('album_link') or ''
        if not album_url:
            album_url = as_album_url(known.get('youtube_url'))
        if not album_url:
            pid = scraped.get(norm(title))
            album_url = f'https://music.youtube.com/playlist?list={pid}' if pid else ''

        track_url = over.get('youtube_link') or known.get('youtube_url') or ''
        vid = video_id(track_url) or video_id(album_url)
        cover = f'https://i.ytimg.com/vi/{vid}/hqdefault.jpg' if vid else ''

        # song name -> direct track URL, when we already know it
        by_title = {norm(v.get('title')): v.get('youtube_url')
                    for v in cache.values() if v.get('youtube_url')}

        songs = get_tracks(rid, pat)
        # Only fill songs ONCE gave no video id for. Overwriting unconditionally
        # threw away every link get_tracks had just fetched.
        for s in songs:
            if not s.get('youtube_link'):
                s['youtube_link'] = by_title.get(norm(s['song_name']), '')

        print(f'[{i}/{len(releases)}] {title[:44]:44} {len(songs)} song(s)')

        albums.append({
            'album_name': title,
            'date_published': (rel.get('created_at') or '')[:10],
            'youtube_link': album_url or track_url,
            'album_link': album_url,
            'cover_art': cover,
            'songs': songs,
        })

    # Links collected in DJ_Elsa_YouTube_and_YouTube_Music_Links.json are the
    # most reliable we have. Only blanks are filled: anything ONCE or the
    # scrape already supplied keeps priority. Template, per the owner:
    # https://music.youtube.com/watch?v= + youtube_video_id
    dump_file = Path('DJ_Elsa_YouTube_and_YouTube_Music_Links.json')
    if dump_file.exists():
        try:
            dump_links = {}
            for d in json.loads(dump_file.read_text(encoding='utf-8')):
                vid = d.get('youtube_video_id') or ''
                if not vid:
                    continue
                dump_links[(norm(d.get('album_name')),
                            norm(d.get('song_name')))] = (
                    d.get('youtube_music_link')
                    or f'https://music.youtube.com/watch?v={vid}')
            filled = 0
            for a in albums:
                key = norm(a['album_name'])
                for s in a['songs']:
                    if s.get('youtube_link'):
                        continue
                    url = dump_links.get((key, norm(s['song_name'])))
                    if url:
                        s['youtube_link'] = url
                        filled += 1
            print(f'    + {filled} song link(s) filled from the link dump')
        except Exception as e:
            print(f'    ! link dump unreadable: {e}')

    albums.sort(key=lambda a: a['date_published'], reverse=True)

    payload = {
        'generated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'album_count': len(albums),
        'song_count': sum(len(a['songs']) for a in albums),
        'albums': albums,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2,
                   ensure_ascii=False), encoding='utf-8')

    with_album = sum(1 for a in albums if a['album_link'])
    print(f'\n→ {OUT}')
    print(f'  {len(albums)} albums, {payload["song_count"]} songs')
    print(f'  {with_album} with an album playlist link')


if __name__ == '__main__':
    main()

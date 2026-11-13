#!/usr/bin/env python3
"""
FINAL WORKING SOLUTION - Combines ONCE + YouTube APIs properly
"""

import os
import re
import json
import requests
from pathlib import Path
from datetime import datetime
import time


CACHE_FILE = Path('lore/yt_link_cache.json')
MANUAL_FILE = Path('lore/manual_links.json')
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


def get_once_releases():
    """Get all releases from ONCE API"""
    load_env()
    pat = os.getenv('ONCE_PAT')
    if not pat:
        print("❌ ONCE_PAT not found")
        return []

    headers = {
        'Authorization': f'Bearer {pat}',
        'Content-Type': 'application/json'
    }

    all_releases = []
    offset = 0
    limit = 100

    while True:
        try:
            url = f'https://once.app/v1/releases?limit={limit}&offset={offset}'
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()

            if isinstance(data, dict) and 'releases' in data:
                releases = data['releases']
                all_releases.extend(releases)

                if 'nextOffset' in data and data['nextOffset'] is not None:
                    offset = data['nextOffset']
                else:
                    break
            else:
                break

        except Exception as e:
            print(f"Error fetching ONCE releases: {e}")
            break

    return all_releases


def load_cache():
    """yt_link_cache.json: {"<once release id>": {title, youtube_url, cover_art}}"""
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text())
        except Exception:
            return {}
    return {}


def save_cache(cache):
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, indent=1, ensure_ascii=False))


def load_manual():
    """
    lore/manual_links.json — hand-entered links, keyed by album name.

    Highest priority: overrides ONCE and the scrape. Read-only to this script,
    so a sync never clobbers what you typed in.
    """
    if not MANUAL_FILE.exists():
        return {}
    try:
        data = json.loads(MANUAL_FILE.read_text())
    except Exception as e:
        print(f"  ⚠️  manual_links.json unreadable: {e}")
        return {}
    return {norm(k): v for k, v in data.items()
            if not k.startswith('_') and isinstance(v, dict)}


def yt_link_from_once(release_id, pat, retries=4):
    """
    Ask ONCE where the release is live on YouTube Music.

    The release detail endpoint lists every store with a `urlInStore` once the
    track is "Confirmed live" — that is the authoritative link, no YouTube API
    quota involved.
    """
    headers = {'Authorization': f'Bearer {pat}', 'Content-Type': 'application/json'}

    for attempt in range(retries):
        try:
            response = requests.get(
                f'https://once.app/v1/releases/{release_id}/status',
                headers=headers, timeout=30
            )
            if response.status_code == 429:
                wait = 15 * (attempt + 1)
                print(f"  ⏳ ONCE rate limit, waiting {wait}s...")
                time.sleep(wait)
                continue
            response.raise_for_status()
            data = response.json()

            for store in data.get('storeStatuses', []):
                if store.get('storeName') == 'YouTube Music' and store.get('urlInStore'):
                    return store['urlInStore']
            return None

        except Exception as e:
            wait = 5 * (attempt + 1)
            print(f"  ⚠️  ONCE error ({e}), retrying in {wait}s...")
            time.sleep(wait)

    return None


def norm(s):
    """Compare titles ignoring case, punctuation, spacing and zero-width chars."""
    s = (s or '').replace('\u200b', '').replace('\u200c', '').replace('\u200d', '')
    return re.sub(r'[^a-z0-9]', '', s.lower())


def scrape_channel_releases():
    """
    Scrape https://www.youtube.com/@elsavelaz/releases.

    Each album card in the HTML contains:
        title="<album name>" href="/watch?v=<videoId>&amp;list=OLAK5uy_..."

    Returns {"<normalised title>": {"title", "youtube_url", "video_id"}}.
    No API key, no quota — this is what the public page itself renders.
    """
    try:
        response = requests.get(RELEASES_URL, headers={'User-Agent': UA}, timeout=60)
        response.raise_for_status()
    except Exception as e:
        print(f"  ⚠️  could not scrape releases page: {e}")
        return {}

    html = response.text
    found = {}

    @staticmethod
    def _add(title, video_id, playlist):
        # YouTube's JSON escapes &, <, > as \u0026 etc. — decode those too
        title = re.sub(
            r'\\u([0-9a-fA-F]{4})',
            lambda m: chr(int(m.group(1), 16)),
            title,
        ).replace('&amp;', '&')
        found[norm(title)] = {
            'title': title,
            'video_id': video_id,
            'youtube_url': (f'https://music.youtube.com/watch?v={video_id}&list={playlist}'
                            if video_id else
                            f'https://music.youtube.com/playlist?list={playlist}'),
            'playlist_url': f'https://music.youtube.com/playlist?list={playlist}',
        }

    # Shape A — rendered DOM:
    #   title="<album>" href="/watch?v=<id>&amp;list=OLAK5uy_…"
    for card in html.split('<ytd-rich-item-renderer')[1:]:
        m = re.search(
            r'title="([^"]+)" href="(/watch\?v=([A-Za-z0-9_-]{11})[^"]*?list=(OLAK5uy_[A-Za-z0-9_-]+))"',
            card
        )
        if m:
            _add(m.group(1), m.group(3), m.group(4))

    # Shape B — ytInitialData JSON (what a plain requests GET gets):
    #   "playlistRenderer":{"playlistId":"OLAK5uy_…","title":{"simpleText":"…"} …
    if not found:
        for chunk in html.split('"playlistRenderer":{')[1:]:
            pid = re.search(r'"playlistId":"(OLAK5uy_[A-Za-z0-9_-]+)"', chunk)
            name = re.search(r'"title":\{"simpleText":"([^"]+)"', chunk)
            if not name:
                name = re.search(r'"title":\{"runs":\[\{"text":"([^"]+)"', chunk)
            vid = re.search(r'"watchEndpoint":\{"videoId":"([A-Za-z0-9_-]{11})"', chunk)
            if pid and name:
                _add(name.group(1), vid.group(1) if vid else None, pid.group(1))

    print(f"  📄 releases page: {len(found)} albums", flush=True)
    return found


def search_youtube_video(title, api_key):
    """Fallback only: search YouTube when ONCE has no URL. Throttled + retried."""

    url = "https://www.googleapis.com/youtube/v3/search"

    params = {
        'key': api_key,
        'q': f'"{title}" DJ Elsa',
        'part': 'snippet',
        'type': 'video',
        'maxResults': 1,
        'order': 'relevance'
    }

    for attempt in range(3):
        try:
            response = requests.get(url, params=params, timeout=20)

            if response.status_code == 429:
                wait = 20 * (attempt + 1)
                print(f"  ⏳ YouTube quota, waiting {wait}s...")
                time.sleep(wait)
                continue

            response.raise_for_status()
            data = response.json()

            items = data.get('items', [])
            if items:
                video_id = items[0]['id']['videoId']
                return {
                    'video_id': video_id,
                    'thumbnail': f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
                    'url': f"https://music.youtube.com/watch?v={video_id}"
                }
            return None

        except Exception as e:
            if attempt == 2:
                print(f"Error searching YouTube for '{title}': {e}")
            else:
                time.sleep(10 * (attempt + 1))

    return None


def create_album_data(releases, api_key):
    """
    Build one card per ONCE release — ALL of them, whatever their status.

    Link resolution, first hit wins:
      0. lore/manual_links.json          (you typed it — never overwritten)
      1. ONCE store status `urlInStore`  (exact track URL)
      2. scrape @elsavelaz/releases      (exact track + album playlist)
      3. blank + "Coming soon" placeholder (no YouTube API calls, no quota)
    Cover: the YouTube thumbnail for whatever link we ended up with.
    """
    albums = []
    pat = os.getenv('ONCE_PAT')
    cache = load_cache()
    manual = load_manual()

    # Only fetch the public releases page if something is genuinely new.
    # A release already marked `checked` in the cache (see below) was looked
    # for and not found, so we do not re-scrape it on every run.
    def needs_lookup(r):
        if manual.get(norm(r.get('title', ''))):
            return False
        entry = cache.get(r['id'], {})
        if entry.get('youtube_url'):
            return False
        # Already checked and absent — only retry if ONCE status moved on
        return entry.get('checked_status') != r.get('status')

    unresolved = [r for r in releases if needs_lookup(r)]

    if unresolved:
        print(f"{len(unresolved)} release(s) to look up — checking releases page",
              flush=True)
        scraped = scrape_channel_releases()
    else:
        print("all links known or already checked — not scraping", flush=True)
        scraped = {}

    print(f"{len(releases)} releases on ONCE, resolving links...", flush=True)

    for i, release in enumerate(releases):
        rid = release['id']
        title = release.get('title', f'Release {i+1}')
        known = cache.get(rid, {})
        youtube_url = known.get('youtube_url')
        playlist_url = known.get('album_link')

        print(f"[{i+1}/{len(releases)}] {title}", flush=True)

        # 0) hand-entered link wins over everything and is never overwritten
        override = manual.get(norm(title))
        if override:
            youtube_url = override.get('youtube_link') or youtube_url
            playlist_url = override.get('album_link') or playlist_url
            print(f"  ✅ manual: {youtube_url}", flush=True)

        elif not youtube_url:
            # 1) ONCE knows the exact YouTube Music link
            youtube_url = yt_link_from_once(rid, pat)
            if youtube_url:
                print(f"  ✅ ONCE: {youtube_url}", flush=True)

        # 2) scrape the public releases page (by title, exact-normalised)
        hit = scraped.get(norm(title))
        if hit:
            if not youtube_url:
                youtube_url = hit['youtube_url']
                print(f"  ✅ scrape: {youtube_url}", flush=True)
            playlist_url = playlist_url or hit.get('playlist_url')

        video_id = None
        if youtube_url:
            m = re.search(r'[?&]v=([A-Za-z0-9_-]{11})', youtube_url)
            video_id = m.group(1) if m else None

        if not youtube_url:
            print(f"  ⚠️  no YouTube link yet (ONCE status: "
                  f"{release.get('status')})", flush=True)

        # Cover art: the YouTube thumbnail is the one the browser can actually
        # load (ONCE's /api/files cover-art URLs are account-private → 404).
        # Fall back to the ONCE file only when we have no video id.
        cover = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg" if video_id else ''
        if not cover:
            cover = release.get('cover_art_file_url') or ''
            if cover.startswith('/'):
                cover = 'https://once.app' + cover

        if youtube_url:
            cache[rid] = {
                'title': title,
                'youtube_url': youtube_url,
                'album_link': playlist_url,
                'cover_art': cover,
            }
            save_cache(cache)  # write as we go, so a crash keeps progress
        elif rid in {r['id'] for r in unresolved}:
            # Looked for it and it isn't there. Remember the ONCE status we saw
            # so the next run skips it until that status changes (e.g. the
            # release actually goes live).
            cache[rid] = {
                'title': title,
                'youtube_url': None,
                'album_link': None,
                'cover_art': '',
                'checked_status': release.get('status'),
            }
            save_cache(cache)
            print(f"  ⏳ marked checked — not on YouTube yet "
                  f"(ONCE status: {release.get('status')})", flush=True)

        album = {
            'title': title,
            'date': (release.get('created_at') or '')[:10],
            'cover_art': cover,
            'youtube_url': youtube_url or '',
            'album_link': playlist_url or '',
            'genre': release.get('genre', 'Electronic')
        }
        albums.append(album)

        time.sleep(0.2)

    return albums


def create_html(albums):
    """Create the final HTML"""

    html = '''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DJ Elsa - Music Archive</title>
  <style>
    body { background: #0a0c08; color: #f5f6f0; font-family: Arial, sans-serif; margin: 0; padding: 20px; }
    .container { max-width: 1200px; margin: 0 auto; }
    .header { text-align: center; margin-bottom: 40px; }
    .header h1 { color: #b8ff43; font-size: 3rem; margin: 0; }
    .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 20px; }
    .album { background: #141912; border: 1px solid #303a2d; border-radius: 10px; overflow: hidden; transition: transform 0.2s; }
    .album:hover { transform: translateY(-2px); }
    .album img { width: 100%; height: 200px; object-fit: cover; }
    .album-info { padding: 15px; }
    .album-title { font-size: 1.1rem; font-weight: bold; margin: 0 0 10px 0; }
    .album-link { display: inline-block; background: #b8ff43; color: #131a0c; padding: 8px 16px; text-decoration: none; border-radius: 5px; font-weight: bold; }
    .album-link:hover { filter: brightness(1.1); }
    .album-link.pending { background: #303a2d; color: #aeb8a7; }
    .count { text-align: center; color: #aeb8a7; margin-bottom: 20px; }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>DJ Elsa</h1>
      <p>Music Archive</p>
    </div>
    <div class="count">''' + str(len(albums)) + ''' albums</div>
    <div class="grid">
'''

    for album in albums:
        # ONCE cover-art URLs are account-private (404 for a browser), so only
        # use a cover we know is publicly loadable.
        cover = album['cover_art'] if 'ytimg' in album['cover_art'] else ''
        if not cover:
            cover = (f"https://dummyimage.com/300x300/1a2b1a/b8ff43"
                     f"&text={album['title'].replace(' ', '+')[:15]}")

        if album['youtube_url']:
            link = (f'<a href="{album["youtube_url"]}" target="_blank" '
                    f'class="album-link">Listen on YouTube Music</a>')
        else:
            link = '<span class="album-link pending">Coming soon</span>'

        html += f'''      <div class="album">
        <img src="{cover}" alt="{album['title']}" loading="lazy">
        <div class="album-info">
          <h3 class="album-title">{album['title']}</h3>
          {link}
        </div>
      </div>
'''

    html += '''    </div>
  </div>
</body>
</html>'''

    return html


def main():
    print("🎵 DJ Elsa - FINAL WORKING SYNC")
    print("===============================")
    print()

    load_env()

    # API_KEY is optional. Link resolution no longer touches the YouTube Data
    # API (manual override -> ONCE -> releases page), so the script runs fine
    # without it. Kept only so nothing breaks if it is set.
    api_key = os.getenv('API_KEY')
    if not api_key:
        print("ℹ️  no API_KEY set — running without it (not needed)")

    # Get ONCE releases
    releases = get_once_releases()
    print(f"Fetched {len(releases)} releases from ONCE", flush=True)

    if not releases:
        print("❌ No releases found")
        return

    # Create album data with real YouTube thumbnails
    albums = create_album_data(releases, api_key)

    # Create HTML
    html = create_html(albums)
    Path('kissingface.html').write_text(html)

    # Create lore/songs.json — slim, one row per release
    songs = [
        {
            'song_name': a['title'],
            'date_published': a['date'],
            'album_name': a['title'],
            'youtube_link': a['youtube_url'],
            'album_link': a['album_link'],
            'cover_art': a['cover_art'],
        }
        for a in albums
    ]
    out = Path('lore/songs.json')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(songs, indent=2, ensure_ascii=False), encoding='utf-8')

    with_link = sum(1 for s in songs if s['youtube_link'])
    with_cover = sum(1 for s in songs if s['cover_art'])
    print(f"\n🎉 DONE!")
    print(f"✅ kissingface.html: {len(albums)} album cards")
    print(f"✅ lore/songs.json: {len(songs)} rows")
    print(f"   {with_link} with a YouTube link, {len(songs) - with_link} still blank")
    print(f"   {with_cover} with cover art")


if __name__ == "__main__":
    main()

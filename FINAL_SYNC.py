#!/usr/bin/env python3
"""
FINAL WORKING SOLUTION - Combines ONCE + YouTube APIs properly
"""

import os
import requests
from pathlib import Path
from datetime import datetime
import time


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


def search_youtube_video(title, api_key):
    """Search for a specific video on YouTube"""

    url = "https://www.googleapis.com/youtube/v3/search"

    params = {
        'key': api_key,
        'q': f'"{title}" DJ Elsa',
        'part': 'snippet',
        'type': 'video',
        'maxResults': 1,
        'order': 'relevance'
    }

    try:
        response = requests.get(url, params=params, timeout=10)
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
    except Exception as e:
        print(f"Error searching YouTube for '{title}': {e}")

    return None


def create_album_data(releases, api_key):
    """Create album data with real YouTube thumbnails"""
    albums = []

    for i, release in enumerate(releases):
        if release.get('status') not in ['submitted', 'distributed', 'live']:
            continue

        title = release.get('title', f'Release {i+1}')

        print(f"Processing {i+1}/{len(releases)}: {title}")

        # Search for the actual YouTube video
        youtube_info = search_youtube_video(title, api_key)

        if youtube_info:
            cover_art = youtube_info['thumbnail']
            youtube_url = youtube_info['url']
            print(f"  ✅ Found: {youtube_info['video_id']}")
        else:
            # Fallback to placeholder
            cover_art = f"https://dummyimage.com/300x300/1a2b1a/b8ff43&text={title.replace(' ', '+')[:15]}"
            youtube_url = f"https://music.youtube.com/search?q={title.replace(' ', '+')}+DJ+Elsa"
            print(f"  ❌ Not found, using placeholder")

        album = {
            'title': title,
            'date': release.get('created_at', '')[:10] if release.get('created_at') else datetime.now().strftime('%Y-%m-%d'),
            'cover_art': cover_art,
            'youtube_url': youtube_url,
            'genre': release.get('genre', 'Electronic')
        }
        albums.append(album)

        # Rate limiting
        time.sleep(0.5)

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
        html += f'''      <div class="album">
        <img src="{album['cover_art']}" alt="{album['title']}" loading="lazy">
        <div class="album-info">
          <h3 class="album-title">{album['title']}</h3>
          <a href="{album['youtube_url']}" target="_blank" class="album-link">Listen on YouTube Music</a>
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
    print("This will take a few minutes due to YouTube API rate limits...")
    print()

    load_env()

    # Get API keys
    api_key = os.getenv('API_KEY')
    if not api_key:
        print("❌ API_KEY not found in .env")
        return

    # Get ONCE releases
    releases = get_once_releases()
    print(f"Fetched {len(releases)} releases from ONCE")

    if not releases:
        print("❌ No releases found")
        return

    # Create album data with real YouTube thumbnails
    albums = create_album_data(releases, api_key)

    # Create HTML
    html = create_html(albums)
    Path('kissingface.html').write_text(html)

    print(f"\n🎉 DONE!")
    print(f"✅ Created kissingface.html with {len(albums)} albums")
    print("✅ Real YouTube thumbnails (where found)")
    print("✅ Direct YouTube Music links")
    print("✅ Only YOUR albums from ONCE")


if __name__ == "__main__":
    main()

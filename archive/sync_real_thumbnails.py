#!/usr/bin/env python3
"""
Sync with real YouTube thumbnails by scraping YouTube search results
"""

import os
import json
import re
import requests
from pathlib import Path
from datetime import datetime
from urllib.parse import quote
import time


def load_env():
    if os.path.exists('.env'):
        with open('.env') as f:
            for line in f:
                if line.strip() and not line.startswith('#'):
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value


def fetch_releases():
    """Fetch all releases from ONCE API"""
    load_env()
    pat = os.getenv('ONCE_PAT')
    if not pat:
        print("❌ ONCE_PAT not found in .env")
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
            print(f"Error fetching releases: {e}")
            break

    return all_releases


def scrape_youtube_thumbnail(title, artist="DJ Elsa"):
    """Scrape YouTube search results to get real thumbnail"""
    try:
        # Search YouTube for the album
        query = f"{title} {artist}"
        search_url = f"https://www.youtube.com/results?search_query={quote(query)}"

        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

        print(f"Searching YouTube for: {title}")
        response = requests.get(search_url, headers=headers, timeout=10)
        response.raise_for_status()

        # Look for video IDs in the HTML
        video_ids = re.findall(r'"videoId":"([^"]+)"', response.text)

        if video_ids:
            # Use the first video ID found
            video_id = video_ids[0]
            thumbnail_url = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
            youtube_url = f"https://music.youtube.com/watch?v={video_id}"

            print(f"Found thumbnail: {thumbnail_url}")
            return {
                'thumbnail': thumbnail_url,
                'url': youtube_url
            }
        else:
            print(f"No video found for: {title}")
            return None

    except Exception as e:
        print(f"Error scraping YouTube for {title}: {e}")
        return None


def create_album_data(releases):
    """Create album data with real YouTube thumbnails"""
    albums = []

    for i, release in enumerate(releases):
        # Only include submitted/distributed releases
        if release.get('status') not in ['submitted', 'distributed', 'live']:
            continue

        title = release.get('title', f'Release {i+1}')

        # Try to scrape YouTube thumbnail
        youtube_info = scrape_youtube_thumbnail(title)

        if youtube_info:
            cover_art = youtube_info['thumbnail']
            youtube_url = youtube_info['url']
        else:
            # Fallback to a music-themed placeholder
            safe_title = title.replace(' ', '+')[:15]
            cover_art = f"https://dummyimage.com/300x300/1a2b1a/b8ff43&text=♪+{safe_title}"
            youtube_url = f"https://music.youtube.com/search?q={quote(title + ' DJ Elsa')}"

        album = {
            'title': title,
            'date': release.get('created_at', '')[:10] if release.get('created_at') else datetime.now().strftime('%Y-%m-%d'),
            'cover_art': cover_art,
            'youtube_url': youtube_url,
            'once_id': release.get('id', ''),
            'status': release.get('status', ''),
            'artist': release.get('primary_artist_name', 'DJ Elsa'),
            'genre': release.get('genre', 'Electronic')
        }
        albums.append(album)

        # Add delay to avoid rate limiting
        time.sleep(1)

    return albums


def update_kissingface(albums):
    """Update kissingface.html with real YouTube thumbnails"""

    # Read the current template
    template_path = Path('kissingface_template.html')
    if not template_path.exists():
        print('Creating template from current kissingface.html...')
        content = Path('kissingface.html').read_text()
        template = re.sub(
            r'const albums=\[.*?\];',
            'const albums={{ALBUMS_PLACEHOLDER}};',
            content,
            flags=re.DOTALL
        )
        template_path.write_text(template)

    template = template_path.read_text()

    # Format albums as JavaScript
    js_albums = '[\n'
    for i, album in enumerate(albums):
        js_albums += f'      {{title:"{album["title"]}",date:"{album["date"]}",cover_art:"{album["cover_art"]}",genre:"{album["genre"]}",youtube_url:"{album["youtube_url"]}"}}'
        if i < len(albums) - 1:
            js_albums += ','
        js_albums += '\n'
    js_albums += '    ]'

    # Replace placeholder
    new_content = template.replace('{{ALBUMS_PLACEHOLDER}}', js_albums)

    # Write updated file
    Path('kissingface.html').write_text(new_content)
    print(f'✅ Updated kissingface.html with {len(albums)} albums')


if __name__ == "__main__":
    print("🎵 ONCE Release Sync - Real YouTube Thumbnails")
    print("=============================================")
    print("⚠️  This will scrape YouTube for real thumbnails")
    print("⚠️  It may take a few minutes due to rate limiting")
    print()

    # Fetch all releases
    releases = fetch_releases()
    print(f"Fetched {len(releases)} releases from ONCE")

    if not releases:
        print("❌ No releases found")
        exit(1)

    # Create album data with real thumbnails
    albums = create_album_data(releases)
    print(f"Processed {len(albums)} albums for display")

    # Update HTML
    update_kissingface(albums)

    print("\n🎉 Sync complete!")
    print("✅ Scraped real YouTube thumbnails")
    print("✅ Direct YouTube Music links")
    print("💡 Check your site - it should now show real album artwork!")

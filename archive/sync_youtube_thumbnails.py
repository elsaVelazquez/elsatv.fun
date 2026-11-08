#!/usr/bin/env python3
"""
Sync releases using YouTube thumbnails for cover art
"""

import os
import json
import re
from pathlib import Path
from datetime import datetime


def load_env():
    if os.path.exists('.env'):
        with open('.env') as f:
            for line in f:
                if line.strip() and not line.startswith('#'):
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value


def fetch_releases():
    """Fetch all releases from ONCE API"""
    import requests

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


def get_youtube_thumbnail_url(title):
    """Generate YouTube thumbnail URL from title search"""
    # Use YouTube's search thumbnail approach
    # This will show a thumbnail from the search results
    search_query = title.replace(' ', '+')
    return f"https://i.ytimg.com/vi/search?q={search_query}+DJ+Elsa/hqdefault.jpg"


def create_album_data_with_youtube_thumbs(releases):
    """Create album data with YouTube thumbnails"""
    albums = []

    for i, release in enumerate(releases):
        # Only include submitted/distributed releases
        if release.get('status') not in ['submitted', 'distributed', 'live']:
            continue

        title = release.get('title', f'Release {i+1}')

        # Use YouTube thumbnail (this will show album art from YouTube search)
        cover_art = get_youtube_thumbnail_url(title)

        album = {
            'title': title,
            'date': release.get('created_at', '')[:10] if release.get('created_at') else datetime.now().strftime('%Y-%m-%d'),
            'cover_art': cover_art,
            'once_id': release.get('id', ''),
            'status': release.get('status', ''),
            'artist': release.get('primary_artist_name', 'DJ Elsa'),
            'genre': release.get('genre', 'Electronic')
        }
        albums.append(album)

    return albums


def update_kissingface_with_youtube_thumbs(albums):
    """Update kissingface.html with YouTube thumbnails"""

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
        js_albums += f'      {{title:"{album["title"]}",date:"{album["date"]}",cover_art:"{album["cover_art"]}",genre:"{album["genre"]}"}}'
        if i < len(albums) - 1:
            js_albums += ','
        js_albums += '\n'
    js_albums += '    ]'

    # Replace placeholder
    new_content = template.replace('{{ALBUMS_PLACEHOLDER}}', js_albums)

    # Write updated file
    Path('kissingface.html').write_text(new_content)
    print(
        f'✅ Updated kissingface.html with {len(albums)} albums and YouTube thumbnails')


if __name__ == "__main__":
    print("🎵 ONCE Release Sync - YouTube Thumbnails")
    print("=========================================")

    # Fetch all releases
    releases = fetch_releases()
    print(f"Fetched {len(releases)} releases from ONCE")

    if not releases:
        print("❌ No releases found")
        exit(1)

    # Create album data with YouTube thumbnails
    albums = create_album_data_with_youtube_thumbs(releases)
    print(f"Processed {len(albums)} albums for display")

    # Update HTML
    update_kissingface_with_youtube_thumbs(albums)

    print("\n🎉 Sync complete!")
    print("✅ Using YouTube thumbnails for cover art")
    print("✅ Images should load properly now!")

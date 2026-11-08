#!/usr/bin/env python3
"""
Download cover art from ONCE and serve locally
"""

import os
import json
import re
import requests
from pathlib import Path
from datetime import datetime
from urllib.parse import quote


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


def download_cover_art(url, title, pat):
    """Download cover art with authentication"""
    if not url:
        return None

    try:
        # Create covers directory
        covers_dir = Path('covers')
        covers_dir.mkdir(exist_ok=True)

        # Generate safe filename
        safe_title = re.sub(r'[^\w\s-]', '', title)[:30]
        filename = f"{safe_title.replace(' ', '_')}.jpg"
        filepath = covers_dir / filename

        # Skip if already exists
        if filepath.exists():
            return f"covers/{filename}"

        # Download with authentication
        headers = {
            'Authorization': f'Bearer {pat}',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }

        print(f"Downloading: {title}")
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()

        # Check if it's actually an image
        content_type = response.headers.get('content-type', '')
        if not content_type.startswith('image/'):
            print(f"Warning: {title} returned {content_type}, not an image")
            return None

        # Save the image
        filepath.write_bytes(response.content)
        print(f"Saved: covers/{filename}")
        return f"covers/{filename}"

    except Exception as e:
        print(f"Error downloading {title}: {e}")
        return None


def create_album_data(releases):
    """Create album data with downloaded cover art"""
    load_env()
    pat = os.getenv('ONCE_PAT')

    albums = []

    for i, release in enumerate(releases):
        # Only include submitted/distributed releases
        if release.get('status') not in ['submitted', 'distributed', 'live']:
            continue

        title = release.get('title', f'Release {i+1}')

        # Get cover art URL from ONCE
        cover_art_url = release.get('cover_art_file_url', '')
        if cover_art_url and not cover_art_url.startswith('http'):
            cover_art_url = f"https://once.app{cover_art_url}"

        # Try to download cover art
        local_cover = download_cover_art(cover_art_url, title, pat)

        # Use local cover if downloaded, otherwise use placeholder
        if local_cover:
            cover_art = local_cover
        else:
            # Use a music-themed placeholder
            safe_title = title.replace(' ', '+')[:15]
            cover_art = f"https://dummyimage.com/300x300/1a2b1a/b8ff43&text={safe_title}"

        # Create YouTube Music search URL
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

    return albums


def update_kissingface(albums):
    """Update kissingface.html with downloaded cover art"""

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
    print("🎵 ONCE Release Sync - Download Cover Art")
    print("=========================================")

    # Fetch all releases
    releases = fetch_releases()
    print(f"Fetched {len(releases)} releases from ONCE")

    if not releases:
        print("❌ No releases found")
        exit(1)

    # Create album data with downloaded covers
    albums = create_album_data(releases)
    print(f"Processed {len(albums)} albums for display")

    # Update HTML
    update_kissingface(albums)

    print("\n🎉 Sync complete!")
    print("✅ Downloaded cover art to 'covers/' directory")
    print("✅ Your site now uses local images!")

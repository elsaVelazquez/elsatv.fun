#!/usr/bin/env python3
"""
Sync releases and download cover art locally
"""

import os
import json
import re
import requests
from pathlib import Path
from datetime import datetime
import hashlib


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


def download_cover_art(url, title):
    """Download cover art locally and return local path"""
    if not url:
        return None

    try:
        # Create covers directory
        covers_dir = Path('covers')
        covers_dir.mkdir(exist_ok=True)

        # Generate filename from title
        safe_title = re.sub(r'[^\w\s-]', '', title)[:50]
        filename = f"{safe_title.replace(' ', '_')}.png"
        filepath = covers_dir / filename

        # Skip if already downloaded
        if filepath.exists():
            return f"covers/{filename}"

        # Download the image
        print(f"Downloading cover art for: {title}")
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        # Save the image
        filepath.write_bytes(response.content)
        return f"covers/{filename}"

    except Exception as e:
        print(f"Error downloading cover art for {title}: {e}")
        return None


def create_album_data_with_local_covers(releases):
    """Create album data with local cover art"""
    albums = []

    for i, release in enumerate(releases):
        # Only include submitted/distributed releases
        if release.get('status') not in ['submitted', 'distributed', 'live']:
            continue

        # Get cover art URL from ONCE
        cover_art_url = release.get('cover_art_file_url', '')
        if cover_art_url and not cover_art_url.startswith('http'):
            cover_art_url = f"https://once.app{cover_art_url}"

        # Download cover art locally
        local_cover = download_cover_art(
            cover_art_url, release.get('title', f'Release {i+1}'))

        # Use local cover if downloaded, otherwise use placeholder
        if local_cover:
            cover_art = local_cover
        else:
            # Create a simple placeholder
            title = release.get('title', f'Release {i+1}')
            cover_art = f"https://via.placeholder.com/300x300/1a2b1a/b8ff43?text={title.replace(' ', '+')[:15]}"

        album = {
            'title': release.get('title', f'Release {i+1}'),
            'date': release.get('created_at', '')[:10] if release.get('created_at') else datetime.now().strftime('%Y-%m-%d'),
            'cover_art': cover_art,
            'once_id': release.get('id', ''),
            'status': release.get('status', ''),
            'artist': release.get('primary_artist_name', 'DJ Elsa'),
            'genre': release.get('genre', 'Electronic')
        }
        albums.append(album)

    return albums


def update_kissingface_with_local_covers(albums):
    """Update kissingface.html with local cover art"""

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
        f'✅ Updated kissingface.html with {len(albums)} albums and local cover art')


if __name__ == "__main__":
    print("🎵 ONCE Release Sync - Local Cover Art")
    print("=====================================")

    # Fetch all releases
    releases = fetch_releases()
    print(f"Fetched {len(releases)} releases from ONCE")

    if not releases:
        print("❌ No releases found")
        exit(1)

    # Create album data with local covers
    albums = create_album_data_with_local_covers(releases)
    print(f"Processed {len(albums)} albums for display")

    # Update HTML
    update_kissingface_with_local_covers(albums)

    print("\n🎉 Sync complete!")
    print("✅ Cover art downloaded to 'covers/' directory")
    print("✅ Your site now uses local images that always work!")

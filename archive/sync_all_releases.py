#!/usr/bin/env python3
"""
Sync all releases from ONCE to kissingface.html
Since ONCE API doesn't provide YouTube video IDs, we'll create a template
that you can manually update with YouTube links
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


def create_album_template(releases):
    """Create album template with placeholder YouTube data"""
    albums = []

    for i, release in enumerate(releases):
        # Only include submitted/distributed releases
        if release.get('status') not in ['submitted', 'distributed', 'live']:
            continue

        album = {
            'title': release.get('title', f'Release {i+1}'),
            'date': release.get('created_at', '')[:10] if release.get('created_at') else datetime.now().strftime('%Y-%m-%d'),
            'video': 'PLACEHOLDER_VIDEO_ID',  # You'll need to add these manually
            'list': 'PLACEHOLDER_PLAYLIST_ID',  # You'll need to add these manually
            'once_id': release.get('id', ''),
            'status': release.get('status', ''),
            'artist': release.get('primary_artist_name', 'DJ Elsa')
        }
        albums.append(album)

    return albums


def update_kissingface(albums):
    """Update kissingface.html with album data"""

    # Create template if it doesn't exist
    template_path = Path('kissingface_template.html')
    if not template_path.exists():
        print('Creating template from kissingface.html...')
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
        js_albums += f'      {{title:"{album["title"]}",date:"{album["date"]}",video:"{album["video"]}",list:"{album["list"]}"}}'
        if i < len(albums) - 1:
            js_albums += ','
        js_albums += '\n'
    js_albums += '    ]'

    # Replace placeholder
    new_content = template.replace('{{ALBUMS_PLACEHOLDER}}', js_albums)

    # Write updated file
    Path('kissingface.html').write_text(new_content)
    print(f'✅ Updated kissingface.html with {len(albums)} albums')


def create_youtube_mapping_guide(albums):
    """Create a guide to help you map YouTube IDs"""
    guide = """# YouTube ID Mapping Guide

Your kissingface.html has been updated with all {} releases, but you'll need to add YouTube video IDs and playlist IDs manually.

## How to Find YouTube IDs:

1. Go to your YouTube releases: https://youtube.com/elsavelaz/releases
2. For each album:
   - Click on the album
   - The video ID is in the URL: `https://www.youtube.com/watch?v=VIDEO_ID_HERE`
   - The playlist ID is in the URL: `https://music.youtube.com/playlist?list=PLAYLIST_ID_HERE`

## Albums to Update:

""".format(len(albums))

    for i, album in enumerate(albums, 1):
        guide += f"{i}. **{album['title']}**\n"
        guide += f"   - Date: {album['date']}\n"
        guide += f"   - Status: {album['status']}\n"
        guide += f"   - Video ID: `PLACEHOLDER_VIDEO_ID` → Replace with actual ID\n"
        guide += f"   - Playlist ID: `PLACEHOLDER_PLAYLIST_ID` → Replace with actual ID\n\n"

    guide += """
## Next Steps:

1. Replace all PLACEHOLDER_VIDEO_ID and PLACEHOLDER_PLAYLIST_ID in kissingface.html
2. Or use the YouTube Data API to automatically fetch these IDs
3. Set up webhooks to get notified when new releases are ready

## Need Help?

The ONCE API doesn't provide YouTube video IDs directly. You have 3 options:
1. Manual update (easiest for 74 releases)
2. YouTube Data API integration (requires additional setup)
3. Webhook + manual mapping (hybrid approach)
"""

    Path('youtube_mapping_guide.md').write_text(guide)
    print(f'📄 Created youtube_mapping_guide.md')


if __name__ == "__main__":
    print("🎵 ONCE Release Sync - All Releases")
    print("===================================")

    # Fetch all releases
    releases = fetch_releases()
    print(f"Fetched {len(releases)} releases from ONCE")

    if not releases:
        print("❌ No releases found")
        exit(1)

    # Create album template
    albums = create_album_template(releases)
    print(f"Processed {len(albums)} albums for display")

    # Update HTML
    update_kissingface(albums)

    # Create mapping guide
    create_youtube_mapping_guide(albums)

    print("\n🎉 Sync complete!")
    print("\n📋 Next steps:")
    print("1. Check youtube_mapping_guide.md for YouTube ID mapping")
    print("2. Update kissingface.html with actual YouTube IDs")
    print("3. Your site will show all {} releases!".format(len(albums)))

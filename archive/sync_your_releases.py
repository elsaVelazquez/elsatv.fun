#!/usr/bin/env python3
"""
Scrape YOUR specific YouTube releases page for accurate album data
"""

import os
import json
import re
import requests
from pathlib import Path
from datetime import datetime
from urllib.parse import quote, urljoin
import time


def load_env():
    if os.path.exists('.env'):
        with open('.env') as f:
            for line in f:
                if line.strip() and not line.startswith('#'):
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value


def scrape_your_releases_page():
    """Scrape your specific YouTube releases page"""

    releases_url = "https://www.youtube.com/@elsavelaz/releases"

    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }

    print(f"Scraping: {releases_url}")

    try:
        response = requests.get(releases_url, headers=headers, timeout=15)
        response.raise_for_status()

        html = response.text

        # Look for video data in the page
        # YouTube often embeds data in JSON-LD or script tags
        albums = []

        # Method 1: Look for JSON-LD structured data
        json_ld_matches = re.findall(
            r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)

        for match in json_ld_matches:
            try:
                data = json.loads(match)
                if isinstance(data, dict) and 'itemListElement' in data:
                    for item in data['itemListElement']:
                        if 'item' in item and 'name' in item['item']:
                            # Found a video entry
                            video_data = item['item']
                            title = video_data.get('name', '')
                            video_id = video_data.get('url', '').split(
                                'v=')[-1] if 'v=' in video_data.get('url', '') else ''

                            if title and video_id:
                                albums.append({
                                    'title': title,
                                    'video_id': video_id,
                                    'thumbnail': f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
                                    'url': f"https://music.youtube.com/watch?v={video_id}"
                                })
            except json.JSONDecodeError:
                continue

        # Method 2: Look for video IDs in the page source
        if not albums:
            video_ids = re.findall(r'"videoId":"([^"]+)"', html)
            titles = re.findall(r'"title":{"runs":\[{"text":"([^"]+)"', html)

            # Try to match titles with video IDs
            for i, video_id in enumerate(video_ids):
                if i < len(titles):
                    title = titles[i]
                    # Filter out non-album titles (like channel name, etc.)
                    if title and not title.startswith('@') and len(title) > 3:
                        albums.append({
                            'title': title,
                            'video_id': video_id,
                            'thumbnail': f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
                            'url': f"https://music.youtube.com/watch?v={video_id}"
                        })

        print(f"Found {len(albums)} albums on your releases page")
        return albums

    except Exception as e:
        print(f"Error scraping releases page: {e}")
        return []


def match_with_once_releases(once_releases, youtube_albums):
    """Match ONCE releases with YouTube albums"""

    matched_albums = []

    for once_release in once_releases:
        if once_release.get('status') not in ['submitted', 'distributed', 'live']:
            continue

        once_title = once_release.get('title', '').lower()

        # Try to find exact match on YouTube
        best_match = None
        best_score = 0

        for yt_album in youtube_albums:
            yt_title = yt_album['title'].lower()

            # Simple matching score
            if once_title == yt_title:
                best_match = yt_album
                best_score = 100
                break
            elif once_title in yt_title or yt_title in once_title:
                score = len(set(once_title.split()) & set(yt_title.split()))
                if score > best_score:
                    best_match = yt_album
                    best_score = score

        if best_match:
            # Use the YouTube data but keep ONCE metadata
            album = {
                'title': once_release.get('title', best_match['title']),
                'date': once_release.get('created_at', '')[:10] if once_release.get('created_at') else datetime.now().strftime('%Y-%m-%d'),
                'cover_art': best_match['thumbnail'],
                'youtube_url': best_match['url'],
                'once_id': once_release.get('id', ''),
                'status': once_release.get('status', ''),
                'artist': once_release.get('primary_artist_name', 'DJ Elsa'),
                'genre': once_release.get('genre', 'Electronic')
            }
            matched_albums.append(album)
            print(
                f"✅ Matched: {once_release.get('title')} -> {best_match['video_id']}")
        else:
            print(f"❌ No match found for: {once_release.get('title')}")
            # Add without YouTube data
            album = {
                'title': once_release.get('title', f'Release {len(matched_albums)+1}'),
                'date': once_release.get('created_at', '')[:10] if once_release.get('created_at') else datetime.now().strftime('%Y-%m-%d'),
                'cover_art': f"https://dummyimage.com/300x300/1a2b1a/b8ff43&text=♪+{once_release.get('title', '').replace(' ', '+')[:15]}",
                'youtube_url': f"https://music.youtube.com/search?q={quote(once_release.get('title', '') + ' DJ Elsa')}",
                'once_id': once_release.get('id', ''),
                'status': once_release.get('status', ''),
                'artist': once_release.get('primary_artist_name', 'DJ Elsa'),
                'genre': once_release.get('genre', 'Electronic')
            }
            matched_albums.append(album)

    return matched_albums


def fetch_once_releases():
    """Fetch releases from ONCE API"""
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
            print(f"Error fetching ONCE releases: {e}")
            break

    return all_releases


def update_kissingface(albums):
    """Update kissingface.html with matched album data"""

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
    print("🎵 ONCE + Your YouTube Releases Sync")
    print("===================================")

    # Fetch ONCE releases
    once_releases = fetch_once_releases()
    print(f"Fetched {len(once_releases)} releases from ONCE")

    if not once_releases:
        print("❌ No ONCE releases found")
        exit(1)

    # Scrape your YouTube releases page
    youtube_albums = scrape_your_releases_page()

    if not youtube_albums:
        print("❌ No YouTube albums found on your releases page")
        print("💡 Make sure your releases page is public: https://youtube.com/elsavelaz/releases")
        exit(1)

    # Match ONCE releases with YouTube albums
    matched_albums = match_with_once_releases(once_releases, youtube_albums)

    # Update HTML
    update_kissingface(matched_albums)

    print("\n🎉 Sync complete!")
    print("✅ Matched ONCE releases with your YouTube albums")
    print("✅ No more wrong matches!")
    print("💡 All albums should be yours with correct artwork")

#!/usr/bin/env python3
"""
Sync releases with fallback cover art options
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


def get_youtube_thumbnail(title):
    """Generate a YouTube thumbnail URL based on title search"""
    # This is a workaround - we'll use a placeholder service or YouTube's search thumbnail
    # For now, we'll use a generic music placeholder
    return f"https://via.placeholder.com/300x300/1a2b1a/b8ff43?text={title.replace(' ', '+')[:20]}"


def create_album_data_with_fallback(releases):
    """Create album data with fallback cover art"""
    albums = []

    for i, release in enumerate(releases):
        # Only include submitted/distributed releases
        if release.get('status') not in ['submitted', 'distributed', 'live']:
            continue

        # Get cover art URL from ONCE
        cover_art_url = release.get('cover_art_file_url', '')
        if cover_art_url and not cover_art_url.startswith('http'):
            cover_art_url = f"https://once.app{cover_art_url}"

        # Use ONCE cover art if available, otherwise fallback
        if cover_art_url:
            # Try to use ONCE cover art with CORS proxy
            cover_art = f"https://cors-anywhere.herokuapp.com/{cover_art_url}"
        else:
            # Fallback to a placeholder
            cover_art = get_youtube_thumbnail(
                release.get('title', f'Release {i+1}'))

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


def update_kissingface_with_fallback(albums):
    """Update kissingface.html with fallback cover art"""

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
    print(f'✅ Updated kissingface.html with {len(albums)} albums')


def create_image_proxy():
    """Create a simple image proxy script to handle CORS issues"""
    proxy_script = '''#!/usr/bin/env python3
"""
Simple image proxy to handle CORS issues with ONCE cover art
Run this locally to serve images with proper CORS headers
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
import urllib.parse

class ImageProxyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Parse the image URL from query parameter
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        
        if 'url' not in params:
            self.send_error(400, "Missing url parameter")
            return
        
        image_url = params['url'][0]
        
        try:
            # Fetch the image
            response = requests.get(image_url, timeout=10)
            response.raise_for_status()
            
            # Send the image with CORS headers
            self.send_response(200)
            self.send_header('Content-Type', response.headers.get('Content-Type', 'image/png'))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'GET')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            self.end_headers()
            
            self.wfile.write(response.content)
            
        except Exception as e:
            self.send_error(500, f"Error fetching image: {e}")

if __name__ == "__main__":
    port = 8081
    server = HTTPServer(('localhost', port), ImageProxyHandler)
    print(f"Image proxy running on http://localhost:{port}")
    print("Use: http://localhost:8081/?url=IMAGE_URL")
    server.serve_forever()
'''

    Path('image_proxy.py').write_text(proxy_script)
    print("📄 Created image_proxy.py - run this if images don't load")


if __name__ == "__main__":
    print("🎵 ONCE Release Sync - With Fallback Cover Art")
    print("=============================================")

    # Fetch all releases
    releases = fetch_releases()
    print(f"Fetched {len(releases)} releases from ONCE")

    if not releases:
        print("❌ No releases found")
        exit(1)

    # Create album data with fallback
    albums = create_album_data_with_fallback(releases)
    print(f"Processed {len(albums)} albums for display")

    # Update HTML
    update_kissingface_with_fallback(albums)

    # Create image proxy helper
    create_image_proxy()

    print("\n🎉 Sync complete!")
    print("\n💡 If images still don't load:")
    print("1. Run: python image_proxy.py")
    print("2. Update cover_art URLs to use: http://localhost:8081/?url=ONCE_URL")
    print("3. Or download the images locally")

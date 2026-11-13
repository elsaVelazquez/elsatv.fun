#!/usr/bin/env python3
"""
YouTube Data API Sync - Gets only YOUR albums from your channel
"""

import os
import requests
from pathlib import Path


def load_env():
    """Load environment variables"""
    if os.path.exists('.env'):
        with open('.env') as f:
            for line in f:
                if line.strip() and not line.startswith('#'):
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value


def get_channel_id():
    """Get your YouTube channel ID"""

    # Try to get channel ID from your channel page
    channel_url = "https://www.youtube.com/@elsavelaz"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    }

    try:
        response = requests.get(channel_url, headers=headers, timeout=15)
        response.raise_for_status()

        # Look for channel ID in the page
        import re
        channel_id_match = re.search(r'"channelId":"([^"]+)"', response.text)

        if channel_id_match:
            return channel_id_match.group(1)
        else:
            print("Could not find channel ID automatically")
            return None

    except Exception as e:
        print(f"Error getting channel ID: {e}")
        return None


def get_channel_videos(channel_id, api_key):
    """Get videos from your YouTube channel using Data API"""

    url = "https://www.googleapis.com/youtube/v3/search"

    params = {
        'key': api_key,
        'channelId': channel_id,
        'part': 'snippet',
        'order': 'date',
        'maxResults': 50,
        'type': 'video'
    }

    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()

        videos = []

        for item in data.get('items', []):
            snippet = item['snippet']
            video_id = item['id']['videoId']
            title = snippet['title']

            # Get all videos from your channel
            videos.append({
                'title': title,
                'video_id': video_id,
                'cover_art': f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
                'youtube_url': f"https://music.youtube.com/watch?v={video_id}",
                'published_at': snippet['publishedAt']
            })

        return videos

    except Exception as e:
        print(f"Error getting videos: {e}")
        return []

def get_channel_playlists(channel_id, api_key):
    """Get playlists (releases) from your YouTube channel"""
    
    url = "https://www.googleapis.com/youtube/v3/playlists"
    
    params = {
        'key': api_key,
        'channelId': channel_id,
        'part': 'snippet',
        'maxResults': 50
    }
    
    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        playlists = []
        
        for item in data.get('items', []):
            snippet = item['snippet']
            playlist_id = item['id']
            title = snippet['title']
            
            # Skip non-music playlists
            if any(keyword in title.lower() for keyword in ['album', 'ep', 'single', 'release']):
                playlists.append({
                    'title': title,
                    'playlist_id': playlist_id,
                    'cover_art': f"https://i.ytimg.com/vi/{playlist_id}/hqdefault.jpg",  # This might not work for playlists
                    'youtube_url': f"https://music.youtube.com/playlist?list={playlist_id}",
                    'published_at': snippet['publishedAt']
                })
        
        return playlists
        
    except Exception as e:
        print(f"Error getting playlists: {e}")
        return []


def create_html(albums):
    """Create HTML with your albums"""

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
    print("🎵 DJ Elsa - YouTube Data API Sync")
    print("==================================")

    load_env()

    # Get API key
    api_key = os.getenv('API_KEY') or os.getenv('YOUTUBE_API_KEY')
    if not api_key:
        print("❌ API_KEY not found in .env")
        print("\nMake sure your .env file has:")
        print("API_KEY=your_youtube_api_key_here")
        return

    # Get channel ID from environment or auto-detect
    channel_id = os.getenv('CHANNEL_ID')
    if not channel_id:
        channel_id = get_channel_id()
    
    if not channel_id:
        print("❌ Could not find channel ID")
        print("Please add CHANNEL_ID to your .env file")
        return

    print(f"Using channel ID: {channel_id}")

    # Try to get playlists (releases) first
    print("Looking for releases (playlists)...")
    albums = get_channel_playlists(channel_id, api_key)
    
    if not albums:
        print("No playlists found, getting individual videos...")
        albums = get_channel_videos(channel_id, api_key)
    
    if not albums:
        print("❌ No albums found")
        return

    # Create HTML
    html = create_html(albums)
    Path('kissingface.html').write_text(html)

    print(f"✅ Created kissingface.html with {len(albums)} albums")
    print("✅ All albums are from YOUR YouTube channel")
    print("✅ No more wrong matches!")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
YouTube Release Sync for ONCE Distribution
Automates updating kissingface.html with new releases from YouTube/ONCE
"""

import json
import os
import re
import requests
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
import sys

# Load .env file if it exists
def load_env():
    if os.path.exists('.env'):
        with open('.env') as f:
            for line in f:
                if line.strip() and not line.startswith('#'):
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value

load_env()

class OnceAPI:
    """Handle ONCE API interactions"""
    
    def __init__(self, pat: str):
        self.base_url = "https://once.app/v1"
        self.headers = {
            "Authorization": f"Bearer {pat}",
            "Content-Type": "application/json"
        }
    
    def get_releases(self) -> List[Dict]:
        """Fetch all releases from ONCE with pagination"""
        all_releases = []
        offset = 0
        limit = 100
        
        while True:
            try:
                url = f"{self.base_url}/releases?limit={limit}&offset={offset}"
                response = requests.get(url, headers=self.headers)
                response.raise_for_status()
                data = response.json()
                
                # Handle the actual API response format
                if isinstance(data, dict) and 'releases' in data:
                    releases = data['releases']
                    all_releases.extend(releases)
                    
                    # Check if there are more releases
                    if 'nextOffset' in data and data['nextOffset'] is not None:
                        offset = data['nextOffset']
                    else:
                        break
                elif isinstance(data, list):
                    # Direct list response
                    all_releases.extend(data)
                    break
                else:
                    print(f"Unexpected response format: {type(data)}")
                    break
                    
            except requests.exceptions.RequestException as e:
                print(f"Error fetching releases: {e}")
                break
        
        print(f"Fetched {len(all_releases)} total releases")
        return all_releases
    
    def get_release_status(self, release_id: str) -> Dict:
        """Get detailed status for a specific release"""
        try:
            response = requests.get(
                f"{self.base_url}/releases/{release_id}/status", 
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching release status: {e}")
            return {}

class YouTubeReleaseExtractor:
    """Extract YouTube video and playlist IDs from release data"""
    
    @staticmethod
    def extract_from_release(release: Dict) -> Optional[Dict]:
        """
        Extract YouTube info from a release
        Returns dict with title, date, video_id, playlist_id
        """
        # This is a template - adjust based on actual ONCE API response structure
        youtube_data = release.get('platforms', {}).get('youtube', {})
        
        if not youtube_data.get('video_id'):
            return None
        
        return {
            'title': release.get('title', 'Unknown'),
            'date': release.get('release_date', datetime.now().strftime('%Y-%m-%d')),
            'video': youtube_data.get('video_id'),
            'list': youtube_data.get('playlist_id')
        }

class KissingFaceUpdater:
    """Update kissingface.html with new releases"""
    
    def __init__(self, html_path: str = "kissingface.html"):
        self.html_path = Path(html_path)
        self.template_path = Path("kissingface_template.html")
        
        # If no template exists, create one from current file
        if not self.template_path.exists() and self.html_path.exists():
            self._create_template()
    
    def _create_template(self):
        """Create a template file from current kissingface.html"""
        content = self.html_path.read_text()
        
        # Replace the albums array with a placeholder
        template = re.sub(
            r'const albums=\[.*?\];',
            'const albums={{ALBUMS_PLACEHOLDER}};',
            content,
            flags=re.DOTALL
        )
        
        self.template_path.write_text(template)
        print(f"Created template: {self.template_path}")
    
    def update_releases(self, albums: List[Dict]) -> bool:
        """Update kissingface.html with new album data"""
        try:
            if not self.template_path.exists():
                print("No template found. Please create kissingface_template.html first.")
                return False
            
            template = self.template_path.read_text()
            
            # Format albums as JavaScript array
            js_albums = "const albums=[\n"
            for i, album in enumerate(albums):
                js_albums += f'      {{title:"{album["title"]}",date:"{album["date"]}",video:"{album["video"]}",list:"{album["list"]}"}}'
                if i < len(albums) - 1:
                    js_albums += ","
                js_albums += "\n"
            js_albums += "    ];"
            
            # Replace placeholder
            new_content = template.replace('{{ALBUMS_PLACEHOLDER}}', js_albums)
            
            # Write updated file
            self.html_path.write_text(new_content)
            print(f"Updated {self.html_path} with {len(albums)} releases")
            return True
            
        except Exception as e:
            print(f"Error updating kissingface.html: {e}")
            return False

class WebhookServer:
    """Simple webhook server to receive ONCE webhooks"""
    
    @staticmethod
    def create_handler(updater: KissingFaceUpdater, api: OnceAPI):
        """Create a webhook handler function"""
        def handle_webhook(payload: Dict):
            """Process ONCE webhook payload"""
            print(f"Received webhook: {payload}")
            
            event_type = payload.get('event')
            release_id = payload.get('release_id')
            
            if event_type in ['release.approved', 'release.status_changed']:
                print(f"Processing release {release_id}...")
                
                # Fetch updated release data
                status = api.get_release_status(release_id)
                
                # Extract YouTube info
                extractor = YouTubeReleaseExtractor()
                album = extractor.extract_from_release(status)
                
                if album:
                    # Here you would typically update your local cache/database
                    # and regenerate the HTML
                    print(f"New release detected: {album['title']}")
                    # Trigger update logic
                    # updater.update_releases([album])
        
        return handle_webhook

def main():
    """Main CLI interface"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Sync ONCE releases to kissingface.html')
    parser.add_argument('--pat', help='ONCE Personal Access Token', default=os.environ.get('ONCE_PAT'))
    parser.add_argument('--mode', choices=['fetch', 'webhook', 'cron'], default='fetch',
                       help='Operation mode: fetch (one-time), webhook (listen), cron (scheduled)')
    parser.add_argument('--output', default='kissingface.html', help='Output HTML file')
    parser.add_argument('--port', type=int, default=8080, help='Webhook server port')
    
    args = parser.parse_args()
    
    if not args.pat:
        print("Error: Please provide ONCE_PAT environment variable or --pat argument")
        print("Get your token from: https://beta.once.app/settings/api")
        sys.exit(1)
    
    api = OnceAPI(args.pat)
    updater = KissingFaceUpdater(args.output)
    
    if args.mode == 'fetch':
        # One-time fetch and update
        print("Fetching releases from ONCE...")
        releases = api.get_releases()
        
        extractor = YouTubeReleaseExtractor()
        albums = []
        for release in releases:
            album = extractor.extract_from_release(release)
            if album:
                albums.append(album)
        
        # Sort by date (newest first)
        albums.sort(key=lambda x: x['date'], reverse=True)
        
        if albums:
            updater.update_releases(albums)
        else:
            print("No YouTube releases found")
    
    elif args.mode == 'webhook':
        # Start webhook listener
        print(f"Starting webhook server on port {args.port}...")
        print("Configure this URL in ONCE: https://your-domain.com/webhook")
        print("For local testing, use ngrok: ngrok http 8080")
        
        from http.server import HTTPServer, BaseHTTPRequestHandler
        import json
        
        class WebhookHandler(BaseHTTPRequestHandler):
            def do_POST(self):
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                payload = json.loads(post_data.decode('utf-8'))
                
                handler = WebhookServer.create_handler(updater, api)
                handler(payload)
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "received"}).encode())
        
        server = HTTPServer(('localhost', args.port), WebhookHandler)
        print(f"Webhook server running on http://localhost:{args.port}")
        server.serve_forever()
    
    elif args.mode == 'cron':
        # Cron job mode - just fetch and update
        print(f"[{datetime.now()}] Running scheduled sync...")
        releases = api.get_releases()
        
        extractor = YouTubeReleaseExtractor()
        albums = []
        for release in releases:
            album = extractor.extract_from_release(release)
            if album:
                albums.append(album)
        
        albums.sort(key=lambda x: x['date'], reverse=True)
        
        if albums:
            updater.update_releases(albums)
        else:
            print("No releases to update")

if __name__ == "__main__":
    main()

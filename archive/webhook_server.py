#!/usr/bin/env python3
"""
Simple webhook server for ONCE release notifications
"""

import json
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs


class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        """Handle POST requests from ONCE webhooks"""
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)

        try:
            payload = json.loads(post_data.decode('utf-8'))
            print(f"📡 Received webhook: {json.dumps(payload, indent=2)}")

            # Process the webhook
            self.process_webhook(payload)

            # Send success response
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "received"}).encode())

        except Exception as e:
            print(f"❌ Error processing webhook: {e}")
            self.send_response(400)
            self.end_headers()

    def process_webhook(self, payload):
        """Process ONCE webhook payload"""
        event = payload.get('event')
        release_id = payload.get('release_id')

        print(f"🎵 Event: {event}")
        print(f"🆔 Release ID: {release_id}")

        if event == 'release.approved':
            print("✅ Release approved! You can now sync.")
            # Here you could trigger the sync automatically
            # os.system('./sync_releases.sh fetch')

        elif event == 'release.status_changed':
            print("🔄 Release status changed")
            # Check if it's now live on YouTube
            platforms = payload.get('platforms', {})
            if 'youtube' in platforms:
                print("🎬 YouTube release detected!")

    def log_message(self, format, *args):
        """Custom log format"""
        print(f"[{self.log_date_time_string()}] {format % args}")


def run_server(port=8080):
    """Start the webhook server"""
    server_address = ('', port)
    httpd = HTTPServer(server_address, WebhookHandler)
    print(f"🚀 Webhook server running on port {port}")
    print(f"📡 Local URL: http://localhost:{port}")
    print(f"🌐 Public URL: Use ngrok for external access")
    print(f"   ngrok http {port}")
    print("\nWaiting for ONCE webhooks...")
    httpd.serve_forever()


if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    run_server(port)

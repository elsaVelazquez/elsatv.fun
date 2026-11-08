#!/usr/bin/env python3
"""
Debug ONCE API response
"""

import os
import requests
import json

# Load .env
if os.path.exists('.env'):
    with open('.env') as f:
        for line in f:
            if line.strip() and not line.startswith('#'):
                key, value = line.strip().split('=', 1)
                os.environ[key] = value

pat = os.environ.get('ONCE_PAT')
if not pat:
    print("❌ ONCE_PAT not found")
    exit(1)

print("🔍 Debugging ONCE API Response")
print("==============================")

headers = {
    "Authorization": f"Bearer {pat}",
    "Content-Type": "application/json"
}

# Test the releases endpoint
url = "https://beta.once.app/api/v1/releases"
print(f"Fetching: {url}")

try:
    response = requests.get(url, headers=headers)
    print(f"Status: {response.status_code}")
    print(f"Headers: {dict(response.headers)}")

    if response.status_code == 200:
        data = response.json()
        print(f"\n📦 Response Type: {type(data)}")
        print(
            f"📦 Response Length: {len(data) if isinstance(data, list) else 'N/A'}")

        # Pretty print first few items
        print(f"\n📄 Full Response:")
        print(json.dumps(data, indent=2)[
              :2000] + "..." if len(str(data)) > 2000 else json.dumps(data, indent=2))

        # Check if it's paginated
        if isinstance(data, dict):
            print(f"\n🔍 Response Keys: {list(data.keys())}")
            if 'releases' in data:
                releases = data['releases']
                print(f"🎵 Found {len(releases)} releases")
            if 'pagination' in data:
                print(f"📄 Pagination: {data['pagination']}")

        elif isinstance(data, list):
            print(f"🎵 Found {len(data)} releases")
            if len(data) > 0:
                print(f"\n📄 First Release:")
                print(json.dumps(data[0], indent=2))

    else:
        print(f"❌ Error: {response.text}")

except Exception as e:
    print(f"❌ Exception: {e}")

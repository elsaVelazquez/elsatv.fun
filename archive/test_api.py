#!/usr/bin/env python3
"""
Test ONCE API connection directly
"""

import os
import requests

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

print("🔍 Testing ONCE API")
print("===================")
print(f"Token: {pat[:20]}...")

# Test different endpoints
endpoints = [
    "https://beta.once.app/api/v1/releases",
    "https://beta.once.app/api/v1/user",
    "https://beta.once.app/api/v1/account",
    "https://beta.once.app/api/releases",  # Maybe no /v1
    "https://once.app/api/v1/releases",    # Maybe no beta
]

headers = {
    "Authorization": f"Bearer {pat}",
    "Content-Type": "application/json"
}

for url in endpoints:
    print(f"\nTesting: {url}")
    try:
        response = requests.get(url, headers=headers, timeout=10)
        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            print("✅ SUCCESS!")
            data = response.json()
            print(f"Response: {data}")
        elif response.status_code == 401:
            print("❌ Unauthorized - check your token")
        elif response.status_code == 404:
            print("❌ Not Found - endpoint might be wrong")
        else:
            print(f"Response: {response.text[:200]}")

    except Exception as e:
        print(f"❌ Error: {e}")

print("\n" + "="*50)
print("💡 If all endpoints fail:")
print("1. Check your token has the right permissions")
print("2. Try creating a new token with 'Full REST API access'")
print("3. Check ONCE documentation for correct API endpoints")

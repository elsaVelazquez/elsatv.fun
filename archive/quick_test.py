#!/usr/bin/env python3
"""
Quick test - no hanging, immediate feedback
"""

import os
import sys

print("🔍 Quick Test - YouTube Release Sync")
print("=" * 40)

# Test 1: Check if requests is installed
print("1. Checking Python dependencies...")
try:
    import requests
    print("   ✅ requests is installed")
except ImportError:
    print("   ❌ requests not installed")
    print("   Run: pip3 install requests")
    sys.exit(1)

# Test 2: Check if files exist
print("\n2. Checking files...")
files = ['youtube_release_sync.py', 'kissingface.html']
for f in files:
    if os.path.exists(f):
        print(f"   ✅ {f}")
    else:
        print(f"   ❌ {f} missing")

# Test 3: Check ONCE PAT
print("\n3. Checking ONCE Personal Access Token...")
pat = os.environ.get('ONCE_PAT')
if not pat:
    print("   ❌ ONCE_PAT environment variable not set")
    print("\n   To fix:")
    print("   1. Go to https://beta.once.app/settings/api")
    print("   2. Click 'Create token'")
    print("   3. Copy the token (starts with 'once_pat_...')")
    print("   4. Run: export ONCE_PAT='your_token_here'")
    print("\n   Then run this test again.")
    sys.exit(1)
elif not pat.startswith('once_pat_'):
    print("   ⚠️  Token doesn't start with 'once_pat_'")
    print("   Make sure you copied the full token")
    sys.exit(1)
else:
    print("   ✅ ONCE_PAT is set")

# Test 4: Try to import our module
print("\n4. Testing module import...")
try:
    from youtube_release_sync import OnceAPI
    print("   ✅ Module imports successfully")
except Exception as e:
    print(f"   ❌ Import error: {e}")
    sys.exit(1)

print("\n" + "=" * 40)
print("🎉 Basic tests passed! Ready for next step.")
print("\nNext steps:")
print("1. Set your ONCE token: export ONCE_PAT='your_token_here'")
print("2. Run the sync: python youtube_release_sync.py --mode fetch")
print("\n💡 Tip: To make the token permanent, add it to your ~/.zshrc:")
print("   echo 'export ONCE_PAT=\"your_token_here\"' >> ~/.zshrc")

#!/usr/bin/env python3
"""
Test script for YouTube Release Sync
Run this to verify everything is working before going live
"""

import os
import sys
from pathlib import Path


def test_imports():
    """Test that all required modules can be imported"""
    print("Testing imports...")
    try:
        import requests
        print("✅ requests imported successfully")
        return True
    except ImportError as e:
        print(f"❌ Missing dependency: {e}")
        print("Run: pip install -r requirements.txt")
        return False


def test_once_pat():
    """Test that ONCE PAT is set"""
    print("\nTesting ONCE PAT...")
    pat = os.environ.get('ONCE_PAT')
    if not pat:
        print("❌ ONCE_PAT not set")
        print("Run: export ONCE_PAT='your_token_here'")
        return False

    if not pat.startswith('once_pat_'):
        print("⚠️  Warning: ONCE_PAT doesn't start with 'once_pat_'")
        print("Make sure you copied the full token")
        return False

    print("✅ ONCE_PAT is set")
    return True


def test_files():
    """Test that required files exist"""
    print("\nTesting files...")
    files = [
        'youtube_release_sync.py',
        'kissingface.html'
    ]

    all_exist = True
    for file in files:
        if Path(file).exists():
            print(f"✅ {file} exists")
        else:
            print(f"❌ {file} missing")
            all_exist = False

    return all_exist


def test_api_connection():
    """Test connection to ONCE API"""
    print("\nTesting ONCE API connection...")
    try:
        from youtube_release_sync import OnceAPI

        pat = os.environ.get('ONCE_PAT')
        if not pat:
            print("❌ Cannot test API without ONCE_PAT")
            return False

        api = OnceAPI(pat)
        releases = api.get_releases()

        if isinstance(releases, list):
            print(
                f"✅ API connection successful ({len(releases)} releases found)")
            return True
        else:
            print("⚠️  API returned unexpected format")
            return False

    except Exception as e:
        print(f"❌ API connection failed: {e}")
        return False


def test_template_creation():
    """Test template creation"""
    print("\nTesting template creation...")
    try:
        from youtube_release_sync import KissingFaceUpdater

        updater = KissingFaceUpdater()

        if Path('kissingface_template.html').exists():
            print("✅ Template file exists")
            return True
        else:
            print("❌ Template file not created")
            return False

    except Exception as e:
        print(f"❌ Template creation failed: {e}")
        return False


def main():
    """Run all tests"""
    print("🧪 YouTube Release Sync - Test Suite")
    print("=" * 40)

    tests = [
        test_imports,
        test_once_pat,
        test_files,
        test_template_creation,
        test_api_connection
    ]

    passed = 0
    total = len(tests)

    for test in tests:
        if test():
            passed += 1
        print()

    print("=" * 40)
    print(f"Tests passed: {passed}/{total}")

    if passed == total:
        print("🎉 All tests passed! You're ready to sync releases.")
        print("\nNext steps:")
        print("1. Run: ./sync_releases.sh fetch")
        print("2. Set up cron job for automation")
        print("3. Configure webhooks for real-time updates")
    else:
        print("❌ Some tests failed. Please fix the issues above.")
        sys.exit(1)


if __name__ == "__main__":
    main()

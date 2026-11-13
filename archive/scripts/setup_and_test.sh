#!/bin/bash
# One-command setup and test

# Load environment variables from .env file if it exists
if [ -f .env ]; then
    echo "📄 Loading configuration from .env file..."
    export $(cat .env | grep -v '^#' | xargs)
fi

echo "🎵 YouTube Release Sync - Setup & Test"
echo "======================================"

# Check if we're in the right directory
if [ ! -f "kissingface.html" ]; then
    echo "❌ Error: kissingface.html not found"
    echo "Please run this from your website directory"
    exit 1
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Check if ONCE_PAT is set
if [ -z "$ONCE_PAT" ]; then
    echo ""
    echo "🔑 ONCE Personal Access Token Required"
    echo "======================================"
    echo ""
    echo "Please get your token from: https://beta.once.app/settings/api"
    echo ""
    echo "Then either:"
    echo "  1. Create a .env file: echo 'ONCE_PAT=your_token_here' > .env"
    echo "  2. Or export it: export ONCE_PAT='your_token_here'"
    echo ""
    echo "Then run: ./setup_and_test.sh"
    echo ""
    exit 1
fi

echo "✅ Token found"
echo ""

# Run quick test
echo "🧪 Running tests..."
python quick_test.py

if [ $? -eq 0 ]; then
    echo ""
    echo "🚀 Running first sync..."
    python youtube_release_sync.py --mode fetch
    
    if [ $? -eq 0 ]; then
        echo ""
        echo "🎉 Success! Check your kissingface.html"
        echo ""
        echo "To automate this daily:"
        echo "  crontab -e"
        echo "  Add: 0 2 * * * cd $(pwd) && ./sync_releases.sh cron"
    else
        echo ""
        echo "❌ Sync failed. Check the error above."
    fi
else
    echo ""
    echo "❌ Tests failed. Please fix the issues above."
fi

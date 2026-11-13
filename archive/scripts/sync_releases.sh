#!/bin/bash
# Simple wrapper for YouTube release sync

set -e

# Load environment variables from .env file if it exists
if [ -f .env ]; then
    echo "📄 Loading configuration from .env file..."
    export $(cat .env | grep -v '^#' | xargs)
fi

echo "🎵 YouTube Release Sync for ONCE"
echo "================================"

# Check if ONCE_PAT is set
if [ -z "$ONCE_PAT" ]; then
    echo "❌ Error: ONCE_PAT environment variable not set"
    echo ""
    echo "To get your token:"
    echo "1. Go to https://beta.once.app/settings/api"
    echo "2. Click 'Create token'"
    echo "3. Copy the token (starts with 'once_pat_...')"
    echo "4. Run: export ONCE_PAT='your_token_here'"
    exit 1
fi

# Default to fetch mode if no argument provided
MODE=${1:-fetch}

case $MODE in
    "fetch")
        echo "📥 Fetching releases from ONCE..."
        python3 youtube_release_sync.py --mode fetch
        ;;
    "webhook")
        echo "🔗 Starting webhook server..."
        echo "💡 Use ngrok for public URL: ngrok http 8080"
        python3 youtube_release_sync.py --mode webhook --port 8080
        ;;
    "cron")
        echo "⏰ Running scheduled sync..."
        python3 youtube_release_sync.py --mode cron
        ;;
    "setup")
        echo "🔧 Setting up template..."
        python3 -c "
from youtube_release_sync import KissingFaceUpdater
updater = KissingFaceUpdater()
print('✅ Template created: kissingface_template.html')
        "
        ;;
    *)
        echo "Usage: $0 [fetch|webhook|cron|setup]"
        echo ""
        echo "Commands:"
        echo "  fetch   - One-time sync from ONCE"
        echo "  webhook - Start webhook listener"
        echo "  cron    - Run scheduled sync"
        echo "  setup   - Create template from existing HTML"
        exit 1
        ;;
esac

echo "✅ Done!"

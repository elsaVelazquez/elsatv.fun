#!/bin/bash
# Simple test with maximum verbosity

echo "🔍 Simple Test - YouTube Release Sync"
echo "====================================="

# Load .env
echo "Loading .env file..."
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
    echo "✅ .env loaded"
else
    echo "❌ .env file not found"
    exit 1
fi

# Check token
echo "Checking ONCE_PAT..."
if [ -z "$ONCE_PAT" ]; then
    echo "❌ ONCE_PAT not set"
    exit 1
else
    echo "✅ ONCE_PAT is set (length: ${#ONCE_PAT})"
fi

# Activate virtual environment
echo "Activating virtual environment..."
if [ -d "venv" ]; then
    source venv/bin/activate
    echo "✅ Virtual environment activated"
    echo "Python: $(which python)"
    echo "Python version: $(python --version)"
else
    echo "❌ Virtual environment not found"
    exit 1
fi

# Check files
echo "Checking required files..."
for file in youtube_release_sync.py kissingface.html; do
    if [ -f "$file" ]; then
        echo "✅ $file exists"
    else
        echo "❌ $file missing"
        exit 1
    fi
done

# Test import
echo "Testing Python import..."
python -c "import requests; print('✅ requests imported')" 2>&1

if [ $? -ne 0 ]; then
    echo "❌ Failed to import requests"
    echo "Installing requests..."
    pip install requests
fi

# Run the sync
echo ""
echo "🚀 Running sync..."
echo "Command: python youtube_release_sync.py --mode fetch"
echo ""

python youtube_release_sync.py --mode fetch

echo ""
echo "✅ Script completed"

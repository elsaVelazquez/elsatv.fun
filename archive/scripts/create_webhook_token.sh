#!/bin/bash
# Instructions for creating the right token and webhook

echo "🔧 ONCE Token & Webhook Setup"
echo "============================="
echo ""

echo "1️⃣ CREATE A NEW TOKEN WITH FULL API ACCESS:"
echo "   - Go to: https://beta.once.app/settings/api"
echo "   - Click 'Create token'"
echo "   - Name it: 'YouTube Sync Full Access'"
echo "   - Check 'Full REST API access' (NOT just MCP)"
echo "   - Copy the token"
echo ""

echo "2️⃣ UPDATE YOUR .env FILE:"
echo "   echo 'ONCE_PAT=your_new_full_access_token' > .env"
echo ""

echo "3️⃣ START THE WEBHOOK SERVER:"
echo "   source venv/bin/activate"
echo "   python webhook_server.py 8080"
echo ""

echo "4️⃣ EXPOSE IT PUBLICLY (in another terminal):"
echo "   ngrok http 8080"
echo ""

echo "5️⃣ ADD THE WEBHOOK TO ONCE:"
echo "   - Copy the ngrok URL (e.g., https://abc123.ngrok.io)"
echo "   - In ONCE webhook settings, add:"
echo "     URL: https://abc123.ngrok.io/webhook"
echo "     Events: release.approved, release.status_changed"
echo ""

echo "6️⃣ TEST THE SYNC:"
echo "   ./sync_releases.sh fetch"
echo ""

echo "💡 The webhook will notify you when releases are ready!"

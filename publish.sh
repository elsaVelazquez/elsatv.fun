#!/bin/sh
# publish.sh — rebuild the music page and push it live.
#
#   ./publish.sh
#
# Runs FINAL_SYNC.py (needs .env), then commits only the generated files and
# pushes to main. GitHub Pages serves kissingface.html from the repo root.
set -e
cd "$(dirname "$0")"

# venv must exist — FINAL_SYNC.py needs `requests`
if [ -x venv/bin/python ]; then
    PY=venv/bin/python
elif command -v python3 >/dev/null 2>&1; then
    PY=python3
else
    echo "no python found — create venv first: python3 -m venv venv" >&2
    exit 1
fi

echo "→ syncing releases"
"$PY" FINAL_SYNC.py

# Only build output is staged. manual_links.json and .env are never touched:
# the first is yours to edit, the second must never be committed.
git add kissingface.html lore/songs.json lore/yt_link_cache.json

if git diff --staged --quiet; then
    echo "→ nothing changed, nothing to publish"
    exit 0
fi

echo "→ committing"
git commit -m "Update releases $(date +%F)"

echo "→ pushing to $(git rev-parse --abbrev-ref HEAD)"
git push

echo "✓ published — https://elsatv.fun/kissingface.html"

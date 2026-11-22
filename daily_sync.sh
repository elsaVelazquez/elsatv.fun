#!/bin/bash

set -u

cd "$(dirname "$0")" || exit 1

export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:$PATH"
export GIT_TERMINAL_PROMPT=0

# ==========================================
# 1. PREVENT OVERLAPPING LOCAL RUNS
# ==========================================

# lockf is built into macOS.
# The system releases the lock when the
# process ends, even after most crashes.

if [ "${SYNC_LOCKED:-0}" != "1" ]; then
    exec venv/bin/python -c '
import fcntl
import os
import sys

lock = open(".daily_sync.lock", "a+")

try:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    print("Another sync is already running. Skipping.")
    sys.exit(0)

os.environ["SYNC_LOCKED"] = "1"

# Keep the lock file open while Bash runs.
os.set_inheritable(lock.fileno(), True)
os.execv("/bin/bash", ["/bin/bash", "daily_sync.sh"])
'
fi

echo "===== Daily sync started: $(date) ====="

# ==========================================
# 2. VERIFY MAIN BRANCH
# ==========================================

if [ "$(git branch --show-current)" != "main" ]; then
    echo "ERROR: Not on main. Aborting."
    exit 1
fi

# ==========================================
# 3. UPDATE LOCAL COPY FROM GITHUB
# ==========================================

echo "Checking GitHub for updates..."

if ! git pull --ff-only origin main; then
    echo "ERROR: GitHub update failed."
    echo "No local changes were deleted."
    exit 1
fi

# ==========================================
# 4. POSTS PIPELINE
# ==========================================

echo "--- Syncing Posts ---"

# Can now run 25+ minutes on a first catch-up: it also reads the text inside
# any image that has no reading yet (local tesseract; vision capped at $0.50
# per run). caffeinate keeps the Mac awake so a long run is not cut off.
NO_SLEEP=""
if command -v caffeinate >/dev/null 2>&1; then
    NO_SLEEP="caffeinate -dimsu"
fi

if $NO_SLEEP venv/bin/python \
    scripts/lore/yt_posts_lore_scripts/sync_posts.py; then

    if ! git diff --quiet HEAD -- posts.html; then

        git commit --only \
            -m "Posts: sync" -- posts.html || exit 1

    fi

else
    echo "ERROR: Posts sync failed."
    exit 1
fi

# ==========================================
# 5. KISSINGFACE MUSIC PIPELINE
# ==========================================
# sync_music.py, not FINAL_SYNC.py: it runs build_albums.py and
# collect_music_links.py first, and those are what actually discover the
# per-song YouTube Music links. FINAL_SYNC.py on its own only reuses links it
# is handed, so it can never link the songs of a release it has not seen.

echo "--- Syncing Music ---"

if venv/bin/python \
    scripts/lore/music_lore_scripts/sync_music.py; then

    # Stage every file the music page is built from. The per-song links live in
    # albums.json and music_links_enriched.json: left unstaged, the next run
    # starts without them and has to look everything up again.
    git add -- \
        kissingface.html \
        lore/songs.json \
        lore/albums.json \
        lore/music_links_enriched.json \
        lore/yt_link_cache.json \
        lore/releases_cache.json \
        lore/release_dates.json \
        lore/tracks_cache.json \
        lore/release_cache.json

    if ! git diff --cached --quiet; then
        # Only a regeneration timestamp changed? Then nothing real did — the
        # sync stamps generated_at on every run. Do not commit an empty update.
        if [ -z "$(git diff --cached -U0 | grep -E '^[-+] ' \
            | grep -vE '^[-+]  "(generated_at|source_generated_at)"')" ]; then
            echo "Only timestamps changed — nothing to commit."
            git reset -q
        else
            git commit -m "Update music page" || exit 1
        fi
    fi

else
    echo "ERROR: Music sync failed."
    exit 1
fi

# ==========================================
# 6. PUSH TO GITHUB
# ==========================================

echo "Pushing both pipelines..."

if ! git push origin main; then
    echo "WARNING: Push failed."
    echo "Changes remain committed locally."
    echo "No force-push attempted."
    exit 1
fi

echo "GitHub updated successfully."

# ==========================================
# 7. WAIT FIVE MINUTES
# ==========================================

echo "Waiting 5 minutes for GitHub Pages..."

sleep 300

# ==========================================
# 8. REFRESH BOTH CHROME PAGES
# ==========================================

osascript <<'APPLESCRIPT'

set targetURLs to {"https://elsatv.fun/posts.html", "https://elsatv.fun/kissingface.html"\}

tell application "Google Chrome"

    activate

    if (count of windows) is 0 then
        make new window
    end if

    repeat with targetURL in targetURLs

        set foundTab to false

        repeat with w in windows

            repeat with i from 1 to (count of tabs of w)

                if (URL of tab i of w) starts with (contents of targetURL) then

                    set foundTab to true
                    set index of w to 1
                    set active tab index of w to i

                    delay 1

                    tell application "System Events"
                        keystroke "r" using {command down, shift down}
                    end tell

                    exit repeat
                end if

            end repeat

            if foundTab then exit repeat
        end repeat

        if not foundTab then
            open location (contents of targetURL)
            delay 3

            tell application "System Events"
                keystroke "r" using {command down, shift down}
            end tell
        end if

        delay 2

    end repeat

end tell

APPLESCRIPT

if [ $? -eq 0 ]; then
    echo "Both pages refreshed."
else
    echo "WARNING: Browser refresh failed."
fi

echo "===== Daily sync finished: $(date) ====="


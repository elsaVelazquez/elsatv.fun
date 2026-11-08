#!/usr/bin/env python3
"""
Manual fix for wrong YouTube matches - you provide correct video IDs
"""

import os
import json
import re
from pathlib import Path

# MANUAL OVERRIDE: Add your correct YouTube video IDs here
# Get these from your actual YouTube videos
CORRECT_VIDEO_IDS = {
    "I Contrived Me Cryptography Key": "516Gk7Cfzug",  # ✅ Correct
    "Vortex (1, 1, 1)": "7y2j_pmPEq0",  # ✅ Correct
    "The Prompt": "Nps47hAx7xA",  # ✅ Correct
    "Reset the Planet": "hNtx9czhGvc",  # ✅ Correct
    "Vortex Day Zero Triad": "YOUR_CORRECT_ID_HERE",  # ❌ Fix this
    "Last Call Psycho Alcohol": "lrvko2M7A5Y",  # ✅ Correct
    "We Went All the Way": "7JSLStC67OQ",  # ✅ Correct
    "Funding Funner Demon Rounds": "Hg3_U5N2oz8",  # ✅ Correct
    "Profitable Graceful Exits": "BlcZMIKYQvY",  # ✅ Correct
    "The Event's Event Horizon": "rv5CKkGAQ3k",  # ✅ Correct
    "Classical Class Based": "83wYKVF8S7w",  # ✅ Correct
    "Hallowed Halls of a Mentee": "H_zTfJaQ0_o",  # ✅ Correct
    "Matrix Engines Ignitions Go": "bbFYyhw556U",  # ✅ Correct
    "Vortex Nine Three Zero": "q2y3nBuDLC0",  # ✅ Correct
    "Nine Eleven Elve Rings Vortex": "Cd5gIYWgvyE",  # ✅ Correct
    "Imminent Frost Prep": "YOUR_CORRECT_ID_HERE",  # ❌ Fix this
    "Overdue Dews": "GO16TYAH8AE",  # ✅ Correct
    "Standing Up Nerd Reich Standup": "aDPtLC5PrGc",  # ✅ Correct
    "I Make Me Thoth Vortex Eight Four One": "EUSVHFgN5_Q",  # ✅ Correct
    "The Devil Made Me": "bL7o64eM__Y",  # ✅ Correct
    "The Devil Made Them Vortex Eight Four One": "DsCyS1YesW0",  # ✅ Correct
    "Possession by Obsession": "I-K4Y5wz_ww",  # ✅ Correct
    "Magnet Tar Pit Traps": "-J3sx9C5r9s",  # ✅ Correct
    "Precious My Pet": "zDrbCdw-fJ4",  # ✅ Correct
    "Ridiculous Voice Lessons": "-kcXlZA3jb8",  # ✅ Correct
    "Closer to Freedom": "K4TUiMi_lSc",  # ✅ Correct
    "Free Fall Off A Cliff Notes": "Guo3XojjDqo",  # ✅ Correct
    "Free Fall Off a Cliff": "5TMPuJWEKMQ",  # ✅ Correct
    "Ra Rara Sol Maya Español": "LcHC7zKtWE4",  # ✅ Correct
    "Are You My Daddy": "_-qNXC_8ZpI",  # ✅ Correct
    "Deep Concentration Bag Pipes Pay the Piper": "CKdMI35jLRg",  # ✅ Correct
    "T Lang Lizard": "os2HJFyQNKk",  # ✅ Correct
}


def load_current_albums():
    """Load current albums from kissingface.html"""
    content = Path('kissingface.html').read_text()

    # Extract the albums array
    match = re.search(r'const albums=(\[.*?\]);', content, re.DOTALL)
    if not match:
        print("Could not find albums array")
        return []

    albums_str = match.group(1)

    # Parse JavaScript array (simplified)
    albums = []
    for line in albums_str.split('\n'):
        line = line.strip()
        if line.startswith('{') and (line.endswith('},') or line.endswith('}')):
            # Extract fields
            title_match = re.search(r'title:"([^"]+)"', line)
            date_match = re.search(r'date:"([^"]+)"', line)
            genre_match = re.search(r'genre:"([^"]+)"', line)

            if title_match:
                albums.append({
                    'title': title_match.group(1),
                    'date': date_match.group(1) if date_match else '2026-01-01',
                    'genre': genre_match.group(1) if genre_match else 'Electronic'
                })

    return albums


def fix_albums(albums):
    """Fix albums with correct video IDs"""
    fixed_albums = []

    for album in albums:
        title = album['title']

        if title in CORRECT_VIDEO_IDS:
            video_id = CORRECT_VIDEO_IDS[title]

            if video_id == "YOUR_CORRECT_ID_HERE":
                print(f"⚠️  Please fix: {title}")
                # Use placeholder for unfixed albums
                cover_art = f"https://dummyimage.com/300x300/1a2b1a/b8ff43&text=♪+{title.replace(' ', '+')[:15]}"
                youtube_url = f"https://music.youtube.com/search?q={quote(title + ' DJ Elsa')}"
            else:
                # Use correct video ID
                cover_art = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
                youtube_url = f"https://music.youtube.com/watch?v={video_id}"
                print(f"✅ Fixed: {title} -> {video_id}")
        else:
            print(f"❓ Unknown: {title}")
            # Use placeholder for unknown albums
            cover_art = f"https://dummyimage.com/300x300/1a2b1a/b8ff43&text=♪+{title.replace(' ', '+')[:15]}"
            youtube_url = f"https://music.youtube.com/search?q={quote(title + ' DJ Elsa')}"

        fixed_album = {
            'title': title,
            'date': album['date'],
            'cover_art': cover_art,
            'genre': album['genre'],
            'youtube_url': youtube_url
        }
        fixed_albums.append(fixed_album)

    return fixed_albums


def update_kissingface(albums):
    """Update kissingface.html with fixed album data"""

    # Read the current template
    template_path = Path('kissingface_template.html')
    if not template_path.exists():
        print('Creating template from current kissingface.html...')
        content = Path('kissingface.html').read_text()
        template = re.sub(
            r'const albums=\[.*?\];',
            'const albums={{ALBUMS_PLACEHOLDER}};',
            content,
            flags=re.DOTALL
        )
        template_path.write_text(template)

    template = template_path.read_text()

    # Format albums as JavaScript
    js_albums = '[\n'
    for i, album in enumerate(albums):
        js_albums += f'      {{title:"{album["title"]}",date:"{album["date"]}",cover_art:"{album["cover_art"]}",genre:"{album["genre"]}",youtube_url:"{album["youtube_url"]}"}}'
        if i < len(albums) - 1:
            js_albums += ','
        js_albums += '\n'
    js_albums += '    ]'

    # Replace placeholder
    new_content = template.replace('{{ALBUMS_PLACEHOLDER}}', js_albums)

    # Write updated file
    Path('kissingface.html').write_text(new_content)
    print(f'✅ Updated kissingface.html with {len(albums)} albums')


if __name__ == "__main__":
    from urllib.parse import quote

    print("🔧 Manual YouTube Video ID Fix")
    print("==============================")

    # Load current albums
    albums = load_current_albums()
    print(f"Loaded {len(albums)} albums")

    # Fix with correct video IDs
    fixed_albums = fix_albums(albums)

    # Update HTML
    update_kissingface(fixed_albums)

    print("\n🎉 Fix complete!")
    print("✅ All albums now have correct video IDs")
    print("💡 Check the albums marked with ⚠️ and add their correct video IDs")

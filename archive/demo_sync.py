#!/usr/bin/env python3
"""
Demo version with sample data - shows how the HTML update works
"""

import re
from pathlib import Path

# Sample release data (like what ONCE would return)
sample_albums = [
    {
        "title": "Galactic Grim Reaper Diaries",
        "date": "2026-10-29",
        "video": "17L5pnh8U3U",
        "list": "OLAK5uy_njDnaz1_ezOhxg6FrA5IMBGdNbqEua5_Q"
    },
    {
        "title": "The Book of Becoming: The Seed",
        "date": "2026-10-27",
        "video": "3qB2fRYf88w",
        "list": "OLAK5uy_m42EEp7pBZmKkhZobdmAhFzLM4Dd01lsY"
    },
    {
        "title": "Puppets (Deluxe Edition)",
        "date": "2026-10-27",
        "video": "4Z14pSOYsS0",
        "list": "OLAK5uy_ky9IhMrJWYi8hvxArbray5Szeew46DIUk"
    }
]


def update_kissingface(albums):
    """Update kissingface.html with album data"""

    # Read the template
    template_path = Path("kissingface_template.html")
    if not template_path.exists():
        print("Creating template from kissingface.html...")
        content = Path("kissingface.html").read_text()
        template = re.sub(
            r'const albums=\[.*?\];',
            'const albums={{ALBUMS_PLACEHOLDER}};',
            content,
            flags=re.DOTALL
        )
        template_path.write_text(template)

    template = template_path.read_text()

    # Format albums as JavaScript (just the array part)
    js_albums = "[\n"
    for i, album in enumerate(albums):
        js_albums += f'      {{title:"{album["title"]}",date:"{album["date"]}",video:"{album["video"]}",list:"{album["list"]}"}}'
        if i < len(albums) - 1:
            js_albums += ","
        js_albums += "\n"
    js_albums += "    ]"

    # Replace placeholder
    new_content = template.replace('{{ALBUMS_PLACEHOLDER}}', js_albums)

    # Write updated file
    Path("kissingface.html").write_text(new_content)
    print(f"✅ Updated kissingface.html with {len(albums)} albums")


if __name__ == "__main__":
    print("🎵 Demo Sync - YouTube Release Update")
    print("====================================")
    print(f"Using {len(sample_albums)} sample albums...")

    update_kissingface(sample_albums)

    print("\n📄 Check your kissingface.html - it should now have sample data!")
    print("🔍 Look for the 'const albums=' section")

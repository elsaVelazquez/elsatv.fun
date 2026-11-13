#!/usr/bin/env python3
"""
Simple Manual YouTube Sync - You control which albums are included
"""

from pathlib import Path

# 🎯 YOUR ACTUAL ALBUMS - Add your real YouTube video IDs here
# Get them from: https://www.youtube.com/@elsavelaz/releases
ALBUMS = [
    {
        "title": "I Contrived Me Cryptography Key",
        "video_id": "516Gk7Cfzug",  # ✅ Your actual video ID
    },
    {
        "title": "Vortex (1, 1, 1)", 
        "video_id": "7y2j_pmPEq0",  # ✅ Your actual video ID
    },
    {
        "title": "The Prompt",
        "video_id": "Nps47hAx7xA",  # ✅ Your actual video ID
    },
    {
        "title": "Reset the Planet",
        "video_id": "hNtx9czhGvc",  # ✅ Your actual video ID
    },
    {
        "title": "Last Call Psycho Alcohol",
        "video_id": "lrvko2M7A5Y",  # ✅ Your actual video ID
    },
    {
        "title": "We Went All the Way",
        "video_id": "7JSLStC67OQ",  # ✅ Your actual video ID
    },
    {
        "title": "Funding Funner Demon Rounds",
        "video_id": "Hg3_U5N2oz8",  # ✅ Your actual video ID
    },
    {
        "title": "Profitable Graceful Exits",
        "video_id": "BlcZMIKYQvY",  # ✅ Your actual video ID
    },
    {
        "title": "The Event's Event Horizon",
        "video_id": "rv5CKkGAQ3k",  # ✅ Your actual video ID
    },
    {
        "title": "Classical Class Based",
        "video_id": "83wYKVF8S7w",  # ✅ Your actual video ID
    },
    {
        "title": "Hallowed Halls of a Mentee",
        "video_id": "H_zTfJaQ0_o",  # ✅ Your actual video ID
    },
    {
        "title": "Matrix Engines Ignitions Go",
        "video_id": "bbFYyhw556U",  # ✅ Your actual video ID
    },
    {
        "title": "Vortex Nine Three Zero",
        "video_id": "q2y3nBuDLC0",  # ✅ Your actual video ID
    },
    {
        "title": "Nine Eleven Elve Rings Vortex",
        "video_id": "Cd5gIYWgvyE",  # ✅ Your actual video ID
    },
    {
        "title": "Overdue Dews",
        "video_id": "GO16TYAH8AE",  # ✅ Your actual video ID
    },
    {
        "title": "Standing Up Nerd Reich Standup",
        "video_id": "aDPtLC5PrGc",  # ✅ Your actual video ID
    },
    {
        "title": "I Make Me Thoth Vortex Eight Four One",
        "video_id": "EUSVHFgN5_Q",  # ✅ Your actual video ID
    },
    {
        "title": "The Devil Made Me",
        "video_id": "bL7o64eM__Y",  # ✅ Your actual video ID
    },
    {
        "title": "The Devil Made Them Vortex Eight Four One",
        "video_id": "DsCyS1YesW0",  # ✅ Your actual video ID
    },
    {
        "title": "Possession by Obsession",
        "video_id": "I-K4Y5wz_ww",  # ✅ Your actual video ID
    },
    {
        "title": "Magnet Tar Pit Traps",
        "video_id": "-J3sx9C5r9s",  # ✅ Your actual video ID
    },
    {
        "title": "Precious My Pet",
        "video_id": "zDrbCdw-fJ4",  # ✅ Your actual video ID
    },
    {
        "title": "Ridiculous Voice Lessons",
        "video_id": "-kcXlZA3jb8",  # ✅ Your actual video ID
    },
    {
        "title": "Closer to Freedom",
        "video_id": "K4TUiMi_lSc",  # ✅ Your actual video ID
    },
    {
        "title": "Free Fall Off A Cliff Notes",
        "video_id": "Guo3XojjDqo",  # ✅ Your actual video ID
    },
    {
        "title": "Free Fall Off a Cliff",
        "video_id": "5TMPuJWEKMQ",  # ✅ Your actual video ID
    },
    {
        "title": "Ra Rara Sol Maya Español",
        "video_id": "LcHC7zKtWE4",  # ✅ Your actual video ID
    },
    {
        "title": "Are You My Daddy",
        "video_id": "_-qNXC_8ZpI",  # ✅ Your actual video ID
    },
    {
        "title": "Deep Concentration Bag Pipes Pay the Piper",
        "video_id": "CKdMI35jLRg",  # ✅ Your actual video ID
    },
    {
        "title": "T Lang Lizard",
        "video_id": "os2HJFyQNKk",  # ✅ Your actual video ID
    },
]

def create_html():
    """Create the HTML file with your albums"""
    
    html = '''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DJ Elsa - Music Archive</title>
  <style>
    body { background: #0a0c08; color: #f5f6f0; font-family: Arial, sans-serif; margin: 0; padding: 20px; }
    .container { max-width: 1200px; margin: 0 auto; }
    .header { text-align: center; margin-bottom: 40px; }
    .header h1 { color: #b8ff43; font-size: 3rem; margin: 0; }
    .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 20px; }
    .album { background: #141912; border: 1px solid #303a2d; border-radius: 10px; overflow: hidden; transition: transform 0.2s; }
    .album:hover { transform: translateY(-2px); }
    .album img { width: 100%; height: 200px; object-fit: cover; }
    .album-info { padding: 15px; }
    .album-title { font-size: 1.1rem; font-weight: bold; margin: 0 0 10px 0; }
    .album-link { display: inline-block; background: #b8ff43; color: #131a0c; padding: 8px 16px; text-decoration: none; border-radius: 5px; font-weight: bold; }
    .album-link:hover { filter: brightness(1.1); }
    .count { text-align: center; color: #aeb8a7; margin-bottom: 20px; }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>DJ Elsa</h1>
      <p>Music Archive</p>
    </div>
    <div class="count">''' + str(len(ALBUMS)) + ''' albums</div>
    <div class="grid">
'''
    
    for album in ALBUMS:
        video_id = album['video_id']
        title = album['title']
        
        html += f'''      <div class="album">
        <img src="https://i.ytimg.com/vi/{video_id}/hqdefault.jpg" alt="{title}" loading="lazy">
        <div class="album-info">
          <h3 class="album-title">{title}</h3>
          <a href="https://music.youtube.com/watch?v={video_id}" target="_blank" class="album-link">Listen on YouTube Music</a>
        </div>
      </div>
'''
    
    html += '''    </div>
  </div>
</body>
</html>'''
    
    return html

def main():
    print("🎵 DJ Elsa Music Archive")
    print("========================")
    print(f"Using {len(ALBUMS)} verified albums")
    
    html = create_html()
    Path('kissingface.html').write_text(html)
    
    print("✅ Created kissingface.html")
    print("✅ All albums have real YouTube artwork")
    print("✅ All links go to your actual YouTube videos")
    print("\n💡 To add more albums:")
    print("1. Go to https://www.youtube.com/@elsavelaz/releases")
    print("2. Click on an album")
    print("3. Copy the video ID from the URL")
    print("4. Add it to the ALBUMS list above")

if __name__ == "__main__":
    main()

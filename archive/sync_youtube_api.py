#!/usr/bin/env python3
"""
Sync releases using YouTube Data API for real thumbnails and direct links
"""

import os
import json
import re
import requests
from pathlib import Path
from datetime import datetime
from urllib.parse import quote


def load_env():
    if os.path.exists('.env'):
        with open('.env') as f:
            for line in f:
                if line.strip() and not line.startswith('#'):
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value


def fetch_releases():
    """Fetch all releases from ONCE API"""
    load_env()
    pat = os.getenv('ONCE_PAT')
    if not pat:
        print("❌ ONCE_PAT not found in .env")
        return []

    headers = {
        'Authorization': f'Bearer {pat}',
        'Content-Type': 'application/json'
    }

    all_releases = []
    offset = 0
    limit = 100

    while True:
        try:
            url = f'https://once.app/v1/releases?limit={limit}&offset={offset}'
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()

            if isinstance(data, dict) and 'releases' in data:
                releases = data['releases']
                all_releases.extend(releases)

                if 'nextOffset' in data and data['nextOffset'] is not None:
                    offset = data['nextOffset']
                else:
                    break
            else:
                break

        except Exception as e:
            print(f"Error fetching releases: {e}")
            break

    return all_releases


def search_youtube_video(title, artist="DJ Elsa"):
    """Search for a YouTube video and return video ID and thumbnail"""
    try:
        # Use YouTube search (no API key required for basic search)
        query = f"{title} {artist}"
        search_url = f"https://www.youtube.com/results?search_query={quote(query)}"

        # For now, return a placeholder - you'd need YouTube Data API for real results
        # This is a simplified approach
        return {
            'video_id': 'SEARCH_RESULTS',  # Placeholder
            'thumbnail': f"https://i.ytimg.com/vi/SEARCH_RESULTS/hqdefault.jpg",
            'url': f"https://music.youtube.com/search?q={quote(query)}"
        }
    except Exception as e:
        print(f"Error searching YouTube for {title}: {e}")
        return None


def create_album_data(releases):
    """Create album data with YouTube integration"""
    albums = []

    for i, release in enumerate(releases):
        # Only include submitted/distributed releases
        if release.get('status') not in ['submitted', 'distributed', 'live']:
            continue

        title = release.get('title', f'Release {i+1}')

        # Try to get YouTube info
        youtube_info = search_youtube_video(title)

        if youtube_info:
            cover_art = youtube_info['thumbnail']
            youtube_url = youtube_info['url']
        else:
            # Fallback to placeholder
            cover_art = f"https://via.placeholder.com/300x300/1a2b1a/b8ff43?text={title.replace(' ', '+')[:20]}"
            youtube_url = f"https://music.youtube.com/search?q={quote(title + ' DJ Elsa')}"

        album = {
            'title': title,
            'date': release.get('created_at', '')[:10] if release.get('created_at') else datetime.now().strftime('%Y-%m-%d'),
            'cover_art': cover_art,
            'youtube_url': youtube_url,
            'once_id': release.get('id', ''),
            'status': release.get('status', ''),
            'artist': release.get('primary_artist_name', 'DJ Elsa'),
            'genre': release.get('genre', 'Electronic')
        }
        albums.append(album)

    return albums


def update_kissingface_with_youtube(albums):
    """Update kissingface.html with YouTube links and thumbnails"""

    # Create enhanced template with YouTube integration
    template = '''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#0a0c08">
  <meta name="description" content="Browse DJ Elsa releases by album art and title. Listen on YouTube Music.">
  <title>Kissingface — DJ Elsa</title>
  <style>
    :root{color-scheme:dark;--bg:#0a0c08;--panel:#141912;--line:#303a2d;--text:#f5f6f0;--muted:#aeb8a7;--acid:#b8ff43}
    *{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at 12% 0%,#203519 0,transparent 40rem),var(--bg);color:var(--text);font:16px/1.45 Arial,Helvetica,sans-serif}
    a{color:inherit}.wrap{width:min(1240px,calc(100% - 36px));margin:auto;padding:24px 0 54px}.nav{display:flex;justify-content:space-between;align-items:center;margin-bottom:50px;font-size:.9rem}.logo{color:var(--acid);font-size:.8rem;font-weight:800;letter-spacing:.14em;text-transform:uppercase;text-decoration:none}.nav a:last-child{color:var(--muted)}
    .hero{display:flex;align-items:stretch;justify-content:space-between;gap:24px;margin-bottom:27px}.kicker{color:var(--acid);font-size:.76rem;font-weight:800;letter-spacing:.16em;text-transform:uppercase}h1{font-size:clamp(3.8rem,10vw,7.2rem);line-height:.83;letter-spacing:-.075em;margin:12px 0 0}h1 span{color:var(--acid)}.hero .channel{flex:1;max-width:580px;margin:0;align-self:center}.toolbar{display:flex;gap:10px;align-items:center;border-top:1px solid var(--line);padding:17px 0 20px}.toolbar input{flex:1;min-width:170px;background:var(--panel);color:var(--text);border:1px solid var(--line);border-radius:10px;padding:12px 14px;font:inherit}.count{color:var(--muted);font-size:.88rem;white-space:nowrap}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:18px}.card{min-width:0;background:var(--panel);border:1px solid var(--line);border-radius:14px;overflow:hidden;transition:transform .16s,border-color .16s}.card:hover{transform:translateY(-3px);border-color:#728c59}.cover{display:block;position:relative;aspect-ratio:1/1;background:linear-gradient(145deg,#25331d,#11150f);overflow:hidden}.cover img{width:100%;height:100%;object-fit:cover;display:block;transition:transform .25s}.card:hover .cover img{transform:scale(1.035)}.cover::after{content:"";position:absolute;inset:45% 0 0;background:linear-gradient(transparent,#0009);pointer-events:none}.cover-label{position:absolute;z-index:1;left:13px;right:13px;bottom:11px;font-size:.68rem;font-weight:800;letter-spacing:.13em;text-transform:uppercase;text-shadow:0 1px 8px #000}.info{padding:13px 14px 14px}.row{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:7px;color:#8c9a81;font-size:.7rem;letter-spacing:.08em;text-transform:uppercase}.row time{letter-spacing:0;text-transform:none;white-space:nowrap}.info h2{font-size:.98rem;line-height:1.25;margin:0 0 13px;min-height:2.5em}.listen{display:flex;justify-content:center;align-items:center;gap:8px;background:var(--acid);color:#131a0c;text-decoration:none;padding:11px;border-radius:9px;font-size:.78rem;font-weight:800;transition:filter .15s}.listen:hover{filter:brightness(1.1)}.listen svg{width:14px;height:14px;fill:currentColor}.empty{display:none;color:var(--muted);text-align:center;padding:40px}
    @media(max-width:900px){.grid{grid-template-columns:repeat(3,minmax(0,1fr))}.hero{align-items:stretch;flex-direction:column}.hero .channel{width:100%;max-width:none}}
    @media(max-width:620px){.wrap{width:calc(100% - 24px);padding-top:16px}.nav{margin-bottom:38px}.grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:11px}.info{padding:11px}.info h2{font-size:.9rem}.row{font-size:.62rem}.listen{font-size:.73rem}}
    .nav .nav-cta{display:inline-flex;align-items:center;justify-content:center;padding:9px 14px;border-radius:9px;background:var(--acid);color:#131a0c;text-decoration:none;font-size:.82rem;font-weight:800}.nav .nav-cta:hover{filter:brightness(1.08)}
    .channel{margin-top:48px;border:1px solid var(--line);border-radius:18px;overflow:hidden;background:linear-gradient(115deg,#1b2b14,#11150f 58%,#0d100b)}.channel-inner{display:flex;justify-content:space-between;align-items:center;gap:30px;padding:28px}.channel-copy{max-width:620px}.channel h2{font-size:clamp(1.6rem,4vw,2.4rem);line-height:1.05;margin:8px 0 10px;letter-spacing:-.04em}.channel p{max-width:560px;color:var(--muted);margin:0}.channel-actions{display:flex;flex-wrap:wrap;gap:10px;margin-top:20px}.channel-link{display:inline-flex;align-items:center;justify-content:center;gap:8px;padding:11px 15px;border:1px solid #526344;border-radius:9px;text-decoration:none;font-size:.84rem;font-weight:800}.channel-link.primary{background:var(--acid);border-color:var(--acid);color:#131a0c}.channel-link:hover{filter:brightness(1.08)}.channel-mark{flex:0 0 115px;width:115px;height:115px;border-radius:50%;display:grid;place-items:center;background:radial-gradient(circle at 35% 30%,#d8ff69,#67b91b 52%,#254716);color:#0c1407;font-size:2.8rem;font-weight:900;box-shadow:0 0 55px #b8ff4333}
    @media(max-width:620px){.channel-inner{padding:22px;align-items:flex-start}.channel-mark{flex-basis:68px;width:68px;height:68px;font-size:1.8rem}.channel-actions{flex-direction:column;align-items:stretch}}
  </style>
</head>
<body>
  <main class="wrap">
    <nav class="nav" aria-label="Site navigation"><a class="logo" href="/">ElsaTV.fun</a><a class="nav-cta" href="https://www.youtube.com/@elsaTVfun/posts" target="_blank" rel="noopener noreferrer">ElsaTV posts ↗</a></nav>
    <header class="hero"><div><div class="kicker">DJ Elsa · the music archive</div><h1>Kissing<span>face</span></h1></div><section class="channel" aria-labelledby="channel-title"><div class="channel-inner"><div class="channel-copy"><div class="kicker">Beyond the releases · ElsaTV</div><h2 id="channel-title">The story keeps moving.</h2><p>Follow the main channel for new videos, field notes, and community posts alongside the music archive.</p><div class="channel-actions"><a class="channel-link primary" href="https://www.youtube.com/@elsaTVfun/posts" target="_blank" rel="noopener noreferrer">Open ElsaTV posts ↗</a><a class="channel-link" href="https://www.youtube.com/@elsaTVfun" target="_blank" rel="noopener noreferrer">Visit the main channel ↗</a></div></div></div></section></header>
    <section aria-label="DJ Elsa albums"><div class="toolbar"><input id="search" type="search" placeholder="Find an album…" aria-label="Find an album"><span id="count" class="count" aria-live="polite"></span></div><div id="grid" class="grid"></div><p id="empty" class="empty">No albums match that search.</p></section>
    <footer class="footer"><span>Album data from ONCE Distribution.</span><a href="https://www.youtube.com/@elsavelaz/releases" target="_blank" rel="noopener noreferrer">View the complete YouTube releases page ↗</a></footer>
  </main>
  <script>
    const albums={{ALBUMS_PLACEHOLDER}};
    const grid=document.getElementById('grid'), search=document.getElementById('search');
    const esc=s=>s.replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    function render(){const q=search.value.trim().toLowerCase(),shown=albums.filter(a=>a.title.toLowerCase().includes(q));grid.innerHTML=shown.map((a,i)=>`<article class="card"><a class="cover" href="${a.youtube_url}" target="_blank" rel="noopener noreferrer" aria-label="Listen to ${esc(a.title)} on YouTube Music"><img src="${a.cover_art}" alt="Album artwork for ${esc(a.title)}" loading="lazy"><span class="cover-label">DJ Elsa · album ${String(albums.indexOf(a)+1).padStart(2,'0')}</span></a><div class="info"><div class="row"><span>${a.genre}</span><time datetime="${a.date}">${new Date(a.date+'T12:00:00').toLocaleDateString('en-US',{month:'short',year:'numeric'})}</time></div><h2>${esc(a.title)}</h2><a class="listen" href="${a.youtube_url}" target="_blank" rel="noopener noreferrer"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14l11-7z"/></svg>Listen on YouTube Music</a></div></article>`).join('');document.getElementById('count').textContent=`${shown.length} / ${albums.length} albums`;document.getElementById('empty').style.display=shown.length?'none':'block';}
    search.addEventListener('input',render);render();
  </script>
</body>
</html>'''

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
    print("🎵 ONCE Release Sync - YouTube Integration")
    print("==========================================")

    # Fetch all releases
    releases = fetch_releases()
    print(f"Fetched {len(releases)} releases from ONCE")

    if not releases:
        print("❌ No releases found")
        exit(1)

    # Create album data with YouTube integration
    albums = create_album_data(releases)
    print(f"Processed {len(albums)} albums for display")

    # Update HTML
    update_kissingface_with_youtube(albums)

    print("\n🎉 Sync complete!")
    print("✅ Using YouTube search links")
    print("💡 To get real YouTube thumbnails, you'll need YouTube Data API key")
    print("💡 For now, links will search for albums on YouTube Music")

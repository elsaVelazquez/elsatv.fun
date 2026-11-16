#!/usr/bin/env python3
"""Collect album and song links without publishing or using ONCE.

Run from the website repository root:

  venv/bin/python -m pip install ytmusicapi==1.12.3
  venv/bin/python collect_music_links.py

Reads lore/albums.json and writes a separate lore/music_links_enriched.json.
Use --input and --output to choose different paths. The existing website,
albums.json, manual_links.json and publishing scripts are not changed.

YouTube Music uses the public DJ Elsa artist catalogue and checks the album's
actual track list. Apple uses the public iTunes lookup API. Spotify's public
artist page gives a limited selection; its official search API additionally
needs SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET in the environment. Without
credentials, Spotify links beyond the public selection may remain null.
Never put credentials in this file, the JSON output, or a public repository.

Album titles, song titles, durations, and available song IDs are compared.
When the result is unclear, the relevant links stay null instead of being
guessed. Existing input links are hints, not authoritative matches.
"""

import argparse
import base64
import concurrent.futures
import json
import os
import re
import sys
import tempfile
import threading
import time
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen


YOUTUBE_ARTIST_ID = "UC8p2YZheQLKVxMmhENGmDdQ"
APPLE_ARTIST_ID = "415547530"
SPOTIFY_ARTIST_ID = "27NhC9Ct23OhR441IZH6KY"
MARKET = "US"
USER_AGENT = "ElsaTV-Music-Link-Collector/1.0 (+https://elsatv.fun)"
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
ALBUM_ID = re.compile(r"^OLAK5uy_[A-Za-z0-9_-]+$")
_LOCAL = threading.local()


def request_json(url, headers=None, data=None):
    request = Request(url, data=data, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def get_yt_client():
    if not hasattr(_LOCAL, "yt"):
        from ytmusicapi import YTMusic
        _LOCAL.yt = YTMusic()
    return _LOCAL.yt


def strict_name(value):
    value = unicodedata.normalize("NFKC", str(value or ""))
    # Apple appends - EP or - Single; both services add featured-artist tags.
    value = re.sub(r"\s*[\[(]\s*(?:feat(?:uring)?|ft)\.?\s+[^\])]*[\])]", "", value, flags=re.I)
    value = re.sub(r"\s+-\s*(?:Single|EP)\s*$", "", value, flags=re.I)
    return "".join(c for c in value.casefold() if c.isalnum())


def loose_name(value):
    # Treat a version as a candidate only; track identity/duration must decide.
    value = re.sub(
        r"\s*[\[(](?:deluxe(?:\s+edition)?|[^\])]*\b(?:version|mix|remix|spoken|remaster(?:ed)?)\b[^\])]*|vortex[^\])]*)[\])]",
        "", str(value or ""), flags=re.I,
    )
    value = re.sub(r"\s+-\s*(?:remix|spoken|remaster(?:ed)?|[^-]*\bversion)\s*$", "", value, flags=re.I)
    return strict_name(value)


def same_name(a, b):
    if not a or not b:
        return False
    return strict_name(a) == strict_name(b) or loose_name(a) == loose_name(b)


def seconds(value):
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str) and re.fullmatch(r"\d+(?::\d{2}){1,2}", value):
        result = 0
        for part in value.split(":"):
            result = result * 60 + int(part)
        return result
    return None


def hint_video(url):
    if not isinstance(url, str):
        return None
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if host not in {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be", "www.youtu.be"}:
        return None
    candidate = parsed.path.strip("/").split("/")[0] if host.endswith("youtu.be") else parse_qs(parsed.query).get("v", [""])[0]
    return candidate if VIDEO_ID.fullmatch(candidate) else None


def item_title(item):
    return item.get("title") or item.get("trackName") or item.get("name") or ""


def item_duration(item):
    if item.get("trackTimeMillis") is not None:
        return round(item["trackTimeMillis"] / 1000)
    if item.get("duration_ms") is not None:
        return round(item["duration_ms"] / 1000)
    return seconds(item.get("duration_seconds") or item.get("duration"))


def best_cover(album):
    choices = [t for t in (album.get("thumbnails") or [])
               if isinstance(t, dict) and str(t.get("url") or "").startswith("https://")]
    if not choices:
        return None
    return max(choices, key=lambda t: (t.get("width") or 0) * (t.get("height") or 0))["url"]


def match_tracks(source_songs, tracks):
    """Match by name, with video IDs and duration as additional evidence."""
    used = set()
    matches = {}
    evidence = 0
    for index, source in enumerate(source_songs):
        title = source.get("song_name") or ""
        hint = hint_video(source.get("youtube_link"))
        length = seconds(source.get("duration"))
        candidates = []
        for t_index, track in enumerate(tracks):
            if t_index in used:
                continue
            candidate_title = item_title(track)
            track_length = item_duration(track)
            difference = abs(length - track_length) if length is not None and track_length is not None else None
            exact_name = strict_name(title) == strict_name(candidate_title)
            close_name = False
            if not same_name(title, candidate_title):
                left, right = loose_name(title), loose_name(candidate_title)
                close_name = bool(min(len(left), len(right)) >= 10 and difference is not None
                                  and difference <= 3 and SequenceMatcher(None, left, right).ratio() >= 0.96)
                if not close_name:
                    continue
            hint_match = bool(hint and track.get("videoId") == hint)
            # A supplied link can be wrong, even when it names another version
            # of the same song. Duration prevents it from overriding that evidence.
            if difference is not None and difference > 8:
                continue
            score = (10 if exact_name else 3 if close_name else 5) + (30 if hint_match else 0)
            if difference is not None:
                score += 5 if difference <= 2 else 3 if difference <= 5 else 0
                if difference > 30 and not hint_match:
                    score -= 5
            candidates.append((score, t_index, hint_match))
        candidates.sort(reverse=True)
        if not candidates or (len(candidates) > 1 and candidates[0][0] == candidates[1][0]):
            continue
        score, selected, hint_match = candidates[0]
        used.add(selected)
        matches[index] = selected
        evidence += score
    return matches, evidence


def choose_album(source, options):
    """Choose only a title-compatible album supported by its actual tracks."""
    name = source.get("album_name") or ""
    songs = source.get("songs") or []
    ranked = []
    for album in options:
        if not same_name(name, album.get("title") or ""):
            continue
        matches, evidence = match_tracks(songs, album.get("tracks") or [])
        # A title match alone is insufficient for a release with known songs.
        if songs and (not matches or len(matches) * 2 < len(songs)):
            continue
        album_score = 5 if strict_name(name) == strict_name(album.get("title") or "") else 0
        # An exact date helps distinguish re-releases with identical names and
        # songs. An absent or different date never rules out a valid match.
        source_date = str(source.get("date_published") or "")[:10]
        release_date = str(album.get("release_date") or "")[:10]
        if source_date and source_date == release_date:
            album_score += 4
        ranked.append((evidence + album_score, album, matches))
    ranked.sort(key=lambda x: x[0], reverse=True)
    if not ranked or (len(ranked) > 1 and ranked[0][0] == ranked[1][0]):
        return None, {}
    return ranked[0][1], ranked[0][2]


def cross_platform_reference(source, youtube, youtube_matches):
    """Keep input names in output, but use verified version names to match stores."""
    if not youtube:
        return source
    reference = dict(source)
    reference["album_name"] = youtube.get("title") or source.get("album_name")
    songs = []
    for index, song in enumerate(source.get("songs") or []):
        item = dict(song)
        if index in youtube_matches:
            item["song_name"] = youtube["tracks"][youtube_matches[index]].get("title") or item.get("song_name")
        songs.append(item)
    reference["songs"] = songs
    return reference


def youtube_catalog(source_albums, worker_count):
    client = get_yt_client()
    artist = client.get_artist(YOUTUBE_ARTIST_ID)
    releases = []
    for kind in ("albums", "singles"):
        group = artist.get(kind) or {}
        if group.get("browseId") and group.get("params"):
            releases.extend(client.get_artist_albums(group["browseId"], group["params"], limit=None))
        else:
            releases.extend(group.get("results") or [])
    browses = {}
    for release in releases:
        title = release.get("title") or ""
        browse_id = release.get("browseId")
        if browse_id and any(same_name(a.get("album_name"), title) for a in source_albums):
            browses[browse_id] = release

    def fetch(browse_id):
        try:
            data = get_yt_client().get_album(browse_id)
            return browse_id, {
                "title": data.get("title") or browses[browse_id].get("title") or "",
                "browse_id": browse_id,
                "playlist_id": data.get("audioPlaylistId") or browses[browse_id].get("playlistId"),
                "cover_art": best_cover(data),
                "tracks": data.get("tracks") or [],
            }, None
        except Exception as exc:
            return browse_id, None, f"{type(exc).__name__}: {exc}"

    result = {}
    errors = []
    print(f"YouTube Music: checking {len(browses)} candidate releases...", file=sys.stderr, flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as pool:
        futures = [pool.submit(fetch, browse_id) for browse_id in browses]
        for done, future in enumerate(concurrent.futures.as_completed(futures), 1):
            browse_id, album, error = future.result()
            if album:
                result[browse_id] = album
            elif error:
                errors.append(f"{browse_id}: {error}")
            if done % 20 == 0 or done == len(futures):
                print(f"  YouTube Music releases checked: {done}/{len(futures)}", file=sys.stderr, flush=True)
    return result, errors


def youtube_hint_albums(source, available):
    """Find an omitted release through a song, but verify song and artist."""
    songs = source.get("songs") or []
    hints = [hint_video(s.get("youtube_link")) for s in songs]
    hints.append(hint_video(source.get("youtube_link")))
    known = set()
    new = []
    for video in hints:
        if not video or video in known:
            continue
        known.add(video)
        try:
            watch = get_yt_client().get_watch_playlist(videoId=video, limit=1)
            track = next((t for t in watch.get("tracks", []) if t.get("videoId") == video), None)
            if not track or not any(same_name(s.get("song_name"), item_title(track)) for s in songs):
                continue
            artists = track.get("artists") or []
            if not any(a.get("id") == YOUTUBE_ARTIST_ID or strict_name(a.get("name")) == strict_name("DJ Elsa") for a in artists if isinstance(a, dict)):
                continue
            album = track.get("album") or {}
            browse_id = album.get("id") if isinstance(album, dict) else None
            if not browse_id or not same_name(source.get("album_name"), album.get("name")):
                continue
            if browse_id not in available:
                details = get_yt_client().get_album(browse_id)
                available[browse_id] = {"title": details.get("title") or album.get("name"), "browse_id": browse_id,
                                        "playlist_id": details.get("audioPlaylistId"), "cover_art": best_cover(details),
                                        "tracks": details.get("tracks") or []}
            new.append(available[browse_id])
        except Exception as exc:
            print(f"  Could not check hint for {source.get('album_name')}: {type(exc).__name__}", file=sys.stderr, flush=True)
    return new


def apple_catalog(source_albums):
    params = urlencode({"id": APPLE_ARTIST_ID, "entity": "album", "country": MARKET, "limit": 200})
    result = request_json("https://itunes.apple.com/lookup?" + params)
    collections = {}
    for item in result.get("results", []):
        if item.get("wrapperType") != "collection" or not item.get("collectionId"):
            continue
        if any(same_name(a.get("album_name"), item.get("collectionName")) for a in source_albums):
            collections[str(item["collectionId"])] = item
    ids = list(collections)
    result = []
    errors = []
    print(f"Apple Music: checking {len(ids)} candidate releases in batches...", file=sys.stderr, flush=True)
    for start in range(0, len(ids), 10):
        group = ids[start:start + 10]
        params = urlencode({"id": ",".join(group), "entity": "song", "country": MARKET, "limit": 200})
        try:
            data = request_json("https://itunes.apple.com/lookup?" + params)
            grouped = defaultdict(list)
            for track in data.get("results", []):
                if track.get("wrapperType") == "track" and track.get("kind") == "song":
                    grouped[str(track.get("collectionId"))].append(track)
            for collection_id in group:
                info = collections[collection_id]
                tracks = grouped[collection_id]
                # Do not assume a missing/truncated API response is a complete album.
                if info.get("trackCount") and len(tracks) < int(info["trackCount"]):
                    errors.append(f"Apple returned incomplete tracks for {info.get('collectionName')}")
                    continue
                result.append({"title": info.get("collectionName") or "", "album_link": info.get("collectionViewUrl"),
                               "release_date": info.get("releaseDate"), "tracks": tracks})
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            errors.append(f"Apple batch {start // 10 + 1}: {type(exc).__name__}: {exc}")
        print(f"  Apple release candidates checked: {min(start + len(group), len(ids))}/{len(ids)}", file=sys.stderr, flush=True)
    return result, errors


class SpotifyClient:
    def __init__(self, client_id, client_secret):
        credential = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        payload = urlencode({"grant_type": "client_credentials"}).encode()
        result = request_json("https://accounts.spotify.com/api/token", {"Authorization": f"Basic {credential}"}, payload)
        self.token = result["access_token"]

    def get(self, url, params=None):
        if params:
            url += "?" + urlencode(params)
        return request_json(url, {"Authorization": f"Bearer {self.token}"})

    def candidates(self, album_name):
        query = f'album:"{album_name}" artist:"DJ Elsa"'
        results = self.get("https://api.spotify.com/v1/search", {"q": query, "type": "album", "market": MARKET, "limit": 10})
        albums = []
        for info in (results.get("albums") or {}).get("items", []):
            if not same_name(album_name, info.get("name")):
                continue
            if not any(strict_name(a.get("name")) == strict_name("DJ Elsa") for a in info.get("artists", [])):
                continue
            if not info.get("id"):
                continue
            url = f"https://api.spotify.com/v1/albums/{info['id']}/tracks"
            page = self.get(url, {"market": MARKET, "limit": 50})
            tracks = list(page.get("items") or [])
            while page.get("next"):
                next_url = page["next"]
                if urlparse(next_url).hostname != "api.spotify.com":
                    raise ValueError("Unexpected Spotify pagination URL")
                page = self.get(next_url)
                tracks.extend(page.get("items") or [])
            albums.append({"title": info.get("name") or "", "album_link": (info.get("external_urls") or {}).get("spotify"),
                           "release_date": info.get("release_date"), "tracks": tracks})
        return albums


class _MetadataParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = {}

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "meta":
            return
        attrs = dict(attrs)
        key = attrs.get("name") or attrs.get("property")
        if key and attrs.get("content"):
            self.tags.setdefault(key, []).append(attrs["content"])


def spotify_page(url):
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def spotify_embed_entity(kind, item_id):
    html = spotify_page(f"https://open.spotify.com/embed/{kind}/{item_id}")
    found = re.search(r'<script\s+id="__NEXT_DATA__"\s+type="application/json">(.*?)</script>', html, re.S)
    if not found:
        raise ValueError("Spotify did not return public embed metadata")
    return json.loads(found.group(1))["props"]["pageProps"]["state"]["data"]["entity"]


def spotify_public_catalog(source_albums):
    """Discover a limited selection from the artist's public top-tracks page."""
    artist = spotify_embed_entity("artist", SPOTIFY_ARTIST_ID)
    if artist.get("uri") != f"spotify:artist:{SPOTIFY_ARTIST_ID}":
        raise ValueError("Spotify returned a different artist")
    wanted = [s for a in source_albums for s in (a.get("songs") or [])]
    top_tracks = []
    for track in artist.get("trackList") or []:
        uri = track.get("uri") or ""
        if not re.fullmatch(r"spotify:track:[A-Za-z0-9]{22}", uri):
            continue
        comparable = {"name": track.get("title"), "duration_ms": track.get("duration")}
        if any(match_tracks([song], [comparable])[0] for song in wanted):
            top_tracks.append(uri.rsplit(":", 1)[1])

    def track_album_id(track_id):
        try:
            parser = _MetadataParser()
            parser.feed(spotify_page(f"https://open.spotify.com/track/{track_id}"))
            for url in parser.tags.get("music:album", []):
                match = re.fullmatch(r"https://open\.spotify\.com/album/([A-Za-z0-9]{22})(?:\?.*)?", url)
                if match:
                    return match.group(1)
        except (HTTPError, URLError, TimeoutError, OSError, ValueError):
            return None
        return None

    print(f"Spotify: checking {len(top_tracks)} public top tracks...", file=sys.stderr, flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        album_ids = sorted({x for x in pool.map(track_album_id, top_tracks) if x})
    albums = []
    for album_id in album_ids:
        try:
            entity = spotify_embed_entity("album", album_id)
            if entity.get("uri") != f"spotify:album:{album_id}":
                continue
            tracks = []
            for item in entity.get("trackList") or []:
                uri = item.get("uri") or ""
                if re.fullmatch(r"spotify:track:[A-Za-z0-9]{22}", uri):
                    tracks.append({"name": item.get("title"), "duration_ms": item.get("duration"),
                                   "external_urls": {"spotify": "https://open.spotify.com/track/" + uri.rsplit(":", 1)[1]}})
            albums.append({"title": entity.get("title") or entity.get("name") or "",
                           "album_link": f"https://open.spotify.com/album/{album_id}",
                           "release_date": (entity.get("releaseDate") or {}).get("isoString"), "tracks": tracks})
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            print(f"  Spotify album lookup incomplete: {type(exc).__name__}", file=sys.stderr, flush=True)
    return albums


def output_songs(source_songs, youtube, youtube_matches, apple, apple_matches, spotify, spotify_matches):
    result = []
    for index, source in enumerate(source_songs):
        song = {k: v for k, v in source.items() if k not in {"youtube_link", "album_link"}}
        song.update({"youtube_song_link": None, "youtubemusic_song_link": None, "spotify_song_link": None, "apple_song_link": None})
        if youtube and index in youtube_matches:
            video = youtube["tracks"][youtube_matches[index]].get("videoId")
            if isinstance(video, str) and VIDEO_ID.fullmatch(video):
                song["youtube_song_link"] = f"https://www.youtube.com/watch?v={video}"
                song["youtubemusic_song_link"] = f"https://music.youtube.com/watch?v={video}"
        if apple and index in apple_matches:
            song["apple_song_link"] = apple["tracks"][apple_matches[index]].get("trackViewUrl")
        if spotify and index in spotify_matches:
            song["spotify_song_link"] = (spotify["tracks"][spotify_matches[index]].get("external_urls") or {}).get("spotify")
        result.append(song)
    # Add songs present on the matched YouTube release but missing from the
    # input, so the result contains the complete track list when available.
    if youtube:
        used_youtube = set(youtube_matches.values())
        used_apple = set(apple_matches.values())
        used_spotify = set(spotify_matches.values())
        for track_index, track in enumerate(youtube.get("tracks") or []):
            if track_index in used_youtube or not track.get("title"):
                continue
            source = {"track_number": track_index + 1, "song_name": track["title"], "duration": track.get("duration")}
            added = output_songs([source], None, {}, None, {}, None, {})[0]
            video = track.get("videoId")
            if isinstance(video, str) and VIDEO_ID.fullmatch(video):
                added["youtube_song_link"] = f"https://www.youtube.com/watch?v={video}"
                added["youtubemusic_song_link"] = f"https://music.youtube.com/watch?v={video}"
            for platform, provider, used in (("apple", apple, used_apple), ("spotify", spotify, used_spotify)):
                if not provider:
                    continue
                remaining = [(i, t) for i, t in enumerate(provider["tracks"]) if i not in used]
                matched, _ = match_tracks([source], [t for _, t in remaining])
                if 0 in matched:
                    actual = remaining[matched[0]][0]
                    used.add(actual)
                    if platform == "apple":
                        added["apple_song_link"] = provider["tracks"][actual].get("trackViewUrl")
                    else:
                        added["spotify_song_link"] = (provider["tracks"][actual].get("external_urls") or {}).get("spotify")
            result.append(added)
    return result


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False, prefix=".music_links_", suffix=".tmp") as f:
            temp_name = f.name
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(temp_name, path)
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path, default=Path("lore/albums.json"))
    parser.add_argument("--output", type=Path, default=Path("lore/music_links_enriched.json"))
    parser.add_argument("--workers", type=int, default=3, help="YouTube lookups in parallel (default 3; max 5)")
    parser.add_argument("--limit", type=int, help="Process only the first N albums, for a small trial")
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error("The output must be a different file from the input.")
    protected = {Path(p).resolve() for p in (
        "lore/albums.json", "lore/manual_links.json", "lore/yt_link_cache.json",
        "lore/songs.json", "kissingface.html", "FINAL_SYNC.py",
    )}
    if args.output.resolve() in protected:
        parser.error("Choose a separate output file; the website and existing data are protected.")
    if args.output.suffix.lower() != ".json":
        parser.error("The output filename must end in .json.")
    if args.workers < 1 or args.workers > 5:
        parser.error("--workers must be between 1 and 5.")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive.")
    try:
        source = json.loads(args.input.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Could not read {args.input}: {exc}", file=sys.stderr)
        return 2
    if not isinstance(source, dict) or not isinstance(source.get("albums"), list):
        print("Input must be a JSON object with an albums list.", file=sys.stderr)
        return 2
    albums = source["albums"][:args.limit] if args.limit else source["albums"]
    try:
        import ytmusicapi  # noqa: F401
    except ImportError:
        print("Install ytmusicapi first: venv/bin/python -m pip install ytmusicapi==1.12.3", file=sys.stderr)
        return 2

    issues = []
    try:
        youtube, yt_errors = youtube_catalog(albums, args.workers)
        issues.extend(yt_errors)
        yt_status = "partial" if yt_errors else "complete"
    except Exception as exc:
        youtube = {}
        yt_status = "failed"
        issues.append(f"YouTube Music catalogue: {type(exc).__name__}: {exc}")
    try:
        apple, apple_errors = apple_catalog(albums)
        issues.extend(apple_errors)
        apple_status = "partial" if apple_errors else "complete"
    except Exception as exc:
        apple = []
        apple_status = "failed"
        issues.append(f"Apple Music catalogue: {type(exc).__name__}: {exc}")

    spotify_client = None
    spotify_cache = {}
    try:
        spotify_public = spotify_public_catalog(albums)
        spotify_status = "public_top_tracks_only"
    except Exception as exc:
        spotify_public = []
        spotify_status = "public_lookup_failed"
        issues.append(f"Spotify public lookup: {type(exc).__name__}")
    client_id = os.environ.get("SPOTIFY_CLIENT_ID")
    client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET")
    if client_id and client_secret:
        try:
            spotify_client = SpotifyClient(client_id, client_secret)
            spotify_status = "authenticated_search"
        except Exception as exc:
            spotify_status = "public_only_spotify_authorization_failed"
            issues.append(f"Spotify authorization: {type(exc).__name__}")

    output = []
    duplicate_names = Counter(strict_name(a.get("album_name")) for a in albums)
    for index, source_album in enumerate(albums, 1):
        name = source_album.get("album_name") or ""
        source_songs = source_album.get("songs") or []
        if duplicate_names[strict_name(name)] > 1 and yt_status != "failed":
            # The artist page may list only one of several versions with the
            # same name. Verify each source song before choosing a release.
            youtube_hint_albums(source_album, youtube)
        options = [a for a in youtube.values() if same_name(name, a.get("title"))]
        yt_album, yt_matches = choose_album(source_album, options)
        if yt_album is None and yt_status != "failed":
            youtube_hint_albums(source_album, youtube)
            options = [a for a in youtube.values() if same_name(name, a.get("title"))]
            yt_album, yt_matches = choose_album(source_album, options)
        reference = cross_platform_reference(source_album, yt_album, yt_matches)
        apple_album, apple_matches = choose_album(reference, apple)
        spotify_options = [a for a in spotify_public if same_name(name, a.get("title"))]
        spotify_album, spotify_matches = choose_album(reference, spotify_options)
        if spotify_client is not None:
            try:
                key = strict_name(name)
                if key not in spotify_cache:
                    spotify_cache[key] = spotify_client.candidates(name)
                known_urls = {a.get("album_link") for a in spotify_options}
                spotify_options.extend(a for a in spotify_cache[key] if a.get("album_link") not in known_urls)
                spotify_album, spotify_matches = choose_album(reference, spotify_options)
            except HTTPError as exc:
                spotify_status = "partial"
                issues.append(f"Spotify lookup for {name}: HTTP {exc.code}")
                if exc.code in (401, 403, 429):
                    # Avoid repeated unauthorized/rate-limited requests.
                    spotify_client = None
            except Exception as exc:
                spotify_status = "partial"
                issues.append(f"Spotify lookup for {name}: {type(exc).__name__}")

        album = {k: v for k, v in source_album.items() if k not in {"youtube_link", "album_link", "songs"}}
        album.update({"youtube_album_link": None, "youtubemusic_album_link": None, "spotify_album_link": None, "apple_album_link": None})
        if yt_album:
            if yt_album.get("cover_art"):
                album["cover_art"] = yt_album["cover_art"]
            playlist_id = yt_album.get("playlist_id")
            if isinstance(playlist_id, str) and ALBUM_ID.fullmatch(playlist_id):
                album["youtube_album_link"] = f"https://www.youtube.com/playlist?list={playlist_id}"
                album["youtubemusic_album_link"] = f"https://music.youtube.com/playlist?list={playlist_id}"
            elif yt_album.get("browse_id"):
                album["youtubemusic_album_link"] = f"https://music.youtube.com/browse/{yt_album['browse_id']}"
        if apple_album:
            album["apple_album_link"] = apple_album.get("album_link")
        if spotify_album:
            album["spotify_album_link"] = spotify_album.get("album_link")
        album["songs"] = output_songs(source_songs, yt_album, yt_matches, apple_album, apple_matches, spotify_album, spotify_matches)
        output.append(album)
        if index % 10 == 0 or index == len(albums):
            print(f"Matched albums: {index}/{len(albums)}", file=sys.stderr, flush=True)

    song_list = [song for album in output for song in album["songs"]]
    counts = {key: sum(bool(item.get(key)) for item in output) for key in ("youtube_album_link", "youtubemusic_album_link", "spotify_album_link", "apple_album_link")}
    counts.update({key: sum(bool(item.get(key)) for item in song_list) for key in ("youtube_song_link", "youtubemusic_song_link", "spotify_song_link", "apple_song_link")})
    result = {"generated_at": datetime.now(timezone.utc).isoformat(), "source_generated_at": source.get("generated_at"),
              "album_count": len(output), "song_count": len(song_list), "lookup_status": {"youtube_music": yt_status, "apple_music": apple_status, "spotify": spotify_status},
              "link_counts": counts, "issues": issues, "albums": output}
    try:
        atomic_json(args.output, result)
    except OSError as exc:
        print(f"Could not write {args.output}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"output": str(args.output), "album_count": len(output), "song_count": len(song_list), "lookup_status": result["lookup_status"], "link_counts": counts, "issues": len(issues)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

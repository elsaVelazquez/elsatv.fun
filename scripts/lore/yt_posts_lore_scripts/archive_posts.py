#!/usr/bin/env python3
"""
archive_posts.py — pull every YouTube Community post (text + images) and keep a
local, self-contained copy.

    venv/bin/python scripts/lore/yt_posts_lore_scripts/archive_posts.py
    venv/bin/python archive_posts.py --channel UCvjxv_x4chfG4c1yeNb7-vw
    venv/bin/python archive_posts.py --no-images        # metadata only
    venv/bin/python archive_posts.py --full             # ignore what we have

INCREMENTAL BY DEFAULT
----------------------
A normal run merges into the index.json that is already on disk: posts we
already have are kept exactly as they are, new posts are added on top, and
the image download stops at the first post id we recognise (the feed is
newest-first, so everything past that point is already archived). That means
a daily run costs one page of the feed and a handful of images instead of
1,617 re-downloads.

Nothing is ever deleted by a normal run. If a post disappears from YouTube it
stays in the archive — that is the whole point of an archive. Use --full when
you deliberately want to rebuild the corpus from scratch.

Writes, under lore/posts/:

    index.json          every post: id, published, text, hashtags, image files,
                        original image URLs, like count, post URL
    posts.md            the same thing as one readable document, newest first
    images/<postid>_<n>.jpg

Why this exists: if the channel is ever lost, the writing and the images are
still here, in a format that does not depend on YouTube. The JSON is the
machine-readable corpus; posts.md is what a human reads.

How: a channel post page embeds its whole first page as `ytInitialData`, so one
GET of /@handle/posts gets the first batch with no API key and no login.
Scrolling further is a POST to youtubei/v1/browse with a continuation token,
also lifted from that same JSON.
"""
import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE = 'https://www.youtube.com'
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0 Safari/537.36')
HEADERS = {'User-Agent': UA, 'Accept-Language': 'en-US,en;q=0.9'}

# The pipeline (build_day_index.py, stamp_images.py, ocr_images.py, …) reads
# lore/YTelsaTVposts/. A fresh run must write there, not to a second folder.
OUT = Path('lore/YTelsaTVposts')
IMAGES = OUT / 'images'

# The browse endpoint wants the public web API key that the page itself uses.
KEY_RE = re.compile(r'"INNERTUBE_API_KEY":"([^"]+)"')


# --------------------------------------------------------------------------- #
def walk(obj, key, out=None):
    """Collect every value stored under `key`, at any depth."""
    if out is None:
        out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key:
                out.append(v)
            walk(v, key, out)
    elif isinstance(obj, list):
        for v in obj:
            walk(v, key, out)
    return out


def initial_data(html):
    m = re.search(r'var ytInitialData = (\{.*?\});</script>', html, re.S)
    if not m:
        m = re.search(r'ytInitialData"\]\s*=\s*(\{.*?\});', html, re.S)
    if not m:
        raise SystemExit('could not find ytInitialData — YouTube changed the page '
                         'or served a consent/bot wall')
    return json.loads(m.group(1))


def runs_text(node):
    """Join a YouTube runs/simpleText block into plain text."""
    if not isinstance(node, dict):
        return ''
    if 'simpleText' in node:
        return node['simpleText']
    return ''.join(r.get('text', '') for r in node.get('runs', []))


def best_thumbnail(thumbs):
    """Largest square thumbnail, with the crop/scale params removed so we get
    the full image rather than a centre-cropped square."""
    if not thumbs:
        return ''
    t = max(thumbs, key=lambda x: x.get('width', 0))
    url = t.get('url', '')
    # yt3.ggpht.com/...=s640-c-fcrop64=...-rw-nd-v1  ->  =s0
    return re.sub(r'=s\d+.*$', '=s0', url)


def post_record(node):
    """Turn a backstagePostRenderer into a flat, readable record."""
    text = runs_text(node.get('contentText'))
    post_id = node.get('postId', '')

    images = []
    att = node.get('backstageAttachment') or {}

    # single image
    single = att.get('backstageImageRenderer')
    if single:
        images.append(best_thumbnail(
            (single.get('image') or {}).get('thumbnails')))

    # carousel / multiple
    multi = att.get('postMultiImageRenderer') or {}
    for item in multi.get('images', []):
        r = item.get('backstageImageRenderer') or {}
        images.append(best_thumbnail((r.get('image') or {}).get('thumbnails')))

    # polls, videos, playlists etc. are noted but not parsed further
    attachment_kind = next((k for k in att if k.endswith('Renderer')), '')

    published = runs_text(node.get('publishedTimeText'))
    published_abs = runs_text(
        (node.get('publishedTimeText') or {}).get('accessibility', {})
        .get('accessibilityData', {}))
    likes = runs_text(node.get('voteCount'))

    return {
        'post_id': post_id,
        'published_text': published,
        # YouTube renders "2 days ago" instead of a timestamp. The
        # accessibility label holds the date; keeping it means a merge can
        # carry over the old spelling if the relative text changes.
        'published_abs': published_abs,
        'text': text.strip(),
        'hashtags': re.findall(r'#\w+', text),
        'image_urls': [u for u in images if u],
        'attachment_kind': attachment_kind,
        'like_count': likes,
        'url': f'{BASE}/post/{post_id}',
    }


def collect_posts(first_data, api_key, client_version, max_pages=200,
                  known=None, max_new=0):
    """Yield every post, following continuation tokens until exhausted.

    If `known` is a set of post ids we already have, stop paging as soon as a
    whole page adds nothing new — the feed is newest-first, so there is
    nothing below that we do not already hold. `max_new` puts a hard ceiling on
    how many new posts an incremental run will follow, for a dry run.
    """
    seen = set()

    def emit(data):
        for p in walk(data, 'backstagePostRenderer'):
            rec = post_record(p)
            if rec['post_id'] and rec['post_id'] not in seen:
                seen.add(rec['post_id'])
                yield rec

    first = list(emit(first_data))
    yield from first

    new_seen = len([p for p in first if not known or p['post_id'] not in known])

    # Already caught up: the first page is all we needed.
    if known and seen and not (seen - known):
        print(f'  first page is entirely known — no paging needed')
        return
    if max_new and new_seen >= max_new:
        print(f'  --max-new {max_new} reached on the first page')
        return

    for tok in [t.get('token') for t in walk(first_data, 'continuationCommand')]:
        if not tok:
            continue
        page = 0
        while tok and page < max_pages:
            page += 1
            payload = {'context': {'client': {
                'clientName': 'WEB', 'clientVersion': client_version,
                'hl': 'en', 'gl': 'US'}}, 'continuation': tok}
            try:
                r = requests.post(
                    f'{BASE}/youtubei/v1/browse?key={api_key}',
                    headers={**HEADERS, 'Content-Type': 'application/json'},
                    json=payload, timeout=60)
                r.raise_for_status()
                data = r.json()
            except Exception as e:
                print(f'  ⚠️  continuation failed: {e}')
                break

            before = len(seen)
            fresh = list(emit(data))
            yield from fresh
            if len(seen) == before:
                break
            new_seen += len([p for p in fresh
                             if not known or p['post_id'] not in known])
            if known and not ({r['post_id'] for r in fresh} - known):
                print(f'  page {page}: all known — stopping')
                break
            if max_new and new_seen >= max_new:
                print(f'  --max-new {max_new} reached on page {page}')
                break

            toks = [t.get('token') for t in walk(data, 'continuationCommand')]
            tok = toks[-1] if toks else None
            time.sleep(0.4)
        break  # first token chain is the post feed


# --------------------------------------------------------------------------- #
def download(url, dest):
    if dest.exists() and dest.stat().st_size > 0:
        return dest.stat().st_size
    try:
        r = requests.get(url, headers=HEADERS, timeout=90)
        r.raise_for_status()
        dest.write_bytes(r.content)
        return len(r.content)
    except Exception as e:
        print(f'    ⚠️  image failed: {e}')
        return 0


def write_markdown(posts):
    lines = ['# Community posts', '',
             f'_Archived {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC} — '
             f'{len(posts)} posts._', '']
    for p in posts:
        lines.append(f'## {p["published_text"] or "undated"}')
        lines.append('')
        lines.append(f'- id: `{p["post_id"]}`')
        lines.append(f'- link: {p["url"]}')
        if p['like_count']:
            lines.append(f'- likes: {p["like_count"]}')
        lines.append('')
        if p['text']:
            lines.append(p['text'])
            lines.append('')
        for f in p.get('image_files', []):
            lines.append(f'![{f}](images/{f})')
        if p.get('image_files'):
            lines.append('')
        lines.append('---')
        lines.append('')
    (OUT / 'posts.md').write_text('\n'.join(lines), encoding='utf-8')


def main():
    global OUT, IMAGES

    ap = argparse.ArgumentParser()
    ap.add_argument('--channel', default='@elsaTVfun',
                    help='handle like @elsaTVfun, or a UC… channel id')
    ap.add_argument('--posts-path', default='/posts')
    ap.add_argument('--no-images', action='store_true')
    ap.add_argument('--out', default=str(OUT))
    ap.add_argument('--full', action='store_true',
                    help='ignore the existing index.json and rescrape everything')
    ap.add_argument('--max-new', type=int, default=0,
                    help='stop paging after N new posts (0 = follow the feed '
                         'until it runs into posts we already hold)')
    ap.add_argument('--refresh-metadata', action='store_true',
                    help='also update like counts / relative "3 days ago" text '
                         'on posts we already have (never re-downloads images)')
    args = ap.parse_args()

    OUT = Path(args.out)
    IMAGES = OUT / 'images'
    OUT.mkdir(parents=True, exist_ok=True)

    url = f'{BASE}/{args.channel}{args.posts_path}'
    print(f'→ {url}')
    r = requests.get(url, headers=HEADERS, timeout=60)
    r.raise_for_status()
    html = r.text

    data = initial_data(html)
    key_m = KEY_RE.search(html)
    ver_m = re.search(r'"INNERTUBE_CLIENT_VERSION":"([^"]+)"', html)
    if not key_m or not ver_m:
        raise SystemExit(
            'could not read the API key / client version from the page')

    print(f'  posts on first page: {len(walk(data, "backstagePostRenderer"))}')

    # What we already hold, keyed by post id, in the order it is on disk.
    existing = {}
    index_path = OUT / 'index.json'
    if index_path.exists() and not args.full:
        try:
            old = json.loads(index_path.read_text())
            existing = {p['post_id']: p for p in old.get('posts', [])
                        if p.get('post_id')}
            print(f'  on disk already: {len(existing)} post(s)')
        except Exception as e:
            print(f'  ⚠️  could not read {index_path} ({e}) — rebuilding')
            existing = {}

    fetched = list(collect_posts(data, key_m.group(1), ver_m.group(1),
                                 known=set(existing) or None,
                                 max_new=args.max_new))
    fresh = [p for p in fetched if p['post_id'] not in existing]
    print(f'  seen in feed: {len(fetched)}, new: {len(fresh)}')
    if not fresh:
        print('  nothing new — index.json left as it is')
        if not args.refresh_metadata:
            return

    # A post we already hold can still have changed: likes go up, and
    # published_text is relative ("6 hours ago" -> "3 days ago"). Copy those
    # two fields across rather than re-fetching or re-downloading anything.
    refreshed = 0
    if args.refresh_metadata:
        for p in fetched:
            old = existing.get(p['post_id'])
            if not old:
                continue
            for k in ('published_text', 'like_count', 'published_abs'):
                if p.get(k) and p[k] != old.get(k):
                    old[k] = p[k]
                    refreshed += 1
        if refreshed:
            print(f'  metadata refreshed on {refreshed} field(s)')

    # Images are per-post-id, so anything not in `fresh` already has its files
    # on disk and must not be looked at again.
    todo = fresh
    if not args.no_images and todo:
        IMAGES.mkdir(parents=True, exist_ok=True)
        total_bytes = 0
        for i, p in enumerate(todo, 1):
            files = []
            for n, u in enumerate(p['image_urls'], 1):
                ext = '.jpg'
                dest = IMAGES / f'{p["post_id"]}_{n}{ext}'
                size = download(u, dest)
                if size:
                    files.append(dest.name)
                    total_bytes += size
            p['image_files'] = files
            if p['image_urls']:
                print(
                    f'  [{i}/{len(todo)}] {len(files)}/'
                    f'{len(p["image_urls"])} images')
        print(f'  images downloaded this run: {total_bytes / 1e6:.1f} MB')

    # New posts in feed order (newest first), then everything we already had
    # in the order it was on disk. Nothing already archived is dropped.
    fresh_ids = {f['post_id'] for f in fresh}
    kept = []
    for pid, p in existing.items():
        if pid in fresh_ids:
            continue
        # Older records have no absolute date; fall back to what they had.
        if not p.get('published_abs'):
            p['published_abs'] = p.get('published_text', '')
        kept.append(p)
    posts = fresh + kept

    payload = {
        'generated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'channel': args.channel,
        'post_count': len(posts),
        'image_count': sum(len(p.get('image_files', [])) for p in posts),
        'posts': posts,
    }
    (OUT / 'index.json').write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')
    write_markdown(posts)

    print(f'\n→ {OUT / "index.json"}')
    print(f'→ {OUT / "posts.md"}')
    print(f'  {len(posts)} posts ({len(fresh)} new, {refreshed} metadata '
          f'updates), {payload["image_count"]} images')


if __name__ == '__main__':
    main()

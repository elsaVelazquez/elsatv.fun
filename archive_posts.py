#!/usr/bin/env python3
"""
archive_posts.py — pull every YouTube Community post (text + images) and keep a
local, self-contained copy.

    venv/bin/python archive_posts.py
    venv/bin/python archive_posts.py --channel UCvjxv_x4chfG4c1yeNb7-vw
    venv/bin/python archive_posts.py --no-images        # metadata only

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

OUT = Path('lore/posts')
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
    likes = runs_text(node.get('voteCount'))

    return {
        'post_id': post_id,
        'published_text': published,
        'text': text.strip(),
        'hashtags': re.findall(r'#\w+', text),
        'image_urls': [u for u in images if u],
        'attachment_kind': attachment_kind,
        'like_count': likes,
        'url': f'{BASE}/post/{post_id}',
    }


def collect_posts(first_data, api_key, client_version, max_pages=200):
    """Yield every post, following continuation tokens until exhausted."""
    seen = set()

    def emit(data):
        for p in walk(data, 'backstagePostRenderer'):
            rec = post_record(p)
            if rec['post_id'] and rec['post_id'] not in seen:
                seen.add(rec['post_id'])
                yield rec

    yield from emit(first_data)

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
            yield from emit(data)
            if len(seen) == before:
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

    posts = list(collect_posts(data, key_m.group(1), ver_m.group(1)))
    print(f'  total posts: {len(posts)}')

    if not args.no_images:
        IMAGES.mkdir(parents=True, exist_ok=True)
        total_bytes = 0
        for i, p in enumerate(posts, 1):
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
                    f'  [{i}/{len(posts)}] {len(files)}/{len(p["image_urls"])} images')
        print(f'  images on disk: {total_bytes / 1e6:.1f} MB')

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
    print(f'  {len(posts)} posts, '
          f'{payload["image_count"]} images')


if __name__ == '__main__':
    main()

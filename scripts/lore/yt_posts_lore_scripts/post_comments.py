#!/usr/bin/env python3
"""
post_comments.py — fetch the comments on each archived post.

    venv/bin/python scripts/lore/yt_posts_lore_scripts/post_comments.py --limit 10   # try a sample
    venv/bin/python scripts/lore/yt_posts_lore_scripts/post_comments.py              # all of them

Writes lore/YTelsaTVposts/comments.json:

    {
      "generated_at": "…",
      "posts": {
        "Ugkx…": [
          {"author": "@someone", "text": "fire", "likes": "2",
           "published": "3 days ago", "is_reply": false}
        ]
      }
    }

HOW YOUTUBE SERVES THESE (this is the fiddly part, hence the long comment)

  1. GET /post/<id> gives ytInitialData. The comment section is a
     `continuationItemRenderer` inside the page — it holds a token but no
     comments. Comments are never in the first payload.
  2. POST that token to /youtubei/v1/browse. WHAT YOU GET DEPENDS ON THE
     CLIENT the request claims to be:

         clientName WEB    -> commentViewModel nodes: ids, no text
         clientName MWEB   -> commentRenderer nodes: author, text, likes, time

     So MWEB is the one that matters, and it keeps this to ONE extra request
     per post. Do not switch it back to WEB.

Two requests per post that has comments, one per post that does not. Replies
are threaded behind a further token and are not chased here.

Pace: the sleep between requests is deliberate. Do not set it to 0.
"""
import argparse
import json
import re
import time
from datetime import datetime
from pathlib import Path

import requests

BASE = 'https://www.youtube.com'
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0 Safari/537.36')
HEADERS = {'User-Agent': UA, 'Accept-Language': 'en-US,en;q=0.9'}
JSON_HEADERS = {**HEADERS, 'Content-Type': 'application/json'}

ROOT = Path('lore/YTelsaTVposts')
INDEX = ROOT / 'index.json'
OUT = ROOT / 'comments.json'

# MWEB is the client that returns comment text; see the docstring.
MWEB_VERSION = '2.20240101.01.00'

KEY_RE = re.compile(r'"INNERTUBE_API_KEY":"([^"]+)"')
INIT_RE = re.compile(r'var ytInitialData = (\{.*?\});</script>', re.S)


# --------------------------------------------------------------------------- #
def walk(obj, key, out=None):
    """Every value stored under `key`, at any depth, in document order."""
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


def runs_text(node):
    """Flatten a runs/simpleText block to plain text."""
    if not isinstance(node, dict):
        return ''
    if 'simpleText' in node:
        return node['simpleText']
    return ''.join(r.get('text', '') for r in node.get('runs', []))


def api_key(html):
    """The public web API key the page itself uses, or None."""
    k = KEY_RE.search(html)
    return k.group(1) if k else None


def comment_token(data):
    """The token that opens the comment section, if the post has one."""
    # the comment section is the last itemSectionRenderer on a post page
    sections = walk(data, 'itemSectionRenderer')
    for sec in reversed(sections):
        for cont in sec.get('contents') or []:
            c = cont.get('continuationItemRenderer')
            if not c:
                continue
            ep = (c.get('continuationEndpoint') or {}).get(
                'continuationCommand')
            if ep and ep.get('token'):
                return ep['token']
    return None


def post_json(endpoint, key, version, token, timeout=45):
    """
    POST a continuation token to youtubei/v1/<endpoint>; returns json or {}.

    clientName MWEB is deliberate: WEB answers with commentViewModel (no text).
    The version string is fixed because MWEB accepts a generic one and it is
    not the version the desktop page advertises.
    """
    payload = {
        'context': {'client': {'clientName': 'MWEB', 'clientVersion': version,
                               'hl': 'en', 'gl': 'US'}},
        'continuation': token,
    }
    r = requests.post(f'{BASE}/youtubei/v1/{endpoint}?key={key}',
                      headers=JSON_HEADERS, json=payload, timeout=timeout)
    r.raise_for_status()
    return r.json()


# --------------------------------------------------------------------------- #
def renderer_to_dict(cr, is_reply=False):
    """commentRenderer -> the shape we store."""
    text = runs_text(cr.get('contentText')).strip()
    if not text:
        return None
    return {
        'author': runs_text(cr.get('authorText')),
        'text': text,
        'likes': runs_text(cr.get('voteCount')),
        'published': runs_text(cr.get('publishedTimeText')),
        'is_reply': is_reply,
    }


def fetch_comments(post_id, sleep=0.4):
    """
    All top-level comments on one post, as a list of dicts.

    Empty list means: genuinely no comments, or the post is inaccessible.
    Nothing is invented — an empty answer stays empty.
    """
    try:
        r = requests.get(f'{BASE}/post/{post_id}', headers=HEADERS, timeout=45)
        if r.status_code != 200:
            return []
        html = r.text
        key = api_key(html)
        if not key:
            return []
        m = INIT_RE.search(html)
        if not m:
            return []
        data = json.loads(m.group(1))
        token = comment_token(data)
        if not token:
            return []
        time.sleep(sleep)

        # step 2: with MWEB this already carries commentRenderer nodes
        j = post_json('browse', key, MWEB_VERSION, token)

        out = []
        for cr in walk(j, 'commentRenderer'):
            rec = renderer_to_dict(cr)
            if rec:
                out.append(rec)
        return out
    except Exception as e:
        print(f'    ⚠️  {post_id}: {e}')
        return []


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=0, help='first N posts only')
    ap.add_argument('--sleep', type=float, default=0.5,
                    help='seconds between requests — do not set to 0')
    ap.add_argument('--out', default=str(OUT))
    ap.add_argument('--refresh', action='store_true',
                    help='re-check posts already in comments.json')
    args = ap.parse_args()

    out_path = Path(args.out)
    existing = {}
    if out_path.exists():
        try:
            existing = json.loads(out_path.read_text()).get('posts', {})
        except Exception:
            existing = {}

    posts = json.loads(INDEX.read_text()).get('posts', [])
    ids = [p['post_id'] for p in posts if p.get('post_id')]
    if args.limit:
        ids = ids[:args.limit]
    print(f'→ checking {len(ids)} post(s) for comments')

    # An empty list is a real answer, but it is also what a failed run leaves
    # behind. --refresh re-checks everything instead of trusting the cache.
    result = dict(existing)
    total = 0
    for i, pid in enumerate(ids, 1):
        if pid in result and not args.refresh:
            total += len(result[pid])
            continue
        cs = fetch_comments(pid, sleep=args.sleep)
        result[pid] = cs
        total += len(cs)
        print(f'  [{i}/{len(ids)}] {pid} — {len(cs)} comment(s)')
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(
            {'generated_at': datetime.now().isoformat(timespec='seconds'),
             'posts': result}, indent=2, ensure_ascii=False))

    with_any = sum(1 for v in result.values() if v)
    print(f'\n→ {out_path}')
    print(f'  {total} comment(s) across {with_any} post(s)')


if __name__ == '__main__':
    main()

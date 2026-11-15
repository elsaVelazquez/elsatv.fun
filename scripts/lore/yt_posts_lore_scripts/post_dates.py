#!/usr/bin/env python3
"""
post_dates.py — resolve an ABSOLUTE publication date for every post id.

    venv/bin/python scripts/lore/yt_posts_lore_scripts/post_dates.py
    venv/bin/python scripts/lore/yt_posts_lore_scripts/post_dates.py --limit 5        # try it on a few

Why: the /@handle/posts feed only carries relative time ("6 hours ago"), which
is useless once the archive outlives the scrape. The individual post page
exposes a schema.org timestamp with second precision:

    "datePublished":"2026-11-12T17:50:44.488385-08:00"

One GET per post. That is the same rate a person browsing the channel makes,
and it is the endpoint the archive already builds URLs for, so it is a light
load. The sleep between requests is deliberate — do not remove it.

Writes lore/YTelsaTVposts/dates.json:

    {
      "generated_at": "…",
      "timezone": "America/Denver",
      "posts": {
        "Ugkx…": {
          "post_id": "Ugkx…",
          "published_iso": "2026-11-12T17:50:44.488385-08:00",
          "published_mst": "2026-11-12T18:50:44-07:00",
          "date_key": "2026-11-12",
          "display": "Nov 12, 2026 6:50 PM"
        }
      }
    }

`date_key` is the local (Mountain) calendar day and is the key the day index
groups on. `display` is what gets stamped onto the image.
"""
import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

BASE = 'https://www.youtube.com'
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0 Safari/537.36')
HEADERS = {'User-Agent': UA, 'Accept-Language': 'en-US,en;q=0.9'}

TZ = ZoneInfo('America/Denver')          # Mountain — handles MST/MDT for you
LOCAL_TZ = 'America/Denver'

ROOT = Path('lore/YTelsaTVposts')
INDEX = ROOT / 'index.json'
OUT = ROOT / 'dates.json'

DATE_RE = re.compile(r'"datePublished":"([^"]+)"')


# --------------------------------------------------------------------------- #
def load_post_ids(index_path=INDEX):
    """Every post id we archived, in archive order."""
    data = json.loads(index_path.read_text())
    return [p['post_id'] for p in data.get('posts', []) if p.get('post_id')]


def fetch_raw_date(post_id, retries=3):
    """The publisher's own timestamp string, or None. One GET per post."""
    url = f'{BASE}/post/{post_id}'
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=45)
            if r.status_code == 404:
                return None
            if r.status_code == 429:
                time.sleep(20 * (attempt + 1))
                continue
            r.raise_for_status()
            m = DATE_RE.search(r.text)
            return m.group(1) if m else None
        except Exception as e:
            if attempt == retries - 1:
                print(f'    ⚠️  {post_id}: {e}')
            time.sleep(3 * (attempt + 1))
    return None


def to_local(raw_iso):
    """'2026-11-12T17:50:44.488385-08:00' -> aware datetime in Mountain time."""
    dt = datetime.fromisoformat(raw_iso)
    return dt.astimezone(TZ)


def display_text(dt):
    """'Nov 12, 2026 6:50 PM' — no seconds, 12-hour clock."""
    return dt.strftime('%b %-d, %Y %-I:%M %p')


def build_record(post_id, raw_iso):
    local = to_local(raw_iso)
    return {
        'post_id': post_id,
        'published_iso': raw_iso,
        'published_mst': local.isoformat(timespec='seconds'),
        'date_key': local.strftime('%Y-%m-%d'),
        'display': display_text(local),
    }


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=0,
                    help='only do the first N posts (0 = all)')
    ap.add_argument('--sleep', type=float, default=0.4,
                    help='seconds between requests; 0.4 is polite, do not set 0')
    ap.add_argument('--out', default=str(OUT))
    args = ap.parse_args()

    ids = load_post_ids()
    if args.limit:
        ids = ids[:args.limit]
    print(f'→ resolving {len(ids)} post date(s)')

    out_path = Path(args.out)
    existing = {}
    if out_path.exists():
        try:
            existing = json.loads(out_path.read_text()).get('posts', {})
        except Exception:
            existing = {}

    posts = dict(existing)
    missing = 0
    for i, pid in enumerate(ids, 1):
        if pid in posts and posts[pid].get('date_key'):
            continue
        raw = fetch_raw_date(pid)
        if not raw:
            missing += 1
            print(f'  [{i}/{len(ids)}] {pid} — no date found')
            continue
        rec = build_record(pid, raw)
        posts[pid] = rec
        print(f'  [{i}/{len(ids)}] {rec["date_key"]}  {rec["display"]}')
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(
            {'generated_at': datetime.now(TZ).isoformat(timespec='seconds'),
             'timezone': LOCAL_TZ,
             'posts': posts}, indent=2, ensure_ascii=False))
        time.sleep(args.sleep)

    print(f'\n→ {out_path}')
    print(f'  {len(posts)} post(s) dated, {missing} without a date')


if __name__ == '__main__':
    main()

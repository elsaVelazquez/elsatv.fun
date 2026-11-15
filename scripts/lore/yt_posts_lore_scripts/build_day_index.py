#!/usr/bin/env python3
"""
build_day_index.py — join the archive, the dates and the OCR into one file
keyed by Mountain-time calendar day.

    venv/bin/python scripts/lore/yt_posts_lore_scripts/build_day_index.py

Inputs (each produced by its own script, so you can re-run one alone):

    lore/YTelsaTVposts/index.json   posts, text, image filenames
    lore/YTelsaTVposts/dates.json   absolute date per post  (post_dates.py)
    lore/YTelsaTVposts/ocr.json     text found inside each image (ocr_images.py)
    lore/YTelsaTVposts/ocr_extra.json  second multi-pass reading (ocr_multi.py)
    lore/YTelsaTVposts/llm_text.json   LLM reading of the same image (ocr_llm.py)
    lore/YTelsaTVposts/comments.json  optional; if absent the column is empty

Writes lore/YTelsaTVposts/days.json:

    {
      "generated_at": "…",
      "timezone": "America/Denver",
      "day_count": 94,
      "days": {
        "2026-11-12": {
          "date_key": "2026-11-12",
          "display": "Nov 12, 2026",
          "posts": [
            {
              "post_id": "…",
              "published": "Nov 12, 2026 6:50 PM",
              "text": "the post body as written on YouTube",
              "hashtags": ["#djing"],
              "url": "https://www.youtube.com/post/…",
              "likes": "3",
              "images": [
                {"file": "Ugkx…_1.jpg",
                 "stamped": "datestamped/Ugkx…_1.jpg",
                 "ocr_text": "text visible in the picture",
                 "ocr_extra": "second pass, anything the first missed",
                 "llm_text": "LLM read of the same picture, verbatim"}
              ],
              "comments": []
            }
          ]
        }
      }
    }

Several posts can share one date — that is expected, and the post text is what
distinguishes them (look for "continued").
"""
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path('lore/YTelsaTVposts')
INDEX = ROOT / 'index.json'
DATES = ROOT / 'dates.json'
OCR = ROOT / 'ocr.json'
OCR_EXTRA = ROOT / 'ocr_extra.json'
LLM_TEXT = ROOT / 'llm_text.json'
COMMENTS = ROOT / 'comments.json'
OUT = ROOT / 'days.json'

TZ_NAME = 'America/Denver'


# --------------------------------------------------------------------------- #
def load(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception as e:
        print(f'  ⚠️  {path} unreadable: {e}')
        return default


def post_date(post, dates):
    """The date record for a post, or None if we never resolved one."""
    return dates.get(post.get('post_id')) or None


def image_entries(post, ocr, extra, llm, stamped_dir):
    """One entry per image on the post, in the order YouTube shows them.

    The three text fields are kept apart on purpose: the first tesseract pass,
    the multi-pass second reading, and the LLM's verbatim retype. Nothing is
    merged or shortened — the page prepends them in that order.

    `cdn` is the image's own URL on YouTube's CDN, taken from index.json. The
    two lists are parallel — image_files[n] came from image_urls[n] when
    archive_posts.py downloaded them — so the file index is the join key. It is
    left '' when the lists do not line up, and the page then falls back to the
    local file path instead of showing a wrong picture.
    """
    files = post.get('image_files') or []
    urls = post.get('image_urls') or []
    out = []
    for n, name in enumerate(files):
        out.append({
            'file': name,
            'cdn': urls[n] if n < len(urls) else '',
            'stamped': (f'{stamped_dir.name}/{name}'
                        if (stamped_dir / name).exists() else ''),
            'ocr_text': (ocr.get(name) or {}).get('text', ''),
            'ocr_extra': (extra.get(name) or {}).get('extra_text', ''),
            'llm_text': (llm.get(name) or {}).get('text', ''),
        })
    return out


def day_display(date_key):
    """'2026-11-12' -> 'Nov 12, 2026' for the grid heading."""
    try:
        return datetime.strptime(date_key, '%Y-%m-%d').strftime('%b %-d, %Y')
    except Exception:
        return date_key


# --------------------------------------------------------------------------- #
def main():
    index = load(INDEX, {})
    dates = (load(DATES, {}) or {}).get('posts', {})
    ocr = (load(OCR, {}) or {}).get('images', {})
    extra = (load(OCR_EXTRA, {}) or {}).get('images', {})
    llm = (load(LLM_TEXT, {}) or {}).get('images', {})
    comments = (load(COMMENTS, {}) or {}).get('posts', {})

    posts = index.get('posts', [])
    print(f'→ {len(posts)} posts, {len(dates)} dated, {len(ocr)} images with OCR, '
          f'{len(extra)} with a second pass, {len(llm)} with LLM text')

    stamped_dir = ROOT / 'datestamped'
    days = {}
    undated = []

    for post in posts:
        rec = post_date(post, dates)
        if not rec or not rec.get('date_key'):
            undated.append(post.get('post_id'))
            continue
        key = rec['date_key']
        days.setdefault(key, {
            'date_key': key,
            'display': day_display(key),
            'posts': [],
        })
        days[key]['posts'].append({
            'post_id': post.get('post_id', ''),
            'published': rec.get('display', ''),
            'published_iso': rec.get('published_mst', ''),
            'text': post.get('text', ''),
            'hashtags': post.get('hashtags') or [],
            'url': post.get('url', ''),
            'likes': post.get('like_count', ''),
            'images': image_entries(post, ocr, extra, llm, stamped_dir),
            'comments': comments.get(post.get('post_id'), []),
        })

    # newest day first; within a day, newest post first
    ordered = dict(sorted(days.items(), reverse=True))
    for key in ordered:
        ordered[key]['posts'].sort(key=lambda p: p.get('published_iso', ''),
                                   reverse=True)

    payload = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'timezone': TZ_NAME,
        'day_count': len(ordered),
        'post_count': sum(len(d['posts']) for d in ordered.values()),
        'undated_posts': undated,
        'days': ordered,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False))

    per_day = Counter({k: len(v['posts']) for k, v in ordered.items()})
    multi = {k: n for k, n in per_day.items() if n > 1}

    print(f'\n→ {OUT}')
    print(f'  {payload["day_count"]} day(s), {payload["post_count"]} post(s)')
    print(f'  {len(multi)} day(s) with more than one post')
    if undated:
        print(f'  ⚠️  {len(undated)} post(s) have no date yet — '
              f'run scripts/lore/yt_posts_lore_scripts/post_dates.py')


if __name__ == '__main__':
    main()

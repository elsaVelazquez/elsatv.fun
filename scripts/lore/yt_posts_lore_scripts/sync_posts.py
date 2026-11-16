#!/usr/bin/env python3
"""
sync_posts.py — the one command that catches the archive up with YouTube.

    venv/bin/python scripts/lore/yt_posts_lore_scripts/sync_posts.py
    venv/bin/python scripts/lore/yt_posts_lore_scripts/sync_posts.py --dry-run
    venv/bin/python scripts/lore/yt_posts_lore_scripts/sync_posts.py --max-new 5
    venv/bin/python scripts/lore/yt_posts_lore_scripts/sync_posts.py --max-cost 0.20

Same idea as FINAL_SYNC.py is for the music page: look at what is already on
disk, fetch only what is missing, rebuild only what changed. Nothing in here
re-does work that is already done.

WHAT IT DOES, IN ORDER
----------------------
  1. archive_posts.py     --max-new N     only posts not already in index.json
                                          (known post_ids are skipped, so images
                                          already downloaded are never re-fetched)
  2. post_dates.py        (new posts)     fills dates.json for ids with no date
  3. post_comments.py     (new posts)     fills comments.json for ids with none
  4. stamp_images.py      --only new      stamps datestamped/ copies that are
                                          missing; existing stamps are untouched
  5. web_images.py        --only new      makes web/*.webp copies that are missing
  6. build_day_index.py                   rebuilds days.json from the JSON files
  7. build_posts_html.py                  rebuilds posts.html + its root copy

Steps 4–7 are local, free and idempotent, so they run every time and cost
seconds when there is nothing new. Steps 1–3 touch the network.

If the archive is already current `--dry-run` prints "nothing new" and exits
without writing anything.

OCR is deliberately NOT here. It is the slow, expensive part, so it is an opt-in
step on the images the run reports as new:

    venv/bin/python scripts/lore/yt_posts_lore_scripts/ocr_images.py --limit 20
    venv/bin/python scripts/lore/yt_posts_lore_scripts/ocr_multi.py --limit 6
    venv/bin/python scripts/lore/yt_posts_lore_scripts/ocr_llm_openai.py --max-cost 0.10
    venv/bin/python scripts/lore/yt_posts_lore_scripts/build_posts_html.py

(or just re-run this script afterwards — it rebuilds the page from whatever
OCR files exist, and every OCR script is resumable.)
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT_DIR = Path('lore/YTelsaTVposts')
INDEX = ROOT_DIR / 'index.json'
DATES = ROOT_DIR / 'dates.json'
COMMENTS = ROOT_DIR / 'comments.json'
IMAGES = ROOT_DIR / 'images'
STAMPED = ROOT_DIR / 'datestamped'
WEB = ROOT_DIR / 'web'

# The venv interpreter this repo already uses, unless we are already inside it.
PY = sys.executable


# --------------------------------------------------------------------------- #
def load(path, default=None):
    if not path.exists():
        return default if default is not None else {}
    try:
        return json.loads(path.read_text())
    except Exception as e:
        print(f'  ⚠️  {path} unreadable: {e}')
        return default if default is not None else {}


def known_post_ids():
    return {p.get('post_id') for p in load(INDEX, {}).get('posts', []) if p.get('post_id')}


def known_images():
    return {p for p in os.listdir(IMAGES)} if IMAGES.is_dir() else set()


def missing(need):
    """Names in `need` that have no file in the target folder."""
    have = {p.stem for p in need.iterdir()} if need.is_dir() else set()
    return have


# --------------------------------------------------------------------------- #
def run(script, args, dry=False, label=''):
    """Run one pipeline script from the repo root. Returns True on success."""
    cmd = [PY, str(HERE / script)] + list(args)
    shown = ' '.join(cmd[1:])
    print(f'\n▸ {label or script}')
    print(f'  $ {shown}')
    if dry:
        return True
    t0 = time.time()
    r = subprocess.run(cmd, cwd=Path.cwd())
    took = time.time() - t0
    if r.returncode != 0:
        print(f'  ✗ {script} exited {r.returncode} — stopping here.')
        print('    Nothing is lost: every step writes its own JSON and resumes.')
        return False
    print(f'  ✓ {script} ({took:.1f}s)')
    return True


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(
        description='Append new YouTube community posts and rebuild the page.')
    ap.add_argument('--max-new', type=int, default=0,
                    help='at most N NEW posts this run (0 = everything new)')
    ap.add_argument('--dry-run', action='store_true',
                    help='say what would happen; change nothing')
    ap.add_argument('--no-images', action='store_true',
                    help='metadata only; skip image download and image passes')
    ap.add_argument('--refresh-metadata', action='store_true',
                    help='also re-read like counts / dates / comments on posts '
                         'we already have')
    ap.add_argument('--max-cost', type=float, default=0.0,
                    help='cap in USD passed to ocr_llm_openai.py if it runs '
                         '(0 = do not run OCR at all)')
    ap.add_argument('--ocr', action='store_true',
                    help='run the OCR passes on new images too (slow)')
    args = ap.parse_args()

    if not INDEX.exists() and not args.dry_run:
        print('no index.json yet — the first run is a full archive, which '
              'archive_posts.py handles on its own:')
        print('  venv/bin/python scripts/lore/yt_posts_lore_scripts/archive_posts.py')

    before_ids = known_post_ids()
    before_images = known_images()
    print(f'archive now: {len(before_ids)} posts, {len(before_images)} images')

    # 1 — the only step that decides what is new --------------------------------
    arch = ['--max-new', str(args.max_new)] if args.max_new else []
    if args.no_images:
        arch.append('--no-images')
    if args.refresh_metadata:
        arch.append('--refresh-metadata')
    if not run('archive_posts.py', arch, args.dry_run,
               '1/7 fetch posts not already in index.json'):
        return 1

    if args.dry_run:
        after = load(INDEX, {}).get('post_count')
        print(f'\n(dry run) index.json says {after} posts. '
              'Run without --dry-run to fetch and rebuild.')
        return 0

    index = load(INDEX, {})
    after_ids = known_post_ids()
    new_ids = after_ids - before_ids
    new_images = known_images() - before_images
    print(f'\nnew: {len(new_ids)} post(s), {len(new_images)} image(s)')
    if new_ids:
        for p in index.get('posts', []):
            if p.get('post_id') in new_ids:
                when = p.get('published_abs') or p.get('published_text') or '?'
                print(f'  + {when:<32} {len(p.get("image_files") or []):>2} img  '
                      f'{(p.get("text") or "")[:60]}')

    if not new_ids and not args.refresh_metadata:
        print('\nnothing new — already current. Only the local rebuild will run '
              '(no network, a few seconds).')

    # 2 — metadata for ids that still have no date ------------------------------
    dates = load(DATES, {}).get('posts', {})
    need_dates = [i for i in new_ids if i not in dates]
    if need_dates:
        if not run('post_dates.py', ['--limit', str(len(need_dates))],
                   label=f'2/7 dates for {len(need_dates)} new post(s)'):
            return 1
    else:
        print('\n▸ 2/7 dates — already have a date for every post')

    # 3 — comments for ids that have none ---------------------------------------
    comments = load(COMMENTS, {}).get('posts', {})
    need_comments = [i for i in new_ids if i not in comments]
    if need_comments and not args.no_images:
        if not run('post_comments.py', ['--limit', str(len(need_comments))],
                   label=f'3/7 comments for {len(need_comments)} new post(s)'):
            return 1
    else:
        print('\n▸ 3/7 comments — nothing to fetch')

    # 4–5 — the image copies, only for files that are missing -------------------
    if not args.no_images:
        if not run('stamp_images.py', [], label='4/7 stamp any new image (existing skipped)'):
            return 1
        web_script = HERE / 'web_images.py'
        if web_script.exists():
            if not run('web_images.py', [], label='5/7 web-size copies (existing skipped)'):
                return 1
        else:
            print('\n▸ 5/7 web_images.py not present — skipped')

        # 6 — optional OCR on the new pictures only -----------------------------
        if args.ocr and new_images:
            if not run('ocr_images.py', ['--limit', str(len(new_images))],
                       label=f'6/7 tesseract pass 1 on {len(new_images)} new image(s)'):
                return 1
            if not run('ocr_multi.py', ['--limit', str(len(new_images))],
                       label='6/7 tesseract multi-pass'):
                return 1
            if args.max_cost:
                run('ocr_llm_openai.py',
                    ['--max-images', str(len(new_images)),
                     '--max-cost', f'{args.max_cost:.2f}'],
                    label=f'6/7 vision model, ceiling ${args.max_cost:.2f}')
    else:
        print('\n▸ 4/7–5/7 image passes — skipped (--no-images)')

    # 7 — rebuild everything that is derived ------------------------------------
    if not run('build_day_index.py', [], label='7/7 rebuild days.json'):
        return 1
    if not run('build_posts_html.py', [], label='7/7 rebuild posts.html'):
        return 1

    payload = load(ROOT_DIR / 'days.json', {})
    print(f'\n🎉 done — {payload.get("day_count", 0)} days, '
          f'{payload.get("post_count", 0)} posts, '
          f'{len(list(IMAGES.iterdir())) if IMAGES.is_dir() else 0} images')
    print(f'   {datetime.now():%Y-%m-%d %H:%M:%S}')
    print('\n   If new images came in, their text is not on the page yet. When '
          'you want it:\n'
          '     venv/bin/python scripts/lore/yt_posts_lore_scripts/ocr_multi.py --limit 20\n'
          '     venv/bin/python scripts/lore/yt_posts_lore_scripts/ocr_llm_openai.py --max-cost 0.10\n'
          '     venv/bin/python scripts/lore/yt_posts_lore_scripts/build_posts_html.py')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

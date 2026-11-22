#!/usr/bin/env python3
"""
sync_posts.py — the one command that catches the archive up with YouTube.

    venv/bin/python scripts/lore/yt_posts_lore_scripts/sync_posts.py
    venv/bin/python scripts/lore/yt_posts_lore_scripts/sync_posts.py --dry-run
    venv/bin/python scripts/lore/yt_posts_lore_scripts/sync_posts.py --max-new 5
    venv/bin/python scripts/lore/yt_posts_lore_scripts/sync_posts.py --max-cost 0.20
    venv/bin/python scripts/lore/yt_posts_lore_scripts/sync_posts.py --no-ocr

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
  6. OCR, --only unread                   reads the text inside every image
                                          that has no reading yet — pass 1 and
                                          multi-pass (local tesseract, free),
                                          then the vision model within --max-cost
  7. build_day_index.py                   rebuilds days.json from the JSON files
  8. build_posts_html.py                  rebuilds posts.html + its root copy

Steps 4–8 are local and idempotent, so they run every time and cost seconds when
there is nothing new. Steps 1–3 touch the network. Step 6 costs CPU, plus money
for the capped vision-model part.

If the archive is already current `--dry-run` prints "nothing new" and exits
without writing anything.

OCR — WHY IT IS STEP 6 AND NOT A SEPARATE COMMAND
------------------------------------------------
An image whose text is not read yet is simply an unfinished image, so the sync
finishes it: it hands each OCR script `--only <the unread files>` and nothing
else. Images already read are never sent again, so nothing is re-done or
re-paid. The two tesseract passes are local and free and always run through.
The vision pass stops at `--max-cost` (default $0.50 per run) and saves as it
goes, so a later sync continues from the cap — the archive catches up over a few
runs instead of spending all at once. `--max-cost 0` or `--no-ocr` skips OCR
entirely and still rebuilds the page.

The full picture is printed at the end (and written to ocr_todo.txt with
ready-to-paste commands) in case you ever want to top up by hand:

    venv/bin/python scripts/lore/yt_posts_lore_scripts/ocr_images.py --only a.jpg,b.jpg
    venv/bin/python scripts/lore/yt_posts_lore_scripts/ocr_multi.py --only a.jpg,b.jpg
    venv/bin/python scripts/lore/yt_posts_lore_scripts/ocr_llm_openai.py \
        --only a.jpg,b.jpg --max-cost 0.50

(every OCR script is resumable, so re-running is always safe.)
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


# Which OCR file each reading is stored in, and how to ask that script for one
# specific set of images.
OCR_PASSES = [
    ('ocr.json', 'ocr_images.py', 'pass 1'),
    ('ocr_extra.json', 'ocr_multi.py', 'multi-pass'),
    ('llm_text.json', 'ocr_llm_openai.py', 'vision'),
]


# --------------------------------------------------------------------------- #
def archive_images():
    """Every image that belongs to a post, oldest post first, de-duplicated."""
    out, seen = [], set()
    for post in load(INDEX, {}).get('posts', []):
        for name in post.get('image_files') or []:
            if name not in seen:
                seen.add(name)
                out.append(name)
    return out


def unread_images():
    """{pass label: [image, ...]} — images that pass has no reading for yet."""
    used = archive_images()
    gaps = {}
    for json_name, _script, label in OCR_PASSES:
        have = load(ROOT_DIR / json_name, {}).get('images', {})
        gaps[label] = [n for n in used if n not in have]
    return gaps


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
    ap.add_argument('--max-cost', type=float, default=0.5,
                    help='ceiling in USD for the vision-model OCR pass of this '
                         'run (default 0.50; the next run continues where it '
                         'stopped). 0 = do not run OCR at all')
    ap.add_argument('--ocr', action='store_true',
                    help='(kept for compatibility; OCR now runs by default when '
                         'any image has no text yet)')
    ap.add_argument('--no-ocr', action='store_true',
                    help='skip the OCR pass this time (page still rebuilds)')
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

        # 6 — text inside the images, for every image that has none yet --------
        if args.no_ocr or args.max_cost <= 0:
            print('\n▸ 6/7 image text — skipped '
                  + ('(--no-ocr)' if args.no_ocr else '(--max-cost 0)'))
        else:
            print('\n▸ 6/7 image text for images with no reading yet')
            if not run_ocr_pass(args.dry_run, args.max_cost):
                print('  (OCR did not finish — the page is still rebuilt below; '
                      'run this command again to continue)')
    else:
        print('\n▸ 4/7–6/7 image passes — skipped (--no-images)')

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
    report_ocr_gaps()
    return 0


# --------------------------------------------------------------------------- #
def run_ocr_pass(dry, max_cost):
    """Read the text in every image that is still unread, cheapest pass first.

    Only the unread files are handed to each script (`--only`), so a run never
    re-reads — and never re-pays for — an image it already has. The two
    tesseract passes are local and free, so they always run to completion. The
    vision pass is capped at `max_cost`, and because `llm_text.json` is saved as
    it goes, the next sync picks up exactly where the cap stopped it.

    Returns True if every image was read, False if something is left over.
    """
    gaps = unread_images()
    if not any(gaps.values()):
        print('  every image already has text — nothing to read')
        return True
    for label, missing in gaps.items():
        print(f'    {label:<12} {len(missing):>4} image(s) to read')
    if dry:
        return True

    complete = True
    for json_name, script, label in OCR_PASSES:
        missing = gaps[label]
        if not missing:
            continue
        if script == 'ocr_llm_openai.py':
            if max_cost <= 0:
                complete = False
                continue
            for i in range(0, len(missing), 400):
                if not run(script, ['--only', ','.join(missing[i:i + 400]),
                                    '--max-cost', f'{max_cost:.2f}'],
                           label=f'6/7 {label} on {len(missing[i:i + 400])} image(s), '
                                 f'ceiling ${max_cost:.2f}'):
                    return False
                if unread_images()[label]:
                    print(f'    ceiling ${max_cost:.2f} reached — the rest waits for '
                          'the next sync')
                    complete = False
                    break
        else:
            for i in range(0, len(missing), 400):
                if not run(script, ['--only', ','.join(missing[i:i + 400])],
                           label=f'6/7 {label} on {min(400, len(missing) - i)} '
                                 'image(s)'):
                    return False
    return complete and not any(unread_images().values())


# --------------------------------------------------------------------------- #
def report_ocr_gaps():
    """Say which images still have no text, and the exact command for them.

    Written to be copy-pasted by hand, and saved to ocr_todo.txt, so a manual
    top-up is a paste, not a guess. Every OCR script skips what it already has.
    """
    used = archive_images()
    gaps = unread_images()
    caps = {'pass 1': '', 'multi-pass': '', 'vision': ' --max-cost 0.50'}

    if not any(gaps.values()):
        print(f'\n   Image text: all {len(used)} image(s) read by all three passes.')
        return

    print(f'\n   Image text still missing ({len(used)} images in the archive):')
    for label, missing in gaps.items():
        print(f'     {label:<12} {len(missing):>4} not read yet')

    # Exact commands for exactly the unread files, oldest post first, in
    # batches of 400 so a shell never gets an argument list longer than ARG_MAX.
    lines = []
    for json_name, script, label in OCR_PASSES:
        missing = gaps[label]
        for i in range(0, len(missing), 400):
            chunk = ','.join(missing[i:i + 400])
            lines.append(f'venv/bin/python scripts/lore/yt_posts_lore_scripts/'
                         f'{script} --only {chunk}{caps[label]}')
    lines.append('venv/bin/python scripts/lore/yt_posts_lore_scripts/'
                 'sync_posts.py')  # rebuilds days.json + posts.html
    todo = ROOT_DIR / 'ocr_todo.txt'
    todo.write_text('\n'.join(lines) + '\n')
    print(f'   To top up by hand instead, these are the only commands needed '
          f'({todo}):')
    print(f'     {len(lines)} command(s) — all of them with:  sh {todo}')
    print('     or just run this sync again: the same set, automatically.')


if __name__ == '__main__':
    raise SystemExit(main())

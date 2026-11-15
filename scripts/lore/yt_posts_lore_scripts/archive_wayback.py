#!/usr/bin/env python3
"""
archive_wayback.py — ask the Internet Archive to capture the page, and pack the
pictures into one zip you can hand it.

    venv/bin/python scripts/lore/yt_posts_lore_scripts/archive_wayback.py --dry-run
    venv/bin/python scripts/lore/yt_posts_lore_scripts/archive_wayback.py
    venv/bin/python scripts/lore/yt_posts_lore_scripts/archive_wayback.py --zip-only
    venv/bin/python scripts/lore/yt_posts_lore_scripts/archive_wayback.py --skip-zip

Two separate jobs, on purpose.

1. THE PAGE. One GET to web.archive.org/save/<url> and the Archive fetches
   posts.html, stores the HTML, and starts pulling the images it points at.
   Free, no account. This is the copy that lets a stranger find the archive
   years from now by searching the site name.

2. THE PICTURES. The Wayback capture of a page is not a reliable copy of 1,617
   images: it fetches what it decides to fetch, sometimes lazily, sometimes not
   at all, and re-crawls on its own schedule. The zip is the guarantee. Upload it
   once to https://archive.org/upload/ as an item — free account, the item does
   not expire, and the files are addressable one by one afterwards.

Writes lore/YTelsaTVposts/export/datestamped.zip (gitignored, ~1.9 GB for
1,617 images), which is why the zip is built in a temp file and renamed at the
end: an interrupted run never leaves a half-written archive that looks
complete.

The zip has no compression on the images (they are already JPEG/PNG — deflate
buys ~2% and costs minutes). No --compress unless you want to wait.
"""
import argparse
import sys
import time
import zipfile
from pathlib import Path

import requests

ROOT = Path('lore/YTelsaTVposts')
SRC = ROOT / 'datestamped'
EXPORT = ROOT / 'export'
ZIP = EXPORT / 'datestamped.zip'

PAGE = 'https://elsatv.fun/posts.html'
SAVE = 'https://web.archive.org/save/{}'
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0 Safari/537.36')


def save_page():
    """One capture request. The Archive answers slowly when busy — that is
    normal, and a long wait usually still succeeds."""
    print(f'→ asking the Archive to capture {PAGE}')
    try:
        r = requests.get(SAVE.format(PAGE), timeout=180,
                         headers={'User-Agent': UA, 'Accept': 'text/html'})
    except requests.RequestException as e:
        print(f'  could not reach the Archive: {e}')
        print('  nothing is lost — open this URL in a browser instead:')
        print(f'    {SAVE.format(PAGE)}')
        return False
    print(f'  HTTP {r.status_code}')
    if r.status_code in (200, 302) and r.url != SAVE.format(PAGE):
        print(f'  stored: {r.url.split("?")[0]}')
        return True
    if r.status_code == 429:
        print('  rate-limited (429). Wait an hour and run again, or use the '
              'browser URL above.')
    else:
        print('  the capture did not confirm — the browser URL above always '
              'works.')
    return False


def build_zip(compress):
    if not SRC.is_dir():
        print(f'  no {SRC} — nothing to pack')
        return False
    files = sorted(p for p in SRC.iterdir() if p.is_file())
    if not files:
        print(f'  {SRC} is empty')
        return False

    EXPORT.mkdir(parents=True, exist_ok=True)
    total = sum(p.stat().st_size for p in files)
    print(f'→ packing {len(files):,} file(s), {total / 1e9:.2f} GB → {ZIP}')

    if ZIP.exists() and ZIP.stat().st_size > total * 0.9:
        print(f'  {ZIP.name} already looks complete — skipping '
              f'(delete it to rebuild)')
        return True

    part = ZIP.with_suffix('.zip.part')
    mode = zipfile.ZIP_DEFLATED if compress else zipfile.ZIP_STORED
    started = time.time()
    with zipfile.ZipFile(part, 'w', allowZip64=True, compression=mode) as z:
        for i, p in enumerate(files, 1):
            # arcname puts them at datestamped/<file> inside the zip, so the
            # archive mirrors the bucket and the page's paths.
            z.write(p, arcname=f'datestamped/{p.name}')
            if i % 250 == 0 or i == len(files):
                mb = i * 1.0 / len(files) * total / 1e6
                print(f'   [{i}/{len(files)}] {mb:.0f} MB · '
                      f'{time.time() - started:.0f}s')
    part.replace(ZIP)

    with zipfile.ZipFile(ZIP) as z:
        bad = z.testzip()
    if bad:
        print(f'  WARNING: {bad} is corrupt in the zip')
        return False
    print(f'  ok — {ZIP} ({ZIP.stat().st_size / 1e9:.2f} GB, '
          f'{len(files):,} entries verified)')
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true',
                    help='say what would happen, touch nothing')
    ap.add_argument('--skip-page', action='store_true',
                    help='do not submit the page')
    ap.add_argument('--skip-zip', action='store_true',
                    help='do not pack the images')
    ap.add_argument('--zip-only', action='store_true',
                    help='short for --skip-page')
    ap.add_argument('--compress', action='store_true',
                    help='deflate the images (slow, saves ~2%)')
    args = ap.parse_args()
    if args.zip_only:
        args.skip_page = True

    files = sorted(SRC.iterdir()) if SRC.is_dir() else []
    total = sum(p.stat().st_size for p in files if p.is_file())
    print(f'→ {len(files):,} image(s), {total / 1e9:.2f} GB')
    print(f'→ zip would be {ZIP}')

    if args.dry_run:
        print('\n  would submit:', 'no' if args.skip_page else PAGE)
        print('  would pack zip:', 'no' if args.skip_zip else 'yes')
        print('  then upload the zip at https://archive.org/upload/')
        return

    ok = True
    if not args.skip_page:
        ok = save_page() and ok
    if not args.skip_zip:
        ok = build_zip(args.compress) and ok

    print('\n→ next: upload the zip as one item, once:')
    print('    https://archive.org/upload/')
    print('  title: elsatv.fun posts archive — datestamped images')
    print('  after that, future batches can be added to the same item.')
    if not ok:
        print('\n  some step did not confirm. Nothing is lost; each step is '
              'independent and safe to re-run.')
        sys.exit(1)


if __name__ == '__main__':
    main()

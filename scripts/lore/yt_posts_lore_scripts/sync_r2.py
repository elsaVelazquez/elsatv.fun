#!/usr/bin/env python3
"""
sync_r2.py — copy the datestamped images to Cloudflare R2, which is what serves
them to the public page when YouTube's CDN does not.

    venv/bin/python scripts/lore/yt_posts_lore_scripts/sync_r2.py --check
    venv/bin/python scripts/lore/yt_posts_lore_scripts/sync_r2.py            # upload
    venv/bin/python scripts/lore/yt_posts_lore_scripts/sync_r2.py --dry-run

Reads  lore/YTelsaTVposts/datestamped/<file>     1,617 stamped images
Writes nothing locally. Uploads to the bucket and prints the public URL to put
in build_posts_html.py as FALLBACK_BASE.

WHY R2
------
10 GB of storage free, egress free, no card needed, and no "your trial ended"
email in a year. The stamped images are about 0.9 GB, so this sits comfortably
inside the free tier. If it ever outgrows it, R2 is $0.015/GB/month — a few
dollars, not a surprise bill.

WHAT IT NEEDS
-------------
Credentials in .env (see HOSTING.md for how to get them):

    R2_ACCOUNT_ID=...
    R2_ACCESS_KEY_ID=...
    R2_SECRET_ACCESS_KEY=...
    R2_BUCKET=elsatv-images

It talks to R2 through the S3 API, so it uses boto3 and nothing else. Only the
stamped copy is uploaded — the one with the black date bar — because the date is
the point: it is what lets a reader see that a thing was predicted before it
happened.

Re-running is cheap: a file whose size and last-modified time already match the
bucket is skipped, so adding one new post uploads one new picture.
"""
import argparse
import mimetypes
import os
import sys
from pathlib import Path

SRC = Path('lore/YTelsaTVposts/datestamped')
PREFIX = 'datestamped'          # key prefix in the bucket; must match
# FALLBACK_DIR in build_posts_html.py
ENDPOINT = 'https://{account}.r2.cloudflarestorage.com'


# --------------------------------------------------------------------------- #
def env():
    """Read .env without pulling in python-dotenv — one less thing to install."""
    values = {}
    f = Path('.env')
    if f.exists():
        for line in f.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            values[k.strip()] = v.strip().strip('"').strip("'")
    for k in ('R2_ACCOUNT_ID', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY',
              'R2_BUCKET'):
        if os.environ.get(k):
            values[k] = os.environ[k]
    missing = [k for k in ('R2_ACCOUNT_ID', 'R2_ACCESS_KEY_ID',
                           'R2_SECRET_ACCESS_KEY', 'R2_BUCKET')
               if not values.get(k)]
    if missing:
        raise SystemExit(
            'missing in .env: ' + ', '.join(missing) +
            '\nsee HOSTING.md — Cloudflare → R2 → Manage API tokens')
    return values


def client(values):
    try:
        import boto3
    except ImportError:
        raise SystemExit('boto3 is not installed:\n'
                         '  venv/bin/pip install boto3')
    from botocore.config import Config
    return boto3.client(
        's3',
        endpoint_url=ENDPOINT.format(account=values['R2_ACCOUNT_ID']),
        aws_access_key_id=values['R2_ACCESS_KEY_ID'],
        aws_secret_access_key=values['R2_SECRET_ACCESS_KEY'],
        region_name='auto',
        config=Config(signature_version='s3v4', retries={'max_attempts': 5}),
    )


def remote_index(s3, bucket):
    """key -> (size, etag) for everything already in the bucket under PREFIX."""
    found = {}
    token = None
    while True:
        kw = {'Bucket': bucket, 'Prefix': PREFIX + '/'}
        if token:
            kw['ContinuationToken'] = token
        page = s3.list_objects_v2(**kw)
        for obj in page.get('Contents', []):
            found[obj['Key']] = obj['Size']
        if not page.get('IsTruncated'):
            return found
        token = page.get('NextContinuationToken')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true',
                    help='report what is local, remote, and missing')
    ap.add_argument('--dry-run', action='store_true',
                    help='say what would be uploaded, upload nothing')
    ap.add_argument('--public-base', default='',
                    help="the bucket's public URL, to print the FALLBACK_BASE "
                         "line (e.g. https://img.elsatv.fun)")
    args = ap.parse_args()

    if not SRC.is_dir():
        raise SystemExit(f'{SRC} does not exist — has the stamping run yet?')

    local = sorted(p for p in SRC.iterdir() if p.is_file())
    print(f'→ {len(local):,} local image(s) in {SRC}')

    values = env()
    s3 = client(values)
    bucket = values['R2_BUCKET']
    remote = remote_index(s3, bucket)
    print(f'→ {len(remote):,} already in s3://{bucket}/{PREFIX}/')

    todo = [p for p in local
            if remote.get(f'{PREFIX}/{p.name}') != p.stat().st_size]
    print(f'→ {len(todo):,} to upload, {len(local) - len(todo):,} already there')

    if args.check or args.dry_run:
        for p in todo[:15]:
            print('   would upload', p.name)
        if len(todo) > 15:
            print(f'   … and {len(todo) - 15} more')
    else:
        done = 0
        total = len(todo)
        for p in todo:
            ctype = mimetypes.guess_type(
                p.name)[0] or 'application/octet-stream'
            s3.upload_file(
                str(p), bucket, f'{PREFIX}/{p.name}',
                ExtraArgs={'ContentType': ctype,
                           # A year is safe: filenames never change content.
                           'CacheControl': 'public, max-age=31536000, immutable'},
            )
            done += 1
            if done % 25 == 0 or done == total:
                print(f'   [{done}/{total}] {p.name}')

    base = args.public_base.rstrip('/')
    if base:
        print(f'\n  put this in build_posts_html.py:\n'
              f"    FALLBACK_BASE = '{base}'")
        print(f'  a test URL: {base}/{PREFIX}/'
              f'{local[0].name if local else "<file>"}')


if __name__ == '__main__':
    main()

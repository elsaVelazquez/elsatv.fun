#!/usr/bin/env python3
"""
sync_r2.py — copy the datestamped images to Cloudflare R2, which is what serves
them to the public page when YouTube's CDN does not.

    venv/bin/python scripts/lore/yt_posts_lore_scripts/sync_r2.py --check
    venv/bin/python scripts/lore/yt_posts_lore_scripts/sync_r2.py            # upload
    venv/bin/python scripts/lore/yt_posts_lore_scripts/sync_r2.py --dry-run

Reads  lore/YTelsaTVposts/web/<file>.webp        1,617 display images (~199 MB)
Writes nothing locally. Uploads to the bucket and prints the public URL to put
in build_posts_html.py as FALLBACK_BASE.

WHY web/ AND NOT datestamped/
-----------------------------
Both folders show the same picture with the black date bar. `datestamped/` is
the master (1.8 GB) and stays on the external drive; `web/` is the same thing
re-encoded for a screen by web_images.py (1600 px on the long edge, ~8x
smaller). Uploading the masters would use a fifth of R2's free 10 GB for
nothing a browser can use.

WHY R2
------
10 GB of storage free, egress free, no card needed, and no "your trial ended"
email in a year. The web set is about 199 MB, so this sits comfortably inside
the free tier (2% of it). If it ever outgrows it, R2 is $0.015/GB/month — a few
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

SRC = Path('lore/YTelsaTVposts/web')
SUFFIX = '.webp'
PREFIX = 'web'                  # key prefix in the bucket; must match
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


KEYS = ('R2_ACCOUNT_ID', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY',
        'R2_BUCKET')


def explain(err, values):
    """R2 answers with an AWS-style error code. Translate it to the fix."""
    text = str(err)
    code = getattr(err, 'response', {}).get('Error', {}).get('Code', '')
    account = values.get('R2_ACCOUNT_ID', '')
    bucket = values.get('R2_BUCKET', '')
    unreachable = ('endpoint' in text.lower()
                   or 'EndpointConnectionError' in type(err).__name__
                   or 'Name or service not known' in text
                   or 'ssl' in text.lower())
    if unreachable:
        return (f'cannot reach R2 for account {account!r}.\n'
                '  The account ID is the 32-character string in the dashboard\n'
                '  URL: dash.cloudflare.com/<ACCOUNT_ID>/r2 . Fix R2_ACCOUNT_ID\n'
                '  in .env and run again.')
    if code in ('InvalidAccessKeyId', 'SignatureDoesNotMatch',
                'InvalidToken', 'AccessDenied'):
        return (f'R2 rejected the credentials ({code}).\n'
                '  Your token does not match this account or bucket. Either:\n'
                '   * re-copy the Access Key ID and Secret from\n'
                '     R2 → Manage R2 API Tokens, or\n'
                '   * give the token permission on this bucket.\n'
                '  Then: sync_r2.py --set-keys <ACCOUNT_ID> <KEY_ID> <SECRET>')
    if code == 'NoSuchBucket':
        return (f'there is no bucket named {bucket!r} in this account.\n'
                '  Create it first: Cloudflare → R2 → Create bucket, name it\n'
                f'  exactly {bucket} , location Automatic. Then run again.')
    return f'R2 error: {code or text}'


def set_keys(pairs, bucket):
    """Write the R2_* lines into .env, replacing any that are already there.

    Editing .env by hand is where this normally goes wrong: a trailing space or
    a stray quote after the secret makes R2 answer SignatureDoesNotMatch and
    nothing says why. This strips the values, keeps .env's other lines exactly
    as they are, and never prints a secret back.
    """
    values = dict(zip(KEYS[:3], pairs))
    values['R2_BUCKET'] = bucket or 'elsatv-images'
    for k, v in values.items():
        v = (v or '').strip().strip('"').strip("'")
        if not v:
            raise SystemExit(f'{k} is empty — nothing written')
        if any(c.isspace() for c in v):
            raise SystemExit(f'{k} contains a space — re-copy it; '
                             'secrets have no spaces')
        values[k] = v

    header = '# Cloudflare R2 — image delivery for posts.html (sync_r2.py)'
    f = Path('.env')
    keep = []
    dropped = 0
    if f.exists():
        for line in f.read_text().splitlines():
            name = line.split('=', 1)[0].strip()
            if '=' in line and name in values:
                dropped += 1
                continue
            if line.strip() == header:   # ours from an earlier run
                continue
            keep.append(line)
    while keep and not keep[-1].strip():
        keep.pop()
    if keep and not any(l.lstrip().startswith('#') for l in keep[-2:]):
        keep.append('')
    keep.append(header)
    keep += [f'{k}={values[k]}' for k in KEYS]
    f.write_text('\n'.join(keep) + '\n')

    print(f'→ wrote {len(KEYS)} R2 key(s) to {f.resolve()}')
    if dropped:
        print(f'  replaced {dropped} old R2_ line(s)')
    for k in KEYS:
        v = values[k]
        shown = v if k == 'R2_BUCKET' else f'{v[:4]}…{v[-4:]} ({len(v)} chars)'
        print(f'  {k} = {shown}')
    print('\n  next:  venv/bin/python scripts/lore/yt_posts_lore_scripts/'
          'sync_r2.py --check')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--set-keys', nargs=3, metavar=('ACCOUNT_ID', 'KEY_ID',
                                                   'SECRET'),
                    help='write the R2 credentials from the Cloudflare screen '
                         'into .env, then exit. Paste them in quotes.')
    ap.add_argument('--set-bucket', default='',
                    help='bucket name for --set-keys (default elsatv-images)')
    ap.add_argument('--check', action='store_true',
                    help='report what is local, remote, and missing')
    ap.add_argument('--dry-run', action='store_true',
                    help='say what would be uploaded, upload nothing')
    ap.add_argument('--public-base', default='',
                    help="the bucket's public URL, to print the FALLBACK_BASE "
                         "line (e.g. https://img.elsatv.fun)")
    args = ap.parse_args()

    if args.set_keys:
        set_keys(args.set_keys, args.set_bucket)
        return

    if not SRC.is_dir():
        raise SystemExit(f'{SRC} does not exist — run web_images.py first')

    local = sorted(p for p in SRC.iterdir()
                   if p.is_file() and p.suffix.lower() == SUFFIX)
    if not local:
        raise SystemExit(f'no {SUFFIX} files in {SRC} — run web_images.py')
    print(f'→ {len(local):,} local image(s) in {SRC}')

    values = env()
    s3 = client(values)
    bucket = values['R2_BUCKET']
    try:
        remote = remote_index(s3, bucket)
    except Exception as e:
        raise SystemExit(explain(e, values))
    print(f'→ {len(remote):,} already in s3://{bucket}/{PREFIX}/')

    todo = [p for p in local
            if remote.get(f'{PREFIX}/{p.name}') != p.stat().st_size]
    print(f'→ {len(todo):,} to upload, {len(local) - len(todo):,} already there')

    if not todo:
        print('  the bucket already matches — nothing to do')

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
            try:
                s3.upload_file(
                    str(p), bucket, f'{PREFIX}/{p.name}',
                    ExtraArgs={'ContentType': ctype,
                               # A year is safe: filenames never change content.
                               'CacheControl': 'public, max-age=31536000, immutable'},
                )
            except Exception as e:
                raise SystemExit(explain(e, values))
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

#!/usr/bin/env python3
"""
distribute_stores.py — add MISSING stores to already-submitted ONCE releases.

Uses POST /v1/releases/{id}/distribute ("Deliver an already-submitted release to
additional stores"), which queues delivery to extra stores without re-uploading
assets.

This script is deliberately conservative. It only ever ADDS stores a release
does not already have, and it never touches the stores listed in EXCLUDED_STORES
below.

Why the exclusions exist
------------------------
Spotify and SoundCloud currently reject this account with:

    Multiple artists (DJ Elsa, Elsa Velazquez) share the same Spotify profile Id
    27NhC9Ct23OhR441IZH6KY. Each artist must have a unique profile Id.

    Multiple artists (DJ Elsa, Elsa Velazquez) share the same Soundcloud profile
    Id 3913582. Each artist must have a unique profile Id.

That is an ONCE-side artist-identity problem, already reported and queued for
their fix. Re-requesting those stores before it lands would push the same
invalid payload back at their validator and risk muddying the ticket, so the
script skips them unconditionally. Drop them from EXCLUDED_STORES once ONCE
confirms the fix.

Usage
-----
    ./venv/bin/python scripts/lore/music_lore_scripts/distribute_stores.py            # plan only
    ./venv/bin/python scripts/lore/music_lore_scripts/distribute_stores.py --apply
    ./venv/bin/python scripts/lore/music_lore_scripts/distribute_stores.py --apply \
        --release e54062fc-5595-43bd-96db-e23c34f2bd02
    ./venv/bin/python scripts/lore/music_lore_scripts/distribute_stores.py \
        --add "Boomplay,Flo"          # replace the default target set

Run from the repo root: .env and every relative path below assume it.
"""

import argparse
import os
import sys
import time

import requests

BASE = 'https://once.app/v1'

# Never requested, whatever the plan says. See module docstring.
EXCLUDED_STORES = {
    'Spotify',     # shared profile id 27NhC9Ct23OhR441IZH6KY — ONCE ticket open
    'SoundCloud',  # shared profile id 3913582 — ONCE ticket open
}

# Stores we do want everywhere, by name. Everything in ONCE's catalog that is
# enabled by default and not excluded is fine; these are just the ones worth
# naming so the intent is explicit if the catalog changes.
DEFAULT_TARGETS = [
    'Apple Music', 'YouTube Music', 'TikTok', 'Amazon', 'Tidal', 'Nuuday',
    'Pandora', 'KKBOX', 'iMusica', 'iHeartRadio', 'Anghami', 'Jiosaavn', 'AWA',
    'Tencent', 'NetEase', 'Facebook Audio Library', 'Mixcloud', 'Boomplay',
    'Snap', 'Peloton', 'Audiomack', 'JOOX', 'Flo',
]


def load_env():
    if os.path.exists('.env'):
        with open('.env') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key, value)


def headers():
    pat = os.getenv('ONCE_PAT')
    if not pat:
        raise SystemExit('ONCE_PAT not found in .env')
    return {'Authorization': f'Bearer {pat}', 'Content-Type': 'application/json'}


def get(url, h, retries=4):
    """GET with 429/5xx backoff, mirroring FINAL_SYNC.py's ONCE handling."""
    for attempt in range(retries):
        r = requests.get(url, headers=h, timeout=60)
        if r.status_code == 429:
            wait = 15 * (attempt + 1)
            print(f"  ⏳ ONCE rate limit, waiting {wait}s...", flush=True)
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r.json()
    raise SystemExit(f'ONCE kept rate-limiting: {url}')


def fetch_stores(h):
    return {s['name']: s for s in get(f'{BASE}/distribution-stores', h)['stores']}


def fetch_releases(h):
    releases, offset = [], 0
    while True:
        page = get(f'{BASE}/releases?limit=100&offset={offset}', h).get('releases', [])
        if not page:
            return releases
        releases.extend(page)
        if len(page) < 100:
            return releases
        offset += 100


def store_names(release_id, h):
    """Names of the stores a release already targets."""
    data = get(f'{BASE}/releases/{release_id}/status', h)
    return {s.get('storeName') for s in data.get('storeStatuses', []) if s.get('storeName')}


def plan(h, releases, catalog, targets):
    """Return [(release, [missing store names])] for every release with a gap."""
    rows = []
    for r in releases:
        have = store_names(r['id'], h)
        missing = [n for n in targets if n not in have and n not in EXCLUDED_STORES]
        if missing:
            rows.append((r, missing, sorted(EXCLUDED_STORES - have)))
    return rows


def main():
    ap = argparse.ArgumentParser(
        description='Add missing stores to already-submitted ONCE releases.')
    ap.add_argument('--apply', action='store_true',
                    help='actually call /distribute (default: plan only)')
    ap.add_argument('--release', action='append', default=None,
                    help='limit to this release id (repeatable)')
    ap.add_argument('--add', default=None,
                    help='comma-separated store names to target instead of the default set')
    ap.add_argument('--include-partner', action='store_true',
                    help='also target partnerOnly stores such as YouTube Content ID')
    ap.add_argument('--limit', type=int, default=0,
                    help='stop after N releases (0 = all)')
    args = ap.parse_args()

    load_env()
    h = headers()

    catalog = fetch_stores(h)
    if args.add:
        targets = [n.strip() for n in args.add.split(',') if n.strip()]
    else:
        targets = list(DEFAULT_TARGETS)
        if args.include_partner:
            targets += [s['name'] for s in catalog.values() if s.get('partnerOnly')]

    unknown = [n for n in targets if n not in catalog]
    if unknown:
        raise SystemExit(f'Not in ONCE store catalog: {unknown}')

    releases = fetch_releases(h)
    if args.release:
        wanted = set(args.release)
        releases = [r for r in releases if r['id'] in wanted]
        if not releases:
            raise SystemExit('No release matched --release id(s)')

    print(f'{len(releases)} release(s), {len(targets)} target store(s)')
    print(f'skipping (ONCE ticket open): {", ".join(sorted(EXCLUDED_STORES))}\n')

    rows = plan(h, releases, catalog, targets)
    if args.limit:
        rows = rows[:args.limit]

    if not rows:
        print('Nothing to add — every release already has every target store.')
        return 0

    total = 0
    for r, missing, skipped in rows:
        label = (f'{r["title"]} [{r.get("status")}] {r["id"]}')
        print(f'{label}\n  + {", ".join(missing)}')
        if skipped:
            print(f'  · excluded, still absent: {", ".join(skipped)}')
        total += len(missing)

        if not args.apply:
            continue

        body = {'store_ids': [catalog[n]['storeId'] for n in missing]}
        resp = requests.post(f'{BASE}/releases/{r["id"]}/distribute',
                             headers=h, json=body, timeout=60)
        if resp.status_code == 409:
            print('  ⚠️  409 — not submitted/distributed yet, skipped')
            continue
        if resp.status_code == 403:
            print(f'  ⚠️  403 — {resp.text[:200]}')
            continue
        if not resp.ok:
            print(f'  ⚠️  {resp.status_code} — {resp.text[:300]}')
            continue

        data = resp.json() if resp.content else {}
        queued = data.get('queuedStoreIds') or data.get('storeIds') or []
        skipped_dsp = data.get('skippedStoreIds') or []
        print(f'  ✅ queued {len(queued) or len(body["store_ids"])}')
        if skipped_dsp:
            print(f'  · ONCE skipped: {skipped_dsp}')
        time.sleep(1)

    if args.apply:
        print(f'\nDone. Requested {total} store addition(s) across {len(rows)} release(s).')
    else:
        print(f'\nPlan only: {total} store addition(s) across {len(rows)} release(s).')
        print('Re-run with --apply to send them.')
    return 0


if __name__ == '__main__':
    sys.exit(main())

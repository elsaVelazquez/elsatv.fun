#!/usr/bin/env python3
"""
album_status.py — read-only status report straight from ONCE.

    venv/bin/python scripts/lore/music_lore_scripts/album_status.py
    venv/bin/python scripts/lore/music_lore_scripts/album_status.py "Real Dream Is Real"
    venv/bin/python scripts/lore/music_lore_scripts/album_status.py --limit 5
    venv/bin/python scripts/lore/music_lore_scripts/album_status.py "dream"   # any title containing "dream"
    venv/bin/python scripts/lore/music_lore_scripts/album_status.py --save /tmp/report.txt        # also write the .txt
    venv/bin/python scripts/lore/music_lore_scripts/album_status.py --save --md /tmp/report.md    # write a .md too

WHAT IT IS FOR
--------------
You need to tell ONCE which platforms a release is still NOT live on. The music
page pipeline (sync_music.py) only cares about YouTube links, so none of its
output has this. This script asks ONCE directly and prints a plain-text report
you can copy and paste:

    album name, UPC, release date, and the album-level ISRC (when every track
    shares one ISRC — see below), plus every platform NOT live yet, then the
    tracklist with each song's own ISRC and that song's missing platforms.

WHAT "LIVE" MEANS HERE
----------------------
A platform is live when ONCE's store record carries a working link
(`urlInStore`) or a go-live timestamp (`dateLive`). Anything else — "In
inspection", "Delivered to DSP", "Upload failed", "Pending" — is NOT live yet
and is listed. That distinction matters: "Delivered to DSP" means the file was
handed over, not that the store has published it.

ISRC AND UPC
------------
ONCE keeps the UPC on the release and one ISRC per track. There is no separate
album-level ISRC — a release only has one when every track shares it. When they
differ the report says so and the album line is left blank, so nothing is
invented. The per-track ISRCs are always listed.

This script only reads. It makes no changes, writes no cache, and does not
touch git.
"""
import argparse
import json
import os
import re
import sys
import textwrap
import time
import unicodedata
from pathlib import Path

import requests

API = 'https://once.app/v1'
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0 Safari/537.36')

# Timeout per request, and how many times to retry a failure. ONCE does
# occasionally take longer than a minute to answer a detail request.
TIMEOUT = 90
RETRIES = 4


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def load_env(path='.env'):
    """Read .env into os.environ. Existing values win."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def norm(s):
    """Same comparison as the other music scripts: case/punctuation ignored."""
    s = unicodedata.normalize('NFKC', s or '').lower()
    s = re.sub(r'[\u200b-\u200f\ufeff]', '', s)
    return re.sub(r'[^0-9a-z]+', '', s)


def session(pat):
    s = requests.Session()
    s.headers.update({'Authorization': f'Bearer {pat}',
                      'Content-Type': 'application/json',
                      'User-Agent': UA})
    return s


def get(sess, url, params=None, what='request'):
    """GET with retries and a clear error instead of a traceback."""
    last = None
    for attempt in range(RETRIES):
        try:
            r = sess.get(url, params=params, timeout=TIMEOUT)
            if r.status_code == 429:
                wait = 15 * (attempt + 1)
                print(f'  … rate limited, waiting {wait}s', file=sys.stderr)
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()
        except Exception as e:                       # noqa: BLE001
            last = e
            if attempt < RETRIES - 1:
                time.sleep(5 * (attempt + 1))
    raise SystemExit(f'ONCE {what} failed after {RETRIES} tries: {last}\n'
                     f'  {url}\n'
                     '  Check the network and that ONCE_PAT in .env is valid.')


def get_releases(sess):
    """Every release on the account, newest first."""
    out, offset = [], 0
    while True:
        data = get(sess, f'{API}/releases',
                   {'limit': 100, 'offset': offset}, 'release list')
        out.extend(data.get('releases') or [])
        nxt = data.get('nextOffset')
        if nxt is None or nxt == offset:
            return out
        offset = nxt


def get_release(sess, release_id):
    """{'release': {...}, 'tracks': [...]} for one release."""
    return get(sess, f'{API}/releases/{release_id}', None, 'release detail')


def duration(seconds):
    if not seconds:
        return ''
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        return str(seconds)
    return f'{seconds // 60}:{seconds % 60:02d}'


# --------------------------------------------------------------------------- #
# store status
# --------------------------------------------------------------------------- #
def store_state(store):
    """(live?, label) for one store record.

    Live means the store answered with a link or a go-live timestamp. The
    numeric status is deliberately not trusted on its own: "Delivered to DSP"
    (50) arrives without either, and the release is not on the store yet.
    """
    text = (store.get('statusText') or '').strip()
    url = (store.get('urlInStore') or '').strip()
    live_at = (store.get('dateLive') or '').strip()
    if store.get('isError'):
        return False, short_label(text or 'Error')
    if url or live_at:
        return True, short_label(text or 'Live')
    return False, short_label(text or f"Status {store.get('status')}")


# ONCE's own wording, shortened. The wording is kept, because it is the whole
# point: "Delivered to DSP" means handed over, not published.
SHORT = {
    'delivered to dsp': 'Delivered to DSP, not published yet',
    'in inspection': 'In inspection at the store',
    'upload failed': 'Upload failed',
    'pending': 'Pending',
    'on store': 'On store',
    'confirmed live': 'Confirmed live',
}


def short_label(text):
    key = (text or '').strip().lower()
    return SHORT.get(key, text)


def split_stores(stores):
    """Return (live, missing) lists of (name, label, url) tuples."""
    live, missing = [], []
    for st in stores or []:
        name = (st.get('storeName') or '').strip(
        ) or f"Store {st.get('storeId')}"
        is_live, label = store_state(st)
        row = (name, label, (st.get('urlInStore') or '').strip())
        (live if is_live else missing).append(row)
    live.sort(key=lambda r: r[0].lower())
    missing.sort(key=lambda r: r[0].lower())
    return live, missing


def dedupe_missing(rows):
    """Collapse a name that appears more than once (e.g. two YouTube entries
    with the same statusText) into one line, keeping distinct statuses apart."""
    seen, out = set(), []
    for name, label, _ in rows:
        key = (name.lower(), label.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append((name, label))
    return out


# --------------------------------------------------------------------------- #
# report
# --------------------------------------------------------------------------- #
def album_isrc(tracks):
    """The shared ISRC, or '' when the tracks differ.

    Returns (isrc, note). ONCE has no album-level ISRC field, so this is only
    reported when it is genuinely one value for the whole release.
    """
    found = [((t.get('isrc') or '').strip(), (t.get('title') or '').strip())
             for t in tracks]
    found = [(isrc, title) for isrc, title in found if isrc]
    distinct = sorted({isrc for isrc, _ in found})
    if not found:
        return '', 'no ISRC on any track yet'
    if len(found) < len(tracks):
        return '', f'only {len(found)} of {len(tracks)} track(s) have an ISRC'
    if len(distinct) == 1:
        return distinct[0], ''
    return '', (f'the {len(distinct)} tracks have different ISRCs, so there is '
                'no single album ISRC (per song below)')


def release_date(detail, summary):
    """The scheduled date, falling back the same way FINAL_SYNC does."""
    for key in ('release_date', 'original_release_date'):
        value = detail.get(key)
        if value:
            return str(value)[:10]
    for key in ('first_distributed_at', 'created_at'):
        value = summary.get(key) or detail.get(key)
        if value:
            return str(value)[:10]
    return 'unknown'


def header_line(release):
    return (f"{release.get('title') or 'Untitled'}  ·  {release.get('status') or '?'}")


def wrap_names(names, indent=6, bullet='•', width=78):
    """One wrapped, bulleted line of platform names."""
    sep = ' ' if len(names) < 2 else ', '
    body = f'{bullet} ' + sep.join(names)
    lead = ' ' * indent
    wrapped = textwrap.wrap(body, width=width - indent,
                            initial_indent=lead, subsequent_indent=lead + '  ')
    return '\n'.join(wrapped) if wrapped else lead + body


def build_report(release, tracks, width=78, markdown=False):
    """The copy-paste text for one album, as a list of lines.

    markdown=True renders the same content as Markdown instead of plain text
    (bold album name, '- ' bullets), for pasting into a message or ticket.
    """
    bullet = '- ' if markdown else '  • '
    L = []
    bar = '=' * width
    title = release.get('title') or 'Untitled'
    if markdown:
        L.extend([f'## {title}', ''])
    else:
        L.extend([bar, f'ALBUM: {title}', bar])

    config = release.get('configuration') or ''
    type_line = ' · '.join(x for x in [
        release.get('primary_artist_name') or '',
        release.get('genre') or '',
        config,
    ] if x)
    if type_line:
        L.append(type_line)

    L.append(f'Release date : {release_date(release, release)}')
    L.append(f'UPC          : {release.get("upc") or "(none on ONCE yet)"}')

    isrc, note = album_isrc(tracks)
    if isrc:
        L.append(f'Album ISRC   : {isrc}')
    else:
        L.append(f'Album ISRC   : (single value not available — {note})')

    L.append(f'ONCE status  : {release.get("status") or "?"}'
             f'  ·  distribution: {release.get("revelator_status") or "?"}')

    stores = release.get('revelator_store_statuses') or []
    live, missing = split_stores(stores)

    L.append('')
    if not stores:
        L.append('NOT LIVE ON (store status has not come back from ONCE yet):')
        L.append('  everyone — ONCE has no store status for this release.')
    elif not missing:
        L.append('NOT LIVE ON: nothing — every platform reports live. ✅')
    else:
        L.append(f'NOT LIVE ON ({len(missing)} of {len(stores)} platforms):')
        rows = dedupe_missing(missing)
        # Group by reason, worst first, so a long list is readable and ONCE
        # can see at a glance which platforms need action vs which are just
        # still being processed.
        order = ['upload failed', 'error', 'pending', 'in inspection',
                 'delivered', 'other']
        groups = {}
        for name, label in rows:
            low = label.lower()
            key = next((k for k in order[:-1] if k in low), 'other')
            groups.setdefault(key, []).append((name, label))
        for key in order:
            if key not in groups:
                continue
            names = [n for n, _ in groups[key]]
            label = groups[key][0][1]
            L.append(f'  [{label}]  ({len(names)})')
            L.append(wrap_names(names, indent=4, bullet=bullet.strip()))

    if live:
        L.append('')
        L.append(f'LIVE ON ({len(live)}): ' + ', '.join(n for n, _, _ in live))

    L.append('')
    if markdown:
        L.append(f'### Songs ({len(tracks)})')
        L.append('')
    else:
        rule = '-' * width
        L.extend([rule, f'SONGS ({len(tracks)})', rule])

    if not tracks:
        L.append('  (ONCE returned no tracklist for this release)')

    for i, t in enumerate(tracks, 1):
        num = t.get('track_number') or i
        song = (t.get('title') or '').strip() or '(untitled)'
        dur = duration(t.get('duration'))
        isrc_t = (t.get('isrc') or '').strip()
        bits = [f'{num:>2}. {song}']
        if dur:
            bits.append(f'    {dur}')
        L.append(''.join(bits))
        line = (f'    `ISRC: {isrc_t or "(none on ONCE yet)"}`'
                if markdown else f'    ISRC: {isrc_t or "(none on ONCE yet)"}')
        # Song-level store status, when ONCE has it. Most accounts only carry
        # album-level status, so this is a bonus, not a promise.
        t_stores = t.get('revelator_store_statuses') or t.get('store_statuses')
        if t_stores:
            _, t_missing = split_stores(t_stores)
            if t_missing:
                line += ('    not live: '
                         + ', '.join(n for n, _ in dedupe_missing(t_missing)))
        L.append(line)

    L.append('')
    L.append('Source: ONCE API, read-only. "Not live" = the store has no link and '
             'no go-live timestamp.')
    L.append('')
    return L


# --------------------------------------------------------------------------- #
# selection
# --------------------------------------------------------------------------- #
def match_releases(releases, query):
    """Exact title first, then normalised equality, then substring."""
    q = (query or '').strip()
    if not q:
        return list(releases)

    exact = [r for r in releases if (r.get('title') or '') == q]
    if exact:
        return exact

    nq = norm(q)
    n_match = [r for r in releases if norm(r.get('title')) == nq]
    if n_match:
        return n_match

    part = [r for r in releases if nq and nq in norm(r.get('title'))]
    if part:
        return part

    return []


def show_candidates(releases):
    """When nothing matched, show what the titles actually look like."""
    print('No release matched. Releases on ONCE (newest first):\n')
    for r in releases:
        print(f"  {r.get('status', '?'):>16}  {r.get('title')}")
    print('\nPass part of a title, e.g.:\n'
          '  venv/bin/python scripts/lore/music_lore_scripts/album_status.py "dream"')


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(
        description='Read-only ONCE report: album, ISRC, songs, platforms '
                    'each release is not live on yet.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    ap.add_argument('title', nargs='*',
                    help='part of an album title (omit for every release)')
    ap.add_argument('--limit', type=int, default=0, metavar='N',
                    help='report only the N newest matching releases')
    ap.add_argument('--save', nargs='?', const='', metavar='PATH',
                    help='also write the report to a .txt file '
                         '(default: album_status_report.txt)')
    ap.add_argument('--md', nargs='?', const='', metavar='PATH',
                    help='also write a markdown copy (use with --save)')
    args = ap.parse_args()

    load_env()
    pat = os.getenv('ONCE_PAT')
    if not pat:
        raise SystemExit('ONCE_PAT not found in .env '
                         '(run this from the repo root).')

    sess = session(pat)

    print('Reading ONCE…', file=sys.stderr)
    releases = get_releases(sess)
    if not releases:
        raise SystemExit('ONCE returned no releases for this account.')

    query = ' '.join(args.title).strip()
    matched = match_releases(releases, query)
    if not matched:
        show_candidates(releases)
        return 2

    if args.limit:
        matched = matched[:args.limit]

    plain, md = [], []
    for i, summary in enumerate(matched, 1):
        print(f'  [{i}/{len(matched)}] {header_line(summary)}', file=sys.stderr)
        payload = get_release(sess, summary['id'])
        debug_dir = os.getenv('ALBUM_STATUS_DEBUG_DIR')
        if debug_dir:
            Path(debug_dir).mkdir(parents=True, exist_ok=True)
            dump = Path(debug_dir) / f"{summary['id']}.json"
            dump.write_text(json.dumps(payload, indent=1, ensure_ascii=False),
                            encoding='utf-8')
            print(f'    raw -> {dump}', file=sys.stderr)
        release = dict(summary)
        release.update(payload.get('release') or {})
        tracks = sorted(payload.get('tracks') or [],
                        key=lambda t: (t.get('disc_number') or 1,
                                       t.get('track_number') or 0))
        plain.extend(build_report(release, tracks))
        if args.md is not None:
            md.extend(build_report(release, tracks, markdown=True))

    text = '\n'.join(plain)
    print(text)

    # ---------------------------------------------------------------- files
    if args.save is not None:
        path = Path(args.save) if args.save else Path('album_status_report.txt')
        path.write_text(text + '\n', encoding='utf-8')
        print(f'\nSaved: {path.resolve()}', file=sys.stderr)

    if args.md is not None:
        path = Path(args.md) if args.md else Path('album_status_report.md')
        path.write_text('\n'.join(md) + '\n', encoding='utf-8')
        print(f'Saved: {path.resolve()}', file=sys.stderr)

    return 0


if __name__ == '__main__':
    raise SystemExit(main())

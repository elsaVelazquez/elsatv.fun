# lore/music_lore_scripts/

Scripts for the **music** collection: albums, songs, release links.
Feeds `kissingface.html` and `lore/songs.json`.

## These scripts are not in this folder

They live at the **repo root**, and that is on purpose. Two things call them by
a path relative to the repo root:

- `.github/workflows/sync-releases.yml` → `python FINAL_SYNC.py` (nightly cron)
- `publish.sh` → `build_albums.py`, then `FINAL_SYNC.py`

Moving them here would break the nightly release sync.

| File (at repo root)      | What it does                                              |
| ------------------------ | --------------------------------------------------------- |
| `FINAL_SYNC.py`          | Main sync. Writes `kissingface.html` + `lore/songs.json`. |
| `build_albums.py`        | Builds album tracklists from ONCE.                        |
| `add_link.py`            | Pin a YouTube link for one album by hand.                 |
| `collect_music_links.py` | The link scraper. Untracked / local only.                 |

If you later want them physically in this folder, the move is safe — just do it
in three steps at once: move the files, edit `publish.sh`, edit the workflow.
Everything else in the repo only cares about the two output files.

## Data these scripts use

- `lore/manual_links.json` — hand-entered links, highest priority, never overwritten
- `lore/music_links_enriched.json` — the per-song links
- `lore/yt_link_cache.json` — cache, so a run does not re-scrape
- `lore/songs.json` — output

## The one command (use this, not FINAL_SYNC.py alone)

```bash
venv/bin/python scripts/lore/music_lore_scripts/sync_music.py
```

**Why `FINAL_SYNC.py` alone is not enough:** FINAL_SYNC only *reads* song
links out of `lore/music_links_enriched.json`. It never discovers them. The
script that fills that file — `collect_music_links.py` — is a separate step, and
if it is not run a new release gets a card whose tracklist has **plain,
unlinked song names**, and re-running FINAL_SYNC any number of times will never
fix it.

`sync_music.py` runs the whole chain, in order:

| Step | Script | Writes | Network |
| --- | --- | --- | --- |
| 1 | `build_albums.py` | `lore/albums.json` | ONCE |
| 2 | `collect_music_links.py` | `lore/music_links_enriched.json` | YouTube Music, Apple, Spotify |
| 3 | `FINAL_SYNC.py` | `kissingface.html`, `lore/songs.json` | ONCE |

Then it lists any song name still rendered without a link.

```bash
--skip-links   # steps 1-2 skipped; just rebuild the page from existing JSON
--push         # also git add the generated files, commit "Update music page", push
```

Step 2 needs `ytmusicapi` in the venv (once):

```bash
venv/bin/python -m pip install ytmusicapi==1.12.3
```

### Stale-link guard

`collect_music_links.py` rebuilds the enriched file from scratch, so a lookup
that fails on a rerun could drop a link found earlier. `sync_music.py` merges
the old file into the new one first: a song link already known is kept when the
new run did not re-find it. Links are never removed by a sync.

### Files a music sync can change (stage all of them)

```
kissingface.html  lore/songs.json  lore/albums.json  lore/music_links_enriched.json
lore/yt_link_cache.json  lore/releases_cache.json  lore/release_dates.json
```

Committing only `songs.json` + the page loses `albums.json` and the enriched
song links, and the next run has nothing to attach.

### The nightly GitHub Action does not fix song links either

`.github/workflows/sync-releases.yml` runs `FINAL_SYNC.py` only — not
`build_albums.py`, not `collect_music_links.py`. So it keeps the page current
for links it already knows, but it cannot add song links for a new release.

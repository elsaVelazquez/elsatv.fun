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

# elsatv.fun

Static site for DJ Elsa. `kissingface.html` is the music archive page, generated
by `FINAL_SYNC.py`.

## Run it

```bash
cd /path/to/elsatv.fun
source venv/bin/activate
python FINAL_SYNC.py
```

Needs `ONCE_PAT` and `API_KEY` in `.env` (not committed).

Takes ~3 minutes — almost all of it ONCE's per-release status endpoint.

## What it does

```
ONCE releases (all of them, any status)
      │
      ├── 0. lore/manual_links.json        hand-entered, highest priority
      ├── 1. ONCE urlInStore               exact YouTube Music track link
      ├── 2. scrape @elsavelaz/releases   1 request, no API quota
      └── 3. blank → "Coming soon" card
      │
      ├── cover = https://i.ytimg.com/vi/<id>/hqdefault.jpg
      ▼
kissingface.html  +  lore/songs.json  +  lore/yt_link_cache.json
```

No YouTube Data API search calls — that is what caused the 429s. The releases
page is scraped once per run.

## Files that matter

| File                      | Role                                                                               |
| ------------------------- | ---------------------------------------------------------------------------------- |
| `FINAL_SYNC.py`           | the whole pipeline; regenerates `kissingface.html`                                 |
| `add_link.py`             | add a hand-entered link (below)                                                    |
| `lore/manual_links.json`  | **your** links — never overwritten by a sync                                       |
| `lore/yt_link_cache.json` | resolved links by ONCE release id; only hits are stored, so blanks retry every run |
| `lore/songs.json`         | generated output: one row per release + `cover_art`                                |
| `kissingface.html`        | generated output — do not hand-edit, a sync will overwrite it                      |
| `Instructions.md`         | your notes                                                                         |
| `albums.json`             | scraped fallback album list                                                        |

`archive/` holds the retired sync scripts (`archive/scripts/`) and the docs that
described them (`archive/docs/`). Nothing in there is used any more — it is kept
for history only.

## When a release shows "Coming soon"

Usually ONCE has it as `attention_needed`, so there is no store link yet. If
it _is_ live on YouTube, copy the link from
[youtube.com/@elsavelaz/releases](https://www.youtube.com/@elsavelaz/releases)
and add it:

```bash
python add_link.py "Album Name" "https://www.youtube.com/watch?v=XXXXXXXXXXX&list=OLAK5uy_..."

python add_link.py --list      # what's pinned manually
python add_link.py --missing   # what still has no link
```

The `album_link` is derived from the `list=OLAK5uy_…` part automatically.
Entries in `manual_links.json` win over ONCE and the scrape, and survive every
re-sync.

## Notes

- ONCE cover-art URLs (`once.app/api/files/...`) are account-private and return
  404 in a browser, so covers always come from the YouTube thumbnail.
- `.env` is gitignored. Never commit it.

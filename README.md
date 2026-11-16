# elsatv.fun

Static site for DJ Elsa. Two generated pages:

| Page | Built by | Data |
| --- | --- | --- |
| `kissingface.html` | `scripts/lore/music_lore_scripts/FINAL_SYNC.py` | ONCE + YouTube links |
| `posts.html` | `scripts/lore/yt_posts_lore_scripts/build_posts_html.py` | YouTube community posts |

`./publish.sh` publishes **only** the music page. The posts page is published
with `git add posts.html` — `lore/YTelsaTVposts/` is gitignored, so adding that
folder makes `git add` fail and blocks the chained commit and push.

## Run it

**Always run from the repo root**, not from inside `scripts/`:

```bash
cd /path/to/elsatv.fun
venv/bin/python scripts/lore/music_lore_scripts/FINAL_SYNC.py
```

`FINAL_SYNC.py` lives in `scripts/lore/music_lore_scripts/`, and resolves
`lore/`, `.env` and `kissingface.html` relative to the working directory.

Needs `ONCE_PAT` and `API_KEY` in `.env` (not committed).

Takes ~3 minutes — almost all of it ONCE's per-release status endpoint.

## Publish it

Running the script only rewrites files **on this machine**. Nothing reaches
`https://elsatv.fun` until you commit and push:

```bash
git add kissingface.html lore/songs.json lore/yt_link_cache.json
git commit -m "Update music page"
git push origin main
open "https://elsatv.fun/kissingface.html"   # then cmd+shift+r
```

`./publish.sh` does the sync, commit and push in one step. It does **not** touch
`posts.html` — see the section at the end of `Instructions.md` for that page.

### Why "it says DONE but the page didn't change"

Three separate causes, in the order to check them:

1. **Not pushed.** `git status` shows the files as modified. Run the commit+push
   above.
2. **Browser cache.** GitHub Pages sends `cache-control: max-age=600`, so the
   browser shows a 10-minute-old copy. Hard reload (`cmd+shift+r`) or use a
   private window — a private window has no cache, so it shows the truth.
3. **Checked the wrong file.** `kissingface.html` is the music page;
   `index.html` is the homepage and is hand-edited.

A "Coming soon" card is not a publish failure — it means there is no YouTube
link for that release yet (see below).

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
| `FINAL_SYNC.py`           | the whole pipeline; regenerates `kissingface.html` (`scripts/lore/music_lore_scripts/`) |
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
venv/bin/python scripts/lore/music_lore_scripts/add_link.py "Album Name" "https://www.youtube.com/watch?v=XXXXXXXXXXX&list=OLAK5uy_..."

venv/bin/python scripts/lore/music_lore_scripts/add_link.py --list      # what's pinned manually
venv/bin/python scripts/lore/music_lore_scripts/add_link.py --missing   # what still has no link
```

The `album_link` is derived from the `list=OLAK5uy_…` part automatically.
Entries in `manual_links.json` win over ONCE and the scrape, and survive every
re-sync.

## Notes

- ONCE cover-art URLs (`once.app/api/files/...`) are account-private and return
  404 in a browser, so covers always come from the YouTube thumbnail.
- `.env` is gitignored. Never commit it.

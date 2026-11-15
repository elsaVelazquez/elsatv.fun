# scripts/ — where everything lives

Every script in the repo lives inside one of three folders. The folder tells you
which part of the site the script belongs to. Nothing script-related sits at the
repo root except `publish.sh`, which is the button you press.

```
elsatv.fun/
├── publish.sh                      ← the one command you run
├── index.html                      ← front page (hand-edited)
├── kissingface.html                ← music page (generated, never hand-edit)
│
├── scripts/
│   ├── homepage_scripts/           ← the front page (index.html)
│   └── lore/
│       ├── music_lore_scripts/     ← music page + albums/songs data
│       └── yt_posts_lore_scripts/  ← YouTube community posts archive
│
└── lore/                           ← DATA only, no scripts
    ├── songs.json, yt_link_cache.json, manual_links.json, albums.json, ...
    └── YTelsaTVposts/              ← the posts corpus (gitignored)
```

Rule of thumb: **if you need to know which part of the site a script changes,
look at the folder it is in.** A script in `music_lore_scripts/` can only affect
the music page; a script in `yt_posts_lore_scripts/` can only affect the posts
archive. They do not import each other and share no data.

---

## 1. `homepage_scripts/` — the front page

Scripts that touch `index.html`.

**Status: empty.** `index.html` is hand-edited at the repo root. This folder
exists so the first homepage script has an unambiguous home.

---

## 2. `lore/music_lore_scripts/` — the music page

Feeds `kissingface.html` and `lore/songs.json`.

| Script                  | What it does                                        | Tracked?     |
| ----------------------- | --------------------------------------------------- | ------------ |
| `FINAL_SYNC.py`         | the main sync — writes `kissingface.html`, `songs.json` | no (local)   |
| `build_albums.py`       | builds the album tracklists from ONCE               | no (local)   |
| `add_link.py`           | pin one album's YouTube link by hand                | no (local)   |
| `collect_music_links.py`| scrapes the release links                           | no (local)   |

Run them **from the repo root**, because every path inside them is relative to
it (`.env`, `lore/songs.json`, `kissingface.html`). `publish.sh` does exactly
this, and so does the nightly Action:

```bash
./publish.sh                       # normal routine
venv/bin/python scripts/lore/music_lore_scripts/FINAL_SYNC.py   # sync alone
```

`.github/workflows/sync-releases.yml` calls that same path. If you ever rename a
file here, that workflow and `publish.sh` are the two places to change.

---

## 3. `lore/yt_posts_lore_scripts/` — the YouTube community posts archive

Feeds `lore/YTelsaTVposts/posts.html`. **Everything for it is in this folder.**

Run these from the **repo root** as well — they read and write
`lore/YTelsaTVposts/...` relative to where you stand.

### The pipeline, in order

| Step | Script                | Reads                        | Writes                                        |
| ---- | --------------------- | ---------------------------- | --------------------------------------------- |
| 1    | `archive_posts.py`    | youtube.com/@elsaTVfun/posts | `lore/posts/index.json`, `lore/posts/images/` |
| 2    | `post_dates.py`       | `index.json`                 | `dates.json` (Mountain Time)                  |
| 3    | `post_comments.py`    | each post URL                | `comments.json`                               |
| 4    | `ocr_images.py`       | `images/`                    | `ocr.json` (tesseract, pass 1)                |
| 5    | `ocr_multi.py`        | `images/`                    | `ocr_extra.json` (tesseract, multi-pass)      |
| 6    | `ocr_llm_openai.py`   | `images/`                    | `llm_text.json` (vision model, verbatim)      |
| 7    | `stamp_images.py`     | `images/`                    | `datestamped/` (date bar on top)              |
| 8    | `build_day_index.py`  | all of the above             | `days.json`                                   |
| 9    | `build_posts_html.py` | `days.json`                  | `posts.html`                                  |

Only steps 1–3 hit the network. Steps 4–9 are local, free, and re-runnable.

`ocr_llm.py` (Gemini) is **not used** — the key in `.env` is a Google Cloud key
that the Gemini API rejects. `ocr_llm_openai.py` is the one with the cost caps,
and it needs an `OPENAI_API_KEY` in `.env`.

### The short version

```bash
venv/bin/python scripts/lore/yt_posts_lore_scripts/build_day_index.py
venv/bin/python scripts/lore/yt_posts_lore_scripts/build_posts_html.py
```

Those two rebuild the page from data that is already on disk. That is what you
run on a normal day.

### Where images live

Every image in `posts.html` is a **local file on your disk**, not a YouTube
URL:

- `lore/YTelsaTVposts/images/` — the originals, 1,617 files
- `lore/YTelsaTVposts/datestamped/` — the same images with the date bar

`posts.html` points at `datestamped/<file>` and falls back to `images/<file>`.
Both folders are gitignored, so **the images are not on GitHub and not on
GitHub Pages** — only ever on your machine (and wherever you choose to copy
them). See `lore/YTelsaTVposts/README.md`.

---

## `_backups/` and `archive/`

Neither is live code.

- `archive/` — the old release-sync attempts, superseded by `FINAL_SYNC.py`.
- `_backups/` — dated copies of `FINAL_SYNC.py` / `build_albums.py` kept for
  rollback.

Nothing in either folder is called by `publish.sh`, the workflow, or any script
in `scripts/`.
# Daily publish

```sh
./publish.sh
```

That's the whole routine. It syncs, commits the three generated files, and
pushes. If nothing changed it stops without committing.

Run manually instead:

```sh
cd <project-folder>
source venv/bin/activate
# your prompt now starts with (venv)
python -V        # sanity check: should be 3.13
```

Then, for a hand-edited page such as `index.html`:

```sh
git status                       # what's modified
git diff index.html              # read your own changes
git add index.html
git commit -m "Homepage: describe your change here"
git push origin main
```

## If making changes to other pages besides kissingface

`main` takes direct pushes, so there is no pull request and nothing to
"merge" — the push is the update. Use a branch only when you *want* a diff to
review before it goes live:

```sh
git switch -c notes/instructions
git commit -am "Notes: my personal instructions"
git push -u origin notes/instructions
```

GitHub then offers "Compare & pull request" for that branch.

## When to use ./publish.sh instead

If your change is to the music page (`kissingface.html`) or the album/track
data — i.e. you edited `manual_links.json` and want the page regenerated —
then:

```sh
venv/bin/python scripts/lore/music_lore_scripts/FINAL_SYNC.py
```

Always run script commands **from the repo root** (`~CODE/elsatvfun/elsatv.fun`),
not from inside `scripts/`. The scripts find `lore/`, `.env` and `kissingface.html`
relative to wherever you are standing.

## What a normal run does (about 20 seconds)

1. GET the ONCE release list — this is how new releases are found
2. Every link already in `lore/yt_link_cache.json` or `lore/manual_links.json`
   is reused. **No ONCE status lookups, no scraping for those.**
3. The releases page is only scraped if something genuinely new or unresolved
   appears
4. Writes `kissingface.html`, `lore/songs.json`, `lore/yt_link_cache.json`

Releases already looked for and not found are marked `checked_status`, so they
are skipped until their ONCE status changes (e.g. they go live).

## When a new release says "Coming soon"

It means ONCE has no store link yet. If you can see it on YouTube:

```sh
venv/bin/python scripts/lore/music_lore_scripts/add_link.py "Album Name" "https://www.youtube.com/watch?v=XXX&list=OLAK5uy_..."

venv/bin/python scripts/lore/music_lore_scripts/add_link.py --missing   # what still needs one
venv/bin/python scripts/lore/music_lore_scripts/add_link.py --list      # what is pinned manually
```

Then commit the manual file too, or the link only exists on this machine:

```sh
git add lore/manual_links.json && git commit -m "Add link for Album Name"
```

## Things to remember

- `kissingface.html` is generated — never hand-edit it, a sync overwrites it.
- `.env` is gitignored and stays local. Never commit it, never paste its
  contents anywhere.
- `manual_links.json` wins over ONCE and the scrape, and is never overwritten.

## to add links manually

-while in main:

```sh
git add lore/manual_links.json
git commit -m "manual_links: Real Dream Is Real; honour typed playlists"
./publish.sh
```

## Updating https://elsatv.fun/posts.html

`./publish.sh` is for the **music page only** — it never touches `posts.html`.
The posts page has its own orchestrator, run from the repo root:

```sh
venv/bin/python scripts/lore/yt_posts_lore_scripts/sync_posts.py
```

That is the one command. It looks at what is already on disk and fetches only
what is missing — new post ids only, new images only, new dates and comments
only — then rebuilds `days.json` and `posts.html`. Nothing already collected is
re-downloaded. `--dry-run` reports what it would do and exits without writing.

**This script does not commit or push.** It has no git calls on purpose —
review the page first, then publish it yourself:

```sh
git add posts.html
git commit -m "Posts: sync"
git push origin main
```

### `git add posts.html` is the whole `git add`

Only `posts.html` (repo root) ships to GitHub. Everything else the pipeline
writes lives in `lore/YTelsaTVposts/`, which is **gitignored on purpose**
(1.7 GB of images plus the JSON that is regenerated from them).

So never run this:

```sh
git add posts.html lore/YTelsaTVposts/     # ✗ fails, folder is ignored
```

`git add` exits non-zero on the ignored path, and because the command is
chained with `&&`, the commit and push never run — the page looks "not
updated" while everything actually worked. Add `posts.html` alone.

The images are not in the repo at all: `posts.html` links them from YouTube's
CDN (`yt3.ggpht.com/...=s800`), so nothing large is stored on GitHub.

### What the sync prints

Seen on a real run that picked up one new post:

```sh

▸ 1/7 fetch posts not already in index.json
  $ /Volumes/storage2-end-sep2025-to-future/CODE/elsatvfun/elsatv.fun/scripts/lore/yt_posts_lore_scripts/archive_posts.py
→ https://www.youtube.com/@elsaTVfun/posts
  posts on first page: 10
  on disk already: 203 post(s)
  page 1: all known — stopping
  seen in feed: 20, new: 1
  [1/1] 10/10 images
  images downloaded this run: 9.4 MB

→ lore/YTelsaTVposts/index.json
→ lore/YTelsaTVposts/posts.md
  204 posts (1 new, 0 metadata updates), 1655 images
  ✓ archive_posts.py (7.1s)

new: 1 post(s), 10 image(s)
  + 4 hours ago                      10 img  Nov 15 2026 Vortex(0, 6, 0) in my SIM in these songs, I show

▸ 2/7 dates for 1 new post(s)
  $ /Volumes/storage2-end-sep2025-to-future/CODE/elsatvfun/elsatv.fun/scripts/lore/yt_posts_lore_scripts/post_dates.py --limit 1
→ resolving 1 post date(s)
  [1/1] 2026-11-15  Nov 15, 2026 3:39 PM

→ lore/YTelsaTVposts/dates.json
  204 post(s) dated, 0 without a date
  ✓ post_dates.py (0.9s)

▸ 3/7 comments for 1 new post(s)
```

OCR is deliberately not in `sync_posts.py` — it is the slow, paid step. Run it
afterwards on the new images only, then rebuild the page:

```sh
venv/bin/python scripts/lore/yt_posts_lore_scripts/ocr_multi.py --limit 20
venv/bin/python scripts/lore/yt_posts_lore_scripts/ocr_llm_openai.py --max-cost 0.10
venv/bin/python scripts/lore/yt_posts_lore_scripts/build_posts_html.py
```


use these commands to update https://elsatv.fun/posts.html:

```sh
venv/bin/python scripts/lore/yt_posts_lore_scripts/sync_posts.py
git add posts.html
git commit -m "Posts: sync"
git push origin main
```

use this to update the  https://elsatv.fun/kissingface.html


```sh
venv/bin/python scripts/lore/music_lore_scripts/FINAL_SYNC.py
git add kissingface.html lore/songs.json lore/yt_link_cache.json
git commit -m "Update music page"
git push origin main
open "https://elsatv.fun/kissingface.html"
```

then cmd + shift + r


to do all the above using automation, put this into command line 1 time, have to authorize bash to run scripts on mac:

```sh
➜  elsatv.fun git:(main) ✗ chmod +x daily_sync.sh
./daily_sync.sh
./daily_sync.sh: line 1: cd: /Users/elsa/elsatv.fun: No such file or directory
➜  elsatv.fun git:(main) ✗ ./daily_sync.sh
```

to update the home page

```sh
git add index.html
git commit -m "feat: add notes here"
git push origin main
```

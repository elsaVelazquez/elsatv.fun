# lore/yt_posts_lore_scripts/

Scripts for the **YouTube community posts** collection.
Feeds `lore/YTelsaTVposts/posts.html`.

Everything for this section is in this folder. Nothing outside it is needed.

## Run from the repo root

These scripts read and write `lore/YTelsaTVposts/...` relative to the directory
you run them from. So:

```bash
cd ~/CODE/elsatvfun/elsatv.fun          # repo root, NOT this folder
venv/bin/python scripts/lore/yt_posts_lore_scripts/build_day_index.py
```

## The pipeline, in order

| #   | Script                | Reads                        | Writes                           | Network?         |
| --- | --------------------- | ---------------------------- | -------------------------------- | ---------------- |
| 1   | `archive_posts.py`    | youtube.com/@elsaTVfun/posts | `lore/posts/index.json` + images | yes              |
| 2   | `post_dates.py`       | `index.json`                 | `dates.json` (Mountain Time)     | no               |
| 3   | `post_comments.py`    | each post URL                | `comments.json`                  | yes              |
| 4   | `ocr_images.py`       | `images/`                    | `ocr.json`                       | no               |
| 5   | `ocr_multi.py`        | `images/`                    | `ocr_extra.json`                 | no               |
| 6   | `ocr_llm_openai.py`   | `images/`                    | `llm_text.json`                  | yes, costs money |
| 7   | `stamp_images.py`     | `images/`                    | `datestamped/`                   | no               |
| 8   | `build_day_index.py`  | all of the above             | `days.json`                      | no               |
| 9   | `build_posts_html.py` | `days.json`                  | `posts.html`                     | no               |

Steps 4, 5 and 6 do the same job three ways (tesseract once, tesseract
multi-pass, then a vision model). Their outputs sit in three separate files so
none overwrites another. `build_day_index.py` reads all three and
`build_posts_html.py` shows them in that order under each image.

`sync_posts.py` runs steps 1–3, then 7, then 4–6 **only for the images with no
reading yet**, then 8–9. See "The one command" below.

`ocr_llm.py` is the Gemini version — **not used**. The key in `.env` is a Google
Cloud key and the Gemini API rejects it. Use `ocr_llm_openai.py`, which needs
`OPENAI_API_KEY` in `.env` and refuses to run without a cost cap.

## The one command (this now includes the image text)

```bash
venv/bin/python scripts/lore/yt_posts_lore_scripts/sync_posts.py
```

Steps in order: archive new posts → dates → comments → stamp → web copies →
**read the text of every image that has none yet** → rebuild `days.json` and
`posts.html`. Nothing already read is re-read or re-paid.

### How the OCR step decides what to read

| Pass | Script | Stored in | Re-reads? | Cost |
| --- | --- | --- | --- | --- |
| 1 | `ocr_images.py` | `ocr.json` | no (always called with `--only`) | free, local |
| 2 | `ocr_multi.py` | `ocr_extra.json` | no (skips anything present) | free, local |
| 3 | `ocr_llm_openai.py` | `llm_text.json` | no (skips anything present) | paid, capped |

`sync_posts.py` computes the unread images itself (`unread_images()`), in post
order (oldest first), and passes them to each script as `--only a.jpg,b.jpg` in
batches of 400. Passes 1 and 2 run to completion. Pass 3 stops at `--max-cost`
(default **$0.50 per run**) and saves after every 20 images, so each later sync
picks up where the last one stopped. A full catch-up of the archive therefore
takes a few runs, and nothing is ever spent twice.

Flags:

```bash
--max-cost 0.50    # vision-model ceiling for THIS run (default 0.50)
--max-cost 0        # skip the paid pass (free passes still run)
--no-ocr            # skip all OCR this time; page still rebuilds
--dry-run           # fetch nothing, read nothing, write nothing
```

At the end of every run it prints how many images each pass is still missing,
and writes ready-to-paste commands for exactly those files to
`lore/YTelsaTVposts/ocr_todo.txt` (gitignored, regenerated each run) — for manual
top-ups only; normally you do not need it.

### `--limit` vs `--only` (why the old command was misleading)

`--limit N` on `ocr_multi.py` / `ocr_llm_openai.py` means "the first N *unread
by filename*" — which is old images, not new ones. `ocr_images.py --limit N`
means "the first N files alphabetically" and rewrites them regardless. Use
`--only` to target a specific set.

## Free, local rebuild only

```bash
venv/bin/python scripts/lore/yt_posts_lore_scripts/build_day_index.py
venv/bin/python scripts/lore/yt_posts_lore_scripts/build_posts_html.py
```

No network, about a second. Use this after any hand-run OCR script.

## Images are local files, not YouTube links

`posts.html` references `datestamped/<file>` (falling back to `images/<file>`)
relative to the HTML file. Those are files on disk:

- `lore/YTelsaTVposts/images/` — originals, 1,617 files
- `lore/YTelsaTVposts/datestamped/` — with the date bar, 1,617 files

Neither folder is on GitHub. Both are gitignored. The page works when opened
straight from disk; the images just have to sit next to it.

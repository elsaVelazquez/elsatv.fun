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

`ocr_llm.py` is the Gemini version — **not used**. The key in `.env` is a Google
Cloud key and the Gemini API rejects it. Use `ocr_llm_openai.py`, which needs
`OPENAI_API_KEY` in `.env` and refuses to run without a cost cap.

## The normal day

```bash
venv/bin/python scripts/lore/yt_posts_lore_scripts/build_day_index.py
venv/bin/python scripts/lore/yt_posts_lore_scripts/build_posts_html.py
```

Free, local, no network, about a second.

## Images are local files, not YouTube links

`posts.html` references `datestamped/<file>` (falling back to `images/<file>`)
relative to the HTML file. Those are files on disk:

- `lore/YTelsaTVposts/images/` — originals, 1,617 files
- `lore/YTelsaTVposts/datestamped/` — with the date bar, 1,617 files

Neither folder is on GitHub. Both are gitignored. The page works when opened
straight from disk; the images just have to sit next to it.

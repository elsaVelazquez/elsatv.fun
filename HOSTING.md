# Hosting the posts images — R2, the drive, and the Internet Archive

Three copies of the same 1,617 pictures, each doing a different job:

| Copy         | Where               | Job                                              | Cost         |
| ------------ | ------------------- | ------------------------------------------------ | ------------ |
| **Delivery** | Cloudflare R2       | what `posts.html` shows when YouTube's CDN fails | free (10 GB) |
| **Master**   | your external drive | the real archive, the one that never moves       | already paid |
| **Third**    | Internet Archive    | long-term, independent, survives you             | free         |

The page itself (`posts.html`) stays on GitHub Pages. It is one static file, so
Pages is fine. The _pictures_ cannot live there — Pages has a 1 GB limit and the
stamped set is ~0.9 GB before anything else — which is the whole reason for R2.

---

## Before you start (5 minutes, once)

You already have two of the three. The drive copy is on disk. Nothing else
needs an account except R2.

```bash
cd /Volumes/storage2-end-sep2025-to-future/CODE/elsatvfun/elsatv.fun
venv/bin/python -c "import boto3" || TMPDIR=/Volumes/storage2-end-sep2025-to-future/tmp venv/bin/pip install boto3
```

`boto3` is the S3 client that talks to R2. Already installed here.

---

## Step 1 — Make the R2 bucket and a key (you do this in a browser)

1. Go to <https://dash.cloudflare.com> and sign up or log in. **No credit card
   is asked for.** Free R2 stays free; there is no trial that expires.
2. Left sidebar → **R2 Object Storage** → **Create bucket**.
   - Name: `elsatv-images` (must match `R2_BUCKET` below)
   - Location: **Automatic**
   - Click **Create bucket**.
3. Still in R2, click **Manage R2 API Tokens** (top right of the R2 page) →
   **Create API token**.
   - Token name: `elsatv-upload`
   - Permissions: **Object Read & Write**
   - Specify bucket: `elsatv-images` only
   - TTL: leave as-is
   - **Create API Token**
4. The next screen shows four things **once**. Copy them somewhere safe right
   now — the secret is not shown again:
   - Account ID
   - Access Key ID
   - Secret Access Key
   - (the endpoint URL also contains your Account ID)

That's the only fiddly part. Everything after this is one command.

---

## Step 2 — Put the four values in `.env`

`.env` is already gitignored, so these never reach GitHub.

```bash
cd /Volumes/storage2-end-sep2025-to-future/CODE/elsatvfun/elsatv.fun
cat >> .env <<'EOF'

# Cloudflare R2 — image delivery for posts.html
R2_ACCOUNT_ID=paste-account-id
R2_ACCESS_KEY_ID=paste-access-key-id
R2_SECRET_ACCESS_KEY=paste-secret
R2_BUCKET=elsatv-images
EOF
```

Then check it parses (it will say "missing in .env" if a paste went wrong):

```bash
venv/bin/python scripts/lore/yt_posts_lore_scripts/sync_r2.py --check
```

---

## Step 3 — Make the bucket publicly readable

R2 buckets are private by default. The page needs to read them with no key.

**Option A — custom domain on your own site (recommended)**

1. R2 → `elsatv-images` → **Settings** → **Public access** →
   **Connect Domain**.
2. Type `img.elsatv.fun` (or any subdomain of a domain already on Cloudflare).
   Cloudflare adds the DNS record for you.
3. Wait for the status to say **Active** (usually under a minute with the
   domain already on Cloudflare). Files are then at
   `https://img.elsatv.fun/datestamped/<file>`.

**Option B — the free `r2.dev` endpoint (no domain work)**

1. Same page → **Public access** → **R2.dev subdomain** → **Allow access**.
2. Copy the URL it gives you, like `https://pub-1a2b3c4d5e.r2.dev`.

Either works. Option A gives a URL that looks like your site and can be moved
later; Option B is two clicks and no DNS. **Use A if `elsatv.fun` is already on
Cloudflare; use B otherwise.**

---

## Step 4 — Upload the images

```bash
cd /Volumes/storage2-end-sep2025-to-future/CODE/elsatvfun/elsatv.fun

# look first, no uploading
venv/bin/python scripts/lore/yt_posts_lore_scripts/sync_r2.py --dry-run

# then for real
venv/bin/python scripts/lore/yt_posts_lore_scripts/sync_r2.py --public-base https://img.elsatv.fun
```

About 0.9 GB, so a few minutes on a normal connection. It prints progress every
25 files and skips anything already in the bucket, so:

- **you interrupted it?** run the same command again, it picks up where it stopped
- **you added three new posts?** run the same command again, it uploads three files

At the end it prints the exact line to paste in Step 5.

---

## Step 5 — Point the page at the bucket

Open `scripts/lore/yt_posts_lore_scripts/build_posts_html.py`, find line 79:

```python
FALLBACK_BASE = ''
```

and make it the URL from Step 3:

```python
FALLBACK_BASE = 'https://img.elsatv.fun'
```

Then rebuild and publish:

```bash
cd /Volumes/storage2-end-sep2025-to-future/CODE/elsatvfun/elsatv.fun
venv/bin/python scripts/lore/yt_posts_lore_scripts/build_day_index.py
venv/bin/python scripts/lore/yt_posts_lore_scripts/build_posts_html.py

# the builder writes lore/YTelsaTVposts/posts.html; the root copy is what Pages serves
cp lore/YTelsaTVposts/posts.html posts.html

git add posts.html scripts/lore/yt_posts_lore_scripts/build_posts_html.py scripts/lore/yt_posts_lore_scripts/sync_r2.py
git commit -m "posts: images fall back to Cloudflare R2"
git push origin main
```

---

## Step 6 — Prove it works

Check the bucket serves a real file. Take any name from the build output:

```bash
ls lore/YTelsaTVposts/datestamped | head -1
# then open in a browser:
#   https://img.elsatv.fun/datestamped/<that-name>
```

It should show the picture **with the black date bar across the top**. If it
downloads instead of displaying, or 404s, the bucket is not public yet — go
back to Step 3.

Check the page carries the fallback:

```bash
grep -c 'data-fallback=' posts.html     # should be 1617
```

Then open <https://elsatv.fun/posts.html>. The page loads images from YouTube's
CDN as before. To see the fallback actually take over, in Safari:

1. Open the page.
2. Develop → Disable Images, then re-enable — or simply turn off Wi-Fi and
   scroll: pictures already cached stay, uncached ones swap to R2.

The behaviour is: YouTube's copy first (fast, free), R2 if that copy fails
(deleted video, CDN error, blocked network). Nobody sees a broken image.

---

## Step 7 — The third copy: Internet Archive

R2 can be suspended, a domain can lapse, and a drive can be dropped. The
Archive is the copy that outlives all three. Do this **after** the page is
working, because it is the slowest step and the one least likely to be urgent.

One command, and re-run it whenever you add a batch:

```bash
cd /Volumes/storage2-end-sep2025-to-future/CODE/elsatvfun/elsatv.fun
venv/bin/python scripts/lore/yt_posts_lore_scripts/archive_wayback.py --dry-run
venv/bin/python scripts/lore/yt_posts_lore_scripts/archive_wayback.py
```

What it does: submits `posts.html` to the Wayback Machine so the **page** is
captured, and writes `lore/YTelsaTVposts/datestamped/` as a single `.zip` that
you upload once to <https://archive.org/upload/> as an item (free account, free
item, no expiry). The zip is the part that matters: the page in the Wayback
capture will show whatever images Wayback also grabbed, and the zip guarantees
the set survives regardless.

Doing it by hand instead is fine too — the Archive's web uploader accepts a
folder drop. The script just saves you re-zipping 0.9 GB each time.

---

## The daily routine after today

Nothing changes about publishing music (`./publish.sh`). For posts, when you
scrape new ones:

```bash
venv/bin/python scripts/lore/yt_posts_lore_scripts/archive_posts.py      # new posts only
venv/bin/python scripts/lore/yt_posts_lore_scripts/post_dates.py
venv/bin/python scripts/lore/yt_posts_lore_scripts/stamp_images.py       # new images only
venv/bin/python scripts/lore/yt_posts_lore_scripts/build_day_index.py
venv/bin/python scripts/lore/yt_posts_lore_scripts/build_posts_html.py
venv/bin/python scripts/lore/yt_posts_lore_scripts/sync_r2.py            # new images only
cp lore/YTelsaTVposts/posts.html posts.html
git add posts.html && git commit -m "posts: new" && git push origin main
```

Every step above skips work it has already done, so the run costs only the new
posts.

---

## What can cost money, and what cannot

| Thing             | Money            | Notes                                         |
| ----------------- | ---------------- | --------------------------------------------- |
| R2 storage        | **$0**           | 10 GB free, permanently. You use ~0.9 GB.     |
| R2 reads (egress) | **$0**           | R2 charges nothing for downloads, ever.       |
| GitHub Pages      | **$0**           | 1 GB of _site_ storage; you use ~6 MB.        |
| Internet Archive  | **$0**           | Donations only, no plan.                      |
| Custom domain     | **already paid** | the domain you own. `img.` subdomain is free. |

The one thing that _would_ cost: leaving the free tier. You would have to store
roughly 11× what you have now before R2 asks for a card. At 1,617 images in
~19 months, that is not a thing that happens by accident.

With billing turned off (no card on file) Cloudflare cannot bill you at all —
if you somehow exceeded the free tier it would stop accepting writes, not send
an invoice. That is the behaviour you want from a host.

---

## If something goes wrong

| Symptom                     | Cause                                           | Fix                                                    |
| --------------------------- | ----------------------------------------------- | ------------------------------------------------------ |
| `missing in .env: R2_...`   | paste failed, or `.env` is not in the repo root | re-do Step 2, then `--check`                           |
| `SignatureDoesNotMatch`     | wrong secret, or extra spaces                   | re-copy the secret; no spaces around `=`               |
| `NoSuchBucket`              | bucket name typo                                | `R2_BUCKET` must be exactly the bucket name            |
| image URL 404s in a browser | bucket not public                               | Step 3, then test again                                |
| image URL downloads a file  | wrong content type                              | re-run `sync_r2.py`; it sets the type per file         |
| page shows broken images    | `FALLBACK_BASE` wrong, or not rebuilt           | check `grep -c data-fallback= posts.html`, redo Step 5 |
| fallback never fires        | CDN image loaded fine                           | that is success — the fallback is only for failures    |

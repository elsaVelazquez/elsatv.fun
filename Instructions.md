# Daily publish

```
./publish.sh
```

That's the whole routine. It syncs, commits the three generated files, and
pushes. If nothing changed it stops without committing.

Run manually instead:

```
venv/bin/python FINAL_SYNC.py
```

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

```
venv/bin/python add_link.py "Album Name" "https://www.youtube.com/watch?v=XXX&list=OLAK5uy_..."

venv/bin/python add_link.py --missing   # what still needs one
venv/bin/python add_link.py --list      # what is pinned manually
```

Then commit the manual file too, or the link only exists on this machine:

```
git add lore/manual_links.json && git commit -m "Add link for Album Name"
```

## Things to remember

- `kissingface.html` is generated — never hand-edit it, a sync overwrites it.
- `.env` is gitignored and stays local. Never commit it, never paste its
  contents anywhere.
- `manual_links.json` wins over ONCE and the scrape, and is never overwritten.

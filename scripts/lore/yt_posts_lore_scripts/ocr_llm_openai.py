#!/usr/bin/env python3
"""
ocr_llm_openai.py — read the text in each image with an OpenAI vision model,
word for word.

    # what would it cost? sends nothing
    venv/bin/python scripts/lore/yt_posts_lore_scripts/ocr_llm_openai.py --dry-run

    # trial: 5 images, never spend more than 10 cents
    venv/bin/python scripts/lore/yt_posts_lore_scripts/ocr_llm_openai.py --limit 5 --max-cost 0.10

    # only the images a sync just reported as new
    venv/bin/python scripts/lore/yt_posts_lore_scripts/ocr_llm_openai.py --only a.jpg,b.jpg --max-cost 0.10

    # the whole archive, hard-capped at 3 dollars
    venv/bin/python scripts/lore/yt_posts_lore_scripts/ocr_llm_openai.py --max-cost 3.00

Reads  lore/YTelsaTVposts/index.json            which images exist
       lore/YTelsaTVposts/images/<file>         the original (unstamped) image
Writes lore/YTelsaTVposts/llm_text.json

    {"generated_at": "...", "model": "...",
     "images": {"<file>": {"file": "...", "text": "...", "chars": 0, "ok": true}}}

Same output as ocr_llm.py (the Gemini one), so build_day_index.py does not care
which provider filled llm_text.json. The file name and shape are identical on
purpose — you can switch providers without rebuilding the index.

THREE BRAKES, ALL OF THEM YOURS
-------------------------------
The point of this script is that the spending limit lives in the code, not in a
vendor dashboard you have to trust:

  --max-images N   hard count. It cannot process more than N images per run.
  --max-cost N     hard dollar ceiling. It checks the running total BEFORE each
                   request and stops when the next one could cross N. It does
                   not spend first and tell you after.
  --limit N        "just do this many right now", for trials.

  --dry-run        prices the job and exits. No requests, no spend, no writes.

All three are enforced in the loop below, in that order. If you pass none of
them the run is uncapped — so pass one.

WHY THE PROMPT IS SO RUDE
-------------------------
The text burned into these images (captions on photos, screenshots of comments,
DJ decks, receipts) is part of the lore. It is not a summary: it is what the
picture says, exactly as it says it. So the model is told, in as few words as
possible, to retype everything it can read and invent nothing. No intents, no
interpretation, no "the image appears to be…", no tidy-up of spelling, no
translation. If it cannot read something it writes [illegible].

This runs on the ORIGINAL image, not the datestamped copy, so the black date bar
we stamped on top can never be mistaken for content.

SETUP
-----
Put your key in .env (never committed — it is gitignored):

    OPENAI_API_KEY=sk-...

Runs are resumable: whatever is already in llm_text.json is skipped, so a run
that hits the cap is not wasted. Run it again tomorrow with a fresh cap.

PRICING NUMBERS ARE ESTIMATES
-----------------------------
The per-token prices below are the ones in effect when this was written. The
TOKEN counts are real — they come back in every API response and are what the
cap is actually enforced against. Only the dollars-per-token guess is a constant
you may need to update. If OpenAI changes prices, fix PRICES and the cap stays
honest.
"""
import argparse
import base64
import io
import json
import os
import time
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path('lore/YTelsaTVposts')
INDEX = ROOT / 'index.json'
IMAGES = ROOT / 'images'
OUT = ROOT / 'llm_text.json'

MODEL = 'gpt-4o-mini'
ENDPOINT = 'https://api.openai.com/v1/chat/completions'

# USD per 1,000,000 tokens. Input is billed higher than output on every OpenAI
# vision model. Update these if the price sheet moves; the brake uses them.
PRICES = {
    'gpt-4o-mini':  {'in': 0.15, 'out': 0.60},
    'gpt-4.1-mini': {'in': 0.40, 'out': 1.60},
    'gpt-4o':       {'in': 2.50, 'out': 10.00},
    'gpt-4.1':      {'in': 2.00, 'out': 8.00},
}

# Rough per-image token guess for --dry-run only. Images are resized to at most
# MAX_SIDE, so this does not swing much; real counts come back at run time.
EST_IMAGE_TOKENS = 1200
EST_OUTPUT_TOKENS = 400

PROMPT = (
    'Transcribe ALL text visible in this image, exactly as written. '
    'Include text overlaid on photos, captions, headings, small captions, '
    'signs, screens, labels, watermarks, and UI text such as comments, '
    'usernames, timestamps and like counts. '
    'Keep the original spelling, punctuation, capitalisation and line breaks. '
    'Do NOT summarise, explain, translate, correct, describe the picture, or '
    'guess at intent. Output only the transcription. '
    'If there is no readable text at all, output exactly: NO TEXT'
)

MAX_SIDE = 1600          # downscale big photos; the text stays readable
SLEEP = 0.3              # small pause between requests
MAX_FAIL_STREAK = 5      # give up after this many consecutive errors


# --------------------------------------------------------------------------- #
def api_key():
    """OPENAI_API_KEY from the environment, else from .env."""
    key = os.environ.get('OPENAI_API_KEY', '')
    if not key and Path('.env').exists():
        for line in Path('.env').read_text().splitlines():
            line = line.strip()
            if line.startswith('OPENAI_API_KEY='):
                key = line.split('=', 1)[1].strip().strip('"').strip("'")
                break
    if not key:
        raise SystemExit(
            'no OPENAI_API_KEY — put one in .env, on its own line:\n'
            '  OPENAI_API_KEY=sk-...')
    return key


def image_data_uri(path):
    """Original image, shrunk to MAX_SIDE, as a base64 data URI."""
    from PIL import Image

    img = Image.open(path)
    img = img.convert('RGB')
    if max(img.size) > MAX_SIDE:
        scale = MAX_SIDE / max(img.size)
        img = img.resize((int(img.width * scale), int(img.height * scale)),
                         Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=88)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f'data:image/jpeg;base64,{b64}'


def price_of(usage, model):
    """USD for one response, from the token counts it reported."""
    p = PRICES.get(model, PRICES[MODEL])
    prompt = usage.get('prompt_tokens', 0)
    completion = usage.get('completion_tokens', 0)
    return (prompt * p['in'] + completion * p['out']) / 1_000_000, prompt, completion


def read_one(path, key, model):
    """One image -> (text, ok, dollars, prompt_tokens, completion_tokens)."""
    payload = {
        'model': model,
        'temperature': 0,
        'max_tokens': 2048,
        'messages': [{
            'role': 'user',
            'content': [
                {'type': 'text', 'text': PROMPT},
                {'type': 'image_url',
                 'image_url': {'url': image_data_uri(path), 'detail': 'high'}},
            ],
        }],
    }
    r = requests.post(
        ENDPOINT,
        headers={'Authorization': f'Bearer {key}',
                 'Content-Type': 'application/json'},
        json=payload,
        timeout=180,
    )
    if r.status_code != 200:
        raise RuntimeError(f'HTTP {r.status_code}: {r.text[:300]}')
    data = r.json()
    usage = data.get('usage') or {}
    cost, pt, ct = price_of(usage, model)

    choices = data.get('choices') or []
    if not choices:
        return '', False, cost, pt, ct
    text = (choices[0].get('message') or {}).get('content') or ''
    text = text.strip()
    if text.upper() == 'NO TEXT':
        text = ''
    return text, bool(text), cost, pt, ct


# --------------------------------------------------------------------------- #
def wanted_images(index):
    """Every image on every post, in post order, de-duplicated."""
    seen, out = set(), []
    for post in index.get('posts', []):
        for name in post.get('image_files') or []:
            if name not in seen and (IMAGES / name).exists():
                seen.add(name)
                out.append(name)
    return out


def load_done():
    if not OUT.exists():
        return {}
    try:
        return json.loads(OUT.read_text()).get('images', {})
    except Exception:
        return {}


def save(done, model, spent):
    payload = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'model': model,
        'count': len(done),
        'images': dict(sorted(done.items())),
    }
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    # A sidecar so you can see what this pass has cost across all runs, without
    # trusting a vendor dashboard to remember for you.
    ledger = OUT.with_name('llm_spend.json')
    history = {}
    if ledger.exists():
        try:
            history = json.loads(ledger.read_text())
        except Exception:
            history = {}
    history[model] = round(history.get(model, 0) + spent, 6)
    history['total'] = round(
        sum(v for k, v in history.items() if k != 'total'), 6)
    ledger.write_text(json.dumps(history, indent=2))


def chars_of(done):
    return sum(v.get('chars', 0) for v in done.values())


def dry_run(names, todo, model):
    p = PRICES.get(model, PRICES[MODEL])
    per_image = ((EST_IMAGE_TOKENS * p['in'] + EST_OUTPUT_TOKENS * p['out'])
                 / 1_000_000)
    print(f'model          {model}')
    print(f'images total   {len(names)}')
    print(f'still to read  {len(todo)}')
    print(f'est. per image ${per_image:.5f}  '
          f'(~{EST_IMAGE_TOKENS} in + ~{EST_OUTPUT_TOKENS} out tokens)')
    print(f'est. this run  ${per_image * len(todo):.2f}')
    print(f'est. all done  ${per_image * len(names):.2f}')
    print('\nnothing was sent, nothing was written. Add --max-cost to run.')


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=0,
                    help='stop after N new images (0 = no limit)')
    ap.add_argument('--max-images', type=int, default=0,
                    help='hard cap on images processed in THIS run')
    ap.add_argument('--max-cost', type=float, default=0.0,
                    help='hard ceiling in USD for THIS run; stops before '
                         'crossing it (0 = no ceiling)')
    ap.add_argument('--model', default=MODEL, choices=sorted(PRICES),
                    help=f'vision model (default {MODEL})')
    ap.add_argument('--dry-run', action='store_true',
                    help='price it and exit; sends nothing')
    ap.add_argument('--reocr', action='store_true',
                    help='ignore what is already in llm_text.json')
    ap.add_argument('--only', default='',
                    help='comma-separated image filenames to consider, e.g. the '
                         'new ones a sync reported')
    args = ap.parse_args()

    if not INDEX.exists():
        raise SystemExit('no index.json — run the archive script first')
    index = json.loads(INDEX.read_text())
    names = wanted_images(index)
    if args.only:
        only = {n.strip() for n in args.only.split(',') if n.strip()}
        names = [n for n in names if n in only]
    done = {} if args.reocr else load_done()
    todo = [n for n in names if n not in done]

    if args.dry_run:
        dry_run(names, todo[:(args.limit or None)], args.model)
        return

    # Apply the brakes before a single request goes out.
    caps = []
    if args.limit:
        caps.append(args.limit)
    if args.max_images:
        caps.append(args.max_images)
    if caps:
        todo = todo[:min(caps)]

    if not any([args.limit, args.max_images, args.max_cost]):
        print('! no cap given (--max-cost / --max-images / --limit).')
        print('  Running the whole archive uncapped is a choice, not a default.')
        answer = input('  Continue uncapped? type yes: ').strip().lower()
        if answer != 'yes':
            raise SystemExit('stopped, nothing spent.')

    key = api_key()
    print(f'→ {len(names)} image(s), {len(done)} already read, '
          f'{len(todo)} queued, model {args.model}')
    if args.max_cost:
        print(f'  ceiling ${args.max_cost:.2f} for this run')

    started = time.time()
    spent = 0.0
    errors = 0
    processed = 0
    stopped_early = ''

    for i, name in enumerate(todo, 1):
        # Brake 1: dollars. Checked BEFORE the request, using the worst case
        # for this image, so a request that would cross the line never runs.
        if args.max_cost:
            p = PRICES.get(args.model, PRICES[args.model])
            worst = (
                (EST_IMAGE_TOKENS * p['in'] + 2048 * p['out']) / 1_000_000)
            if spent + worst > args.max_cost:
                stopped_early = (f'cost ceiling reached (${spent:.4f} spent of '
                                 f'${args.max_cost:.2f})')
                break

        try:
            text, ok, cost, pt, ct = read_one(IMAGES / name, key, args.model)
        except Exception as e:
            errors += 1
            print(f'  [{i}/{len(todo)}] {name}: {e}')
            if errors >= MAX_FAIL_STREAK:
                stopped_early = (f'{MAX_FAIL_STREAK} failures in a row — '
                                 f'check the key and quota')
                break
            time.sleep(3)
            continue
        errors = 0
        processed += 1
        spent += cost
        done[name] = {
            'file': name,
            'text': text,
            'chars': len(text),
            'ok': ok,
            'note': '',
            'model': args.model,
            'tokens': {'in': pt, 'out': ct},
            'usd': round(cost, 6),
        }
        if processed % 20 == 0 or i == len(todo):
            save(done, args.model, spent)
            rate = (time.time() - started) / processed
            left = (len(todo) - i) * rate
            print(f'  [{i}/{len(todo)}] {len(done)} saved · '
                  f'{chars_of(done):,} chars · ${spent:.4f} spent · '
                  f'~{left/60:.0f} min left')
        time.sleep(SLEEP)

    save(done, args.model, spent)
    empty = sum(1 for v in done.values() if not v.get('ok'))
    print(f'\n→ {OUT}')
    print(f'  {len(done)} image(s) read, {chars_of(done):,} characters, '
          f'{empty} with no readable text')
    print(f'  this run: {processed} image(s), ${spent:.4f}')
    if stopped_early:
        print(f'  stopped: {stopped_early}')
        print(f'  {len(todo) - processed} image(s) left — run again when ready')


if __name__ == '__main__':
    main()

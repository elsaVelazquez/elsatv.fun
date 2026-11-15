#!/usr/bin/env python3
"""
ocr_llm.py — read the text in each image with a vision model, word for word.

    venv/bin/python scripts/lore/yt_posts_lore_scripts/ocr_llm.py                 # everything not done yet
    venv/bin/python scripts/lore/yt_posts_lore_scripts/ocr_llm.py --limit 5       # try 5 images first
    venv/bin/python scripts/lore/yt_posts_lore_scripts/ocr_llm.py --reocr --limit 5

Reads  lore/YTelsaTVposts/index.json            which images exist
       lore/YTelsaTVposts/images/<file>         the original (unstamped) image
Writes lore/YTelsaTVposts/llm_text.json

    {"generated_at": "...", "model": "...",
     "images": {"<file>": {"file": "...", "text": "...", "chars": 0, "ok": true}}}

WHY THIS SCRIPT EXISTS, AND WHY THE PROMPT IS SO RUDE
-----------------------------------------------------
The text burned into these images (captions drawn on top of photos, screenshots
of comments, DJ decks, receipts) is part of the lore. It is not a summary: it is
what the picture says, exactly as it says it. So the model is told, in as few
words as possible, to retype everything it can read and to invent nothing.
No intents, no interpretation, no "the image appears to be…", no tidy-up of
spelling, no translation. If it cannot read something it writes [illegible].

This runs as its own pass, on the ORIGINAL image (not the datestamped copy), so
the black date bar we stamped on top can never be mistaken for content.

The output is a separate dictionary — llm_text.json — so it sits next to
ocr.json (tesseract's first pass) and ocr_extra.json (the multi-pass reading)
without any of them overwriting another. build_day_index.py reads all three,
and build_posts_html.py shows them in that order under each image.

SETUP
-----
Needs a Gemini API key (the only provider wired up here) in .env:

    GEMINI_API_KEY=...

Free keys: https://aistudio.google.com/apikey
Model is picked at the top of the file. If your key cannot reach a model you
get a clear error and nothing is written — the run is resumable, so fixing the
key and running again picks up where it stopped.
"""
import argparse
import base64
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

MODEL = 'gemini-2.5-flash'
ENDPOINT = ('https://generativelanguage.googleapis.com/v1beta/models/'
            '{model}:generateContent?key={key}')

# The whole job. Short on purpose — a long prompt invites the model to be clever.
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
SLEEP = 0.7              # be polite to a free-tier quota


# --------------------------------------------------------------------------- #
def api_key():
    """.env first, then the environment. GEMINI_API_KEY only — API_KEY in this
    repo is a Google Cloud key that the Gemini API rejects."""
    key = os.environ.get('GEMINI_API_KEY', '')
    if not key and Path('.env').exists():
        for line in Path('.env').read_text().splitlines():
            line = line.strip()
            if line.startswith('GEMINI_API_KEY='):
                key = line.split('=', 1)[1].strip().strip('"').strip("'")
                break
    if not key:
        raise SystemExit(
            'no GEMINI_API_KEY — put one in .env\n'
            '  GEMINI_API_KEY=...      (free key: '
            'https://aistudio.google.com/apikey)')
    return key


def image_bytes(path):
    """Original image, shrunk to MAX_SIDE so one request stays small."""
    from PIL import Image
    import io

    img = Image.open(path)
    img = img.convert('RGB')
    if max(img.size) > MAX_SIDE:
        scale = MAX_SIDE / max(img.size)
        img = img.resize((int(img.width * scale), int(img.height * scale)),
                         Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=88)
    return buf.getvalue()


def read_one(path, key):
    """One image -> (text, ok). Raises on anything that is not a 200."""
    payload = {
        'contents': [{
            'parts': [
                {'text': PROMPT},
                {'inline_data': {
                    'mime_type': 'image/jpeg',
                    'data': base64.b64encode(image_bytes(path)).decode(),
                }},
            ],
        }],
        'generationConfig': {
            'temperature': 0,
            'maxOutputTokens': 2048,
        },
    }
    r = requests.post(ENDPOINT.format(model=MODEL, key=key),
                      json=payload, timeout=120)
    if r.status_code != 200:
        raise RuntimeError(f'HTTP {r.status_code}: {r.text[:300]}')
    data = r.json()
    cands = data.get('candidates') or []
    if not cands:
        reason = (data.get('promptFeedback') or {}).get('blockReason', '')
        return '', False, reason
    parts = (cands[0].get('content') or {}).get('parts') or []
    text = ''.join(p.get('text', '') for p in parts).strip()
    if text.upper() == 'NO TEXT':
        text = ''
    return text, bool(text), ''


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


def save(done, model):
    payload = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'model': model,
        'count': len(done),
        'images': dict(sorted(done.items())),
    }
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False))


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=0,
                    help='stop after N new images (0 = all of them)')
    ap.add_argument('--reocr', action='store_true',
                    help='ignore what is already in llm_text.json')
    args = ap.parse_args()

    if not INDEX.exists():
        raise SystemExit('no index.json — run the archive script first')
    key = api_key()
    index = json.loads(INDEX.read_text())
    names = wanted_images(index)
    done = {} if args.reocr else load_done()

    todo = [n for n in names if n not in done]
    if args.limit:
        todo = todo[:args.limit]
    print(f'→ {len(names)} image(s), {len(done)} already read, '
          f'{len(todo)} to go, model {MODEL}')

    started = time.time()
    errors = 0
    for i, name in enumerate(todo, 1):
        try:
            text, ok, why = read_one(IMAGES / name, key)
        except Exception as e:
            errors += 1
            print(f'  [{i}/{len(todo)}] {name}: {e}')
            if errors >= 5 and i == errors:
                print('  5 failures in a row — stopping. Nothing is lost; '
                      'fix the key/quota and run again.')
                break
            time.sleep(3)
            continue
        errors = 0
        done[name] = {
            'file': name,
            'text': text,
            'chars': len(text),
            'ok': ok,
            'note': why,
        }
        if i % 20 == 0 or i == len(todo):
            save(done, MODEL)
            rate = (time.time() - started) / i
            left = (len(todo) - i) * rate
            print(f'  [{i}/{len(todo)}] {len(done)} saved · '
                  f'{chars_of(done):,} chars · ~{left/60:.0f} min left')
        time.sleep(SLEEP)

    save(done, MODEL)
    empty = sum(1 for v in done.values() if not v.get('ok'))
    print(f'\n→ {OUT}')
    print(f'  {len(done)} image(s) read, {chars_of(done):,} characters, '
          f'{empty} with no readable text')


def chars_of(done):
    return sum(v.get('chars', 0) for v in done.values())


if __name__ == '__main__':
    main()

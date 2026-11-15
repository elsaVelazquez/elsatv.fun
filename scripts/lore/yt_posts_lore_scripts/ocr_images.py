#!/usr/bin/env python3
"""
ocr_images.py — read the text already visible inside each archived image.

    venv/bin/python scripts/lore/yt_posts_lore_scripts/ocr_images.py --limit 20      # try a sample
    venv/bin/python scripts/lore/yt_posts_lore_scripts/ocr_images.py                 # all of them

Runs tesseract locally: no API, no quota, no per-image cost. This is the
expensive-in-minutes step (~30 min for 1617 images) but it is CPU, not money,
and it can be interrupted — each image is written as it finishes.

Writes lore/YTelsaTVposts/ocr.json:

    {
      "generated_at": "…",
      "images": {
        "Ugkx…_1.jpg": {
          "file": "Ugkx…_1.jpg",
          "text": "Party Stream Kickoff!\nTONIGHT 1h30m before launch…",
          "lines": 7,
          "chars": 184,
          "ok": true
        }
      }
    }

Only the text is kept. The image itself is never modified here — stamping is a
separate script, so you can re-run either one alone.
"""
import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path('lore/YTelsaTVposts')
IMAGES = ROOT / 'images'
OUT = ROOT / 'ocr.json'

TESSERACT = 'tesseract'
LANG = 'eng'

# Tesseract is happier with '--psm 6' (one uniform block) on screenshots,
# which is what most of these are. Change here if output looks wrong.
PSM = '6'


# --------------------------------------------------------------------------- #
def list_images(images_dir=IMAGES):
    files = sorted(images_dir.glob('*.jpg'))
    return files


def ocr_one(path, timeout=120):
    """
    Text found in one image, or '' if none / if OCR failed.

    Kept deliberately small: it shells out to tesseract and returns a string,
    so you can swap in a different OCR engine without touching anything else.
    """
    try:
        with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as tmp:
            out_base = tmp.name[:-4]
        subprocess.run(
            [TESSERACT, str(path), out_base, '-l', LANG, '--psm', PSM],
            check=True, capture_output=True, timeout=timeout)
        txt_path = Path(out_base + '.txt')
        text = txt_path.read_text(
            errors='replace') if txt_path.exists() else ''
        txt_path.unlink(missing_ok=True)
        return clean_text(text)
    except subprocess.TimeoutExpired:
        print(f'    ⚠️  timed out: {path.name}')
        return ''
    except Exception as e:
        print(f'    ⚠️  {path.name}: {e}')
        return ''


def clean_text(text):
    """Drop the blank-line noise tesseract emits; keep line breaks inside a post."""
    lines = [ln.rstrip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln.strip()]
    return '\n'.join(lines)


def record(path, text):
    return {
        'file': path.name,
        'text': text,
        'lines': len(text.splitlines()) if text else 0,
        'chars': len(text),
        'ok': bool(text),
    }


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=0,
                    help='only the first N images (0 = all)')
    ap.add_argument('--images', default=str(IMAGES))
    ap.add_argument('--out', default=str(OUT))
    args = ap.parse_args()

    files = list_images(Path(args.images))
    if args.limit:
        files = files[:args.limit]
    print(f'→ {len(files)} image(s) to read')

    out_path = Path(args.out)
    found = {}
    if out_path.exists():
        try:
            found = json.loads(out_path.read_text()).get('images', {})
        except Exception:
            found = {}

    for i, path in enumerate(files, 1):
        rec = record(path, ocr_one(path))
        found[path.name] = rec
        flag = '✓' if rec['ok'] else '·'
        print(
            f'  [{i}/{len(files)}] {flag} {path.name[:42]:42} {rec["chars"]:5} chars')
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(
            {'generated_at': datetime.now().isoformat(timespec='seconds'),
             'engine': f'tesseract psm={PSM} lang={LANG}',
             'images': found}, indent=2, ensure_ascii=False))

    with_text = sum(1 for r in found.values() if r['ok'])
    print(f'\n→ {out_path}')
    print(f'  {len(found)} image(s), {with_text} with readable text')


if __name__ == '__main__':
    main()

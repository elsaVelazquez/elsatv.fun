#!/usr/bin/env python3
"""
ocr_multi.py — a second, harsher OCR reading of each image, so the archive keeps
what the first pass missed.

    venv/bin/python scripts/lore/yt_posts_lore_scripts/ocr_multi.py                  # every image
    venv/bin/python scripts/lore/yt_posts_lore_scripts/ocr_multi.py --limit 20       # just a sample
    venv/bin/python scripts/lore/yt_posts_lore_scripts/ocr_multi.py --reocr          # redo everything
    venv/bin/python scripts/lore/yt_posts_lore_scripts/ocr_multi.py --only a.jpg,b.jpg  # just these

Reads  lore/YTelsaTVposts/images/*.jpg
Writes lore/YTelsaTVposts/ocr_extra.json   (adds to what is already there)

Why: text drawn ON a photo (captions, usernames, stickers, burned-in subtitles)
is often light-on-dark, small, or on a busy background, and one tesseract pass
with one page-segmentation mode reads only part of it. This runs tesseract four
more ways — sparse text, light text on dark, dark text on light, and an upscaled
grayscale copy — and keeps every line those passes found that the first pass did
not already have. Nothing is interpreted, summarised or reworded: it is the same
characters, read again more stubbornly.

The result is filed per image and later merged, under the key "ocr_text", into
the same block as the first pass, with the extra lines appended. The two
readings are kept separate in this file so that a re-run never loses either.

Safe to interrupt and re-run: images already present are skipped, and the file
is rewritten every 25 images so a kill loses in-flight work only.
"""
import argparse
import json
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path('lore/YTelsaTVposts')
IMAGES = ROOT / 'images'
BASE_OCR = ROOT / 'ocr.json'
OUT = ROOT / 'ocr_extra.json'

TESSERACT = 'tesseract'
LANG = 'eng'

# A line is kept only if a decent share of its characters land in real words.
# This is a spelling test, not a judgement: it drops tesseract's guesses at
# texture and noise ("RFs", "Ay hy", "2 Se SH") and keeps every readable word.
WORD_MIN_RATIO = 0.62

# Extra readings. (name, pillow preprocessing, tesseract psm)
#   sparse = no layout assumptions, whole picture — floating captions
#   dark   = white letters on a dark photo, inverted first
#   big    = grayscale, upscaled — small text
PASSES = [
    ('sparse', lambda im: im, '11'),
    ('dark', lambda im: ImageOps.invert(im.convert('RGB')), '6'),
    ('big', lambda im: upscale_gray(im), '3'),
]

# Tiles: text that is added ON TOP of a screenshot (a caption, a note, a
# sticker) usually sits in one part of the frame, and a whole-image pass reads
# the busy screenshot behind it better than the caption. Reading each region on
# its own gives that caption a clean, unobstructed pass.
TILES = [
    ('top', 0.0, 0.0, 1.0, 0.40),
    ('middle', 0.0, 0.28, 1.0, 0.74),
    ('bottom', 0.0, 0.60, 1.0, 1.0),
    ('center', 0.15, 0.30, 0.85, 0.80),
]


def upscale_gray(im, factor=2, max_side=3200):
    """Grayscale at ~2x, but not past max_side — small text survives, memory does not blow."""
    im = im.convert('L')
    w, h = im.size
    scale = min(factor, max_side / max(w, h), 1.0 * factor)
    if scale <= 1:
        return im
    return im.resize((int(w * scale), int(h * scale)), Image.LANCZOS)


def crop(im, box):
    w, h = im.size
    x0, y0, x1, y1 = box
    return im.crop((int(w * x0), int(h * y0), int(w * x1), int(h * y1)))


def run_tesseract(path, image, psm, timeout=180):
    """One tesseract reading of a (possibly transformed) image, as a string."""
    tmp_img = tmp_txt = None
    try:
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            tmp_img = f.name
        image.save(tmp_img)
        with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as f:
            tmp_txt = f.name[:-4]
        subprocess.run(
            [TESSERACT, tmp_img, tmp_txt, '-l', LANG, '--psm', psm],
            check=True, capture_output=True, timeout=timeout)
        out = Path(tmp_txt + '.txt')
        return clean_text(out.read_text(errors='replace') if out.exists() else '')
    except subprocess.TimeoutExpired:
        return ''
    except Exception:
        return ''
    finally:
        for p in (tmp_img, tmp_txt and tmp_txt + '.txt'):
            if p:
                Path(p).unlink(missing_ok=True)


def clean_text(text):
    lines = [ln.strip() for ln in text.splitlines()]
    return '\n'.join(ln for ln in lines if ln)


def signature(line):
    """What counts as 'the same line' when de-duplicating two readings."""
    return re.sub(r'[^0-9a-z]+', '', line.lower())


def plausible(line):
    """True if most of the line is spelled in recognisable words.

    No meaning is inferred and nothing is rewritten — this only answers
    'does this look like language or like speckle?'.
    """
    words = re.findall(r"[A-Za-z']+", line)
    if not words:
        return False                       # digits only: timestamps, counters
    real = sum(len(w) for w in words if len(w) >= 3 or w.lower() in SHORT_WORDS)
    total = len(re.sub(r'[^A-Za-z]+', '', line)) or 1
    return real / total >= WORD_MIN_RATIO and sum(
        len(w) >= 3 for w in words) >= 2


SHORT_WORDS = {'a', 'an', 'i', 'is', 'it', 'me', 'my', 'no', 'of', 'on', 'or',
               'so', 'to', 'up', 'us', 'we', 'be', 'by', 'do', 'he', 'if', 'in',
               'am', 'as', 'at', 'go', 'ok', 'the', 'and', 'you', 'not', 'for'}


def new_lines(extra, known):
    """Lines in `extra` worth keeping: readable, and not already in `known`."""
    known_sigs = {signature(k) for k in known.splitlines() if k.strip()}
    blob = signature(known)
    out = []
    for line in extra.splitlines():
        sig = signature(line)
        if len(sig) < 4:              # stray punctuation/specks
            continue
        if not plausible(line):
            continue
        if sig in known_sigs or sig in blob:
            continue
        if any(signature(o) == sig for o in out):
            continue
        out.append(line)
    return out


# --------------------------------------------------------------------------- #
def extract(path):
    """Extra text for one image: all passes, de-duplicated against the first OCR pass."""
    first = ''
    base = BASE_PASS_TEXT.get(path.name) or ''
    try:
        with Image.open(path) as im:
            im.load()
            readings = []
            for name, prep, psm in PASSES:
                readings.append(run_tesseract(path, prep(im), psm))
            for _tname, x0, y0, x1, y1 in TILES:
                region = crop(im, (x0, y0, x1, y1))
                readings.append(run_tesseract(path, upscale_gray(region), '6'))
                readings.append(run_tesseract(
                    path, upscale_gray(ImageOps.invert(region.convert('RGB'))), '6'))
    except Exception as e:
        print(f'    ⚠️  {path.name}: {e}')
        return None
    first = base
    found = []
    for text in readings:
        if not text:
            continue
        keep = new_lines(text, first + '\n' + '\n'.join(found))
        found.extend(keep)
    return {
        'file': path.name,
        'base_text': first,
        'extra_text': '\n'.join(found),
        'base_chars': len(first),
        'extra_chars': len('\n'.join(found)),
        'passes': [p[0] for p in PASSES] + [t[0] for t in TILES],
    }


BASE_PASS_TEXT = {}


def load_base():
    global BASE_PASS_TEXT
    if BASE_OCR.exists():
        try:
            payload = json.loads(BASE_OCR.read_text())
            BASE_PASS_TEXT = {
                k: (v or {}).get('text', '')
                for k, v in (payload.get('images') or {}).items()
            }
        except Exception as e:
            print(f'  ⚠️  {BASE_OCR} unreadable: {e}')
    print(f'  first OCR pass known for {len(BASE_PASS_TEXT)} image(s)')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=0,
                    help='stop after N images (0 = all)')
    ap.add_argument('--reocr', action='store_true',
                    help='redo images already in ocr_extra.json')
    ap.add_argument('--only', default='',
                    help='comma-separated image filenames to consider, e.g. the '
                         'new ones a sync reported')
    args = ap.parse_args()

    load_base()
    files = sorted(IMAGES.glob('*.jpg'))
    if not files:
        raise SystemExit(f'no images in {IMAGES}')

    done = {}
    if OUT.exists():
        try:
            done = (json.loads(OUT.read_text()) or {}).get('images', {})
        except Exception:
            done = {}
    print(f'  {len(done)} image(s) already read extra-wise')

    if args.only:
        only = {n.strip() for n in args.only.split(',') if n.strip()}
        files = [p for p in files if p.name in only]

    todo = [p for p in files if args.reocr or p.name not in done]
    if args.limit:
        todo = todo[:args.limit]
    print(f'  reading {len(todo)} image(s) with {len(PASSES)} extra pass(es)')

    images = dict(done)
    for i, path in enumerate(todo, 1):
        rec = extract(path)
        if rec is not None:
            images[path.name] = rec
        extra = rec['extra_chars'] if rec else 0
        print(f'  [{i}/{len(todo)}] {path.name[:46]:<46} '
              f'+{extra} chars' + ('' if extra else '  (nothing new)'))
        if i % 25 == 0:
            write(images)

    write(images)
    gained = sum(1 for r in images.values() if r.get('extra_text'))
    print(f'\n→ {OUT}')
    print(
        f'  {len(images)} image(s) read; {gained} gained text the first pass missed')


def write(images):
    payload = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'engine': f'{TESSERACT} (multi-pass: ' + ', '.join(p[0] for p in PASSES) + ')',
        'count': len(images),
        'images': dict(sorted(images.items())),
    }
    tmp = OUT.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    tmp.replace(OUT)


if __name__ == '__main__':
    main()

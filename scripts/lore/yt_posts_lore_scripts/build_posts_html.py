#!/usr/bin/env python3
"""
build_posts_html.py — turn days.json into a self-contained, browsable page.

    venv/bin/python scripts/lore/yt_posts_lore_scripts/build_posts_html.py

Reads  lore/YTelsaTVposts/days.json
Writes lore/YTelsaTVposts/posts.html

The page is one static file: no framework, no build step, no server. Images are
referenced by relative path, so it also works opened straight from disk. That
matters because it has to survive being copied to a host, or printed to PDF.

Layout: one row per DAY, newest at the top. Each row has three columns —

    | post text          | images (in YouTube order)   | comments |
    |                    |  + the text found *in* each |          |
    |                    |  image, under it            |          |

Click any image to open it full size (a small vanilla lightbox). Images that
have a stamped copy in datestamped/ are shown stamped, since the date across the
top is the point of the exercise.

No external requests: fonts are system fonts, the zoom is ~40 lines of JS.
"""
import html
import json
from datetime import datetime
from pathlib import Path

ROOT = Path('lore/YTelsaTVposts')
DAYS = ROOT / 'days.json'
OUT = ROOT / 'posts.html'

# Relative to the html file, which lives in ROOT.
IMG_DIR = 'datestamped'
IMG_FALLBACK = 'images'


# --------------------------------------------------------------------------- #
def esc(text):
    """HTML-escape, and keep the line breaks a post actually had."""
    return html.escape(text or '').replace('\n', '<br>')


def image_path(img):
    """Stamped copy if we have one, original otherwise."""
    return img.get('stamped') or f"{IMG_FALLBACK}/{img.get('file', '')}"


def render_image(img, idx):
    """
    One image, plus the text found inside it.

    `loading="lazy"` is deliberately NOT used: these files have no width/height
    in the markup, so a lazy image in a tall page never enters the viewport,
    never loads, and collapses to a 2px sliver. Loading eagerly plus the CSS
    aspect-ratio keeps the layout stable without measuring anything.
    """
    src = image_path(img)

    # Order matters and is the user's: the LLM read comes first, then the first
    # tesseract pass, then the multi-pass reading. All three are verbatim.
    blocks = []
    llm = (img.get('llm_text') or '').strip()
    if llm:
        blocks.append(f'<div class="ocr llm">{esc(llm)}</div>')
    ocr = (img.get('ocr_text') or '').strip()
    if ocr:
        blocks.append(f'<div class="ocr">{esc(ocr)}</div>')
    extra = (img.get('ocr_extra') or '').strip()
    if extra:
        blocks.append(
            f'<div class="ocr pass2">{esc(extra)}</div>')
    text_html = ''.join(blocks)
    return f'''
        <figure class="shot">
          <a href="{html.escape(src)}" class="zoom" data-i="{idx}">
            <img src="{html.escape(src)}"
                 alt="{html.escape(img.get('file', ''))}">
          </a>
          {text_html}
        </figure>'''


def render_comments(comments):
    if not comments:
        return '<p class="none">—</p>'
    rows = []
    for c in comments:
        cls = 'reply' if c.get('is_reply') else 'comment'
        likes = (f'<span class="likes">♥ {esc(c["likes"])}</span>'
                 if c.get('likes') else '')
        rows.append(
            f'<div class="{cls}">'
            f'<div class="who">{esc(c.get("author", ""))}'
            f'<span class="when">{esc(c.get("published", ""))}</span></div>'
            f'<div class="what">{esc(c.get("text", ""))}</div>'
            f'{likes}</div>')
    return ''.join(rows)


def render_post(post):
    tags = ''.join(f'<span class="tag">{esc(t)}</span>'
                   for t in (post.get('hashtags') or []))
    imgs = ''.join(render_image(i, n)
                   for n, i in enumerate(post.get('images') or []))
    if not imgs:
        imgs = '<p class="none">no image</p>'
    likes = (f'<span class="likes">♥ {esc(post["likes"])}</span>'
             if post.get('likes') else '')
    return f'''
      <article class="post">
        <div class="col copy">
          <div class="stamp">{esc(post.get('published', ''))}</div>
          <p class="body">{esc(post.get('text', ''))}</p>
          <div class="tags">{tags}</div>
          <div class="meta">{likes}
            <a href="{html.escape(post.get('url', '#'))}" target="_blank"
               rel="noopener">on YouTube ↗</a></div>
        </div>
        <div class="col shots">{imgs}</div>
        <div class="col talk">{render_comments(post.get('comments'))}</div>
      </article>'''


def render_day(key, day):
    return f'''
    <section class="day" id="d-{key}">
      <h2><time datetime="{key}">{esc(day.get('display', key))}</time>
        <span class="count">{len(day.get('posts', []))} post(s)</span></h2>
      {''.join(render_post(p) for p in day.get('posts', []))}
    </section>'''


# --------------------------------------------------------------------------- #
CSS = '''
:root{--bg:#0a0c08;--panel:#141912;--line:#303a2d;--fg:#f5f6f0;--dim:#6f7d66;
--acc:#5ff2d0;--lime:#b8ff43}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif}
header{position:sticky;top:0;z-index:5;background:rgba(10,12,8,.96);
border-bottom:1px solid var(--line);padding:14px 20px;
display:flex;gap:18px;align-items:baseline;flex-wrap:wrap}
header h1{margin:0;font-size:1.15rem;color:var(--lime);letter-spacing:.02em}
header .stat{color:var(--dim);font-size:.85rem}
main{max-width:1500px;margin:0 auto;padding:22px 18px 80px}
.day{margin:0 0 34px}
.day h2{position:sticky;top:52px;z-index:4;margin:0 0 12px;padding:10px 12px;
background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--acc);
border-radius:6px;font-size:1rem;display:flex;justify-content:space-between;
align-items:baseline;gap:12px}
.day h2 .count{color:var(--dim);font-size:.8rem;font-weight:400}
.post{display:grid;grid-template-columns:minmax(260px,1.1fr) minmax(300px,1.5fr)
minmax(200px,.7fr);gap:16px;padding:16px;margin:0 0 14px;background:var(--panel);
border:1px solid var(--line);border-radius:10px}
.col{min-width:0}
.copy .stamp{color:var(--acc);font-size:.78rem;font-weight:700;
letter-spacing:.04em;text-transform:uppercase;margin-bottom:6px}
.copy .body{margin:0 0 10px;font-size:.95rem;word-break:break-word}
.tags{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px}
.tag{font-size:.72rem;color:var(--acc);border:1px solid rgba(95,242,208,.3);
border-radius:999px;padding:1px 8px}
.meta{display:flex;gap:14px;align-items:center;font-size:.78rem;color:var(--dim)}
.meta a{color:var(--acc);text-decoration:none}
.meta a:hover{text-decoration:underline}
.shots{display:flex;flex-wrap:wrap;gap:12px;align-items:flex-start}
.shot{margin:0;flex:1 1 190px;max-width:340px}
.shot img{width:100%;height:auto;aspect-ratio:4/3;object-fit:cover;display:block;
border-radius:6px;border:1px solid var(--line);cursor:zoom-in;
transition:transform .15s;background:#0d1109}
.shot a:hover img{transform:translateY(-2px)}
.ocr{margin-top:6px;padding:8px 9px;background:#080b07;border:1px solid #22301e;
border-radius:6px;font:12px/1.45 ui-monospace,Menlo,monospace;color:#a9b8a2;
max-height:9.5em;overflow:auto;white-space:pre-wrap}
.ocr:empty{display:none}
.ocr.llm{color:#e8f0de;border-color:#3f5a36;background:#0b120a}
.ocr.pass2{opacity:.75}
.talk{border-left:1px solid var(--line);padding-left:14px}
.comment,.reply{margin:0 0 10px;font-size:.84rem}
.reply{margin-left:14px;opacity:.85}
.comment .who,.reply .who{color:var(--acc);font-weight:600;font-size:.78rem}
.when{color:var(--dim);font-weight:400;margin-left:8px}
.what{color:#d7e0cf}
.likes{color:var(--dim);font-size:.74rem}
.none{color:var(--dim);font-size:.8rem;margin:0}
#zoom{position:fixed;inset:0;background:rgba(0,0,0,.94);display:none;
align-items:center;justify-content:center;z-index:50;cursor:zoom-out}
#zoom.on{display:flex}
#zoom img{max-width:96vw;max-height:94vh;border-radius:4px}
@media (max-width:1000px){
.post{grid-template-columns:1fr}
.talk{border-left:0;border-top:1px solid var(--line);padding-left:0;padding-top:10px}
}
'''

JS = '''
(function(){
  var z=document.getElementById('zoom');
  document.addEventListener('click',function(e){
    var a=e.target.closest('a.zoom');
    if(a){e.preventDefault();
      z.innerHTML='<img src="'+a.getAttribute('href')+'" alt="">';
      z.classList.add('on');return;}
    if(e.target.closest('#zoom')){z.classList.remove('on');z.innerHTML='';}
  });
  document.addEventListener('keydown',function(e){
    if(e.key==='Escape'){z.classList.remove('on');z.innerHTML='';}
  });
})();
'''


def build_page(payload):
    days = payload.get('days', {})
    body = ''.join(render_day(k, d) for k, d in days.items())
    stats = (f'{payload.get("day_count", 0)} days · '
             f'{payload.get("post_count", 0)} posts · '
             f'{datetime.now():%b %-d, %Y}')
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Community posts — archive</title>
<style>{CSS}</style>
</head>
<body>
<header>
  <h1>Community posts</h1>
  <span class="stat">{esc(stats)}</span>
  <span class="stat">newest first · times in Mountain Time</span>
</header>
<main>{body}</main>
<div id="zoom"></div>
<script>{JS}</script>
</body>
</html>
'''


# --------------------------------------------------------------------------- #
def main():
    if not DAYS.exists():
        raise SystemExit('no days.json — run scripts/lore/yt_posts_lore_scripts/build_day_index.py first')
    payload = json.loads(DAYS.read_text())
    page = build_page(payload)
    OUT.write_text(page, encoding='utf-8')
    print(f'→ {OUT}')
    print(f'  {payload.get("day_count", 0)} days, '
          f'{payload.get("post_count", 0)} posts, {len(page)/1024:.0f} KB')


if __name__ == '__main__':
    main()

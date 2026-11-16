#!/usr/bin/env python3
"""
build_posts_html.py — turn days.json into a self-contained, browsable page.

    venv/bin/python scripts/lore/yt_posts_lore_scripts/build_posts_html.py

Reads  lore/YTelsaTVposts/days.json
Writes lore/YTelsaTVposts/posts.html   (canonical, folder-relative copy)
       posts.html                      (same page at the repo root: the
                                        homepage link and the public URL)

The page is one static file: no framework, no build step, no server. Images are
referenced by relative path, so it also works opened straight from disk. That
matters because it has to survive being copied to a host, or printed to PDF.

Layout: one row per DAY, newest at the top. Each row has three columns —

    | post text          | images (in YouTube order)   | comments |
    |                    |  + the text found *in* each |          |
    |                    |  image, under it            |          |

Click any image to open it full size (a small vanilla lightbox).

THE DATE, TWO WAYS — both, on purpose
-------------------------------------
A datestamped copy (black bar, date across the top) is used whenever one exists,
because that date is the point of the exercise: the whole corpus is the record
of what was said and *when it was said*, before vs after the event.

But the hosted copy uses YouTube's own CDN, which serves the ORIGINAL picture —
the one without our bar. So the post date is also written into the markup, as a
small line of text under every image, linked to the post on YouTube. Same idea
as the title line on the homepage cards: a visible, clickable date that is part
of the page, not baked into a JPEG. That means it is there even if the image
never loads, it is selectable and searchable, and it survives being scaled.

No external requests: fonts are system fonts, the zoom is ~40 lines of JS.
"""
import argparse
import html
import json
from datetime import datetime
from pathlib import Path

ROOT = Path('lore/YTelsaTVposts')
DAYS = ROOT / 'days.json'
OUT = ROOT / 'posts.html'
# Mirror at the repo root — served as elsatv.fun/posts.html
ROOT_COPY = Path('posts.html')

# Where "back to the homepage" goes. The homepage is index.html at the repo root.
# The SAME page is written to two places, so the href is relative to the copy:
#   posts.html                      root  -> index.html        (elsatv.fun/)
#   lore/YTelsaTVposts/posts.html   deep  -> ../../index.html
# Rather than guess, the JS at the bottom resolves it at click time from the
# file's own path (see HOME_LINK_EXPR), and the markup below is only the
# no-JS default, which is correct for the copy that matters on the web.
HOME_HREF = 'index.html'
HOME_FROM_DEEP = '../../index.html'

# Relative to the html file, which lives in ROOT.
IMG_DIR = 'datestamped'
IMG_FALLBACK = 'images'

# Where the ORIGINAL YouTube image URL of each file is recorded (archive_posts.py
# writes it). Used to point <img> straight at YouTube's own CDN for the copy of
# the page that goes on the public site: nothing to host, nothing to upload, and
# the photos keep coming from the server that already had them.
INDEX = ROOT / 'index.json'

# YouTube's CDN accepts a size suffix on the same URL. =s800 is a long edge of
# 800px — half the page CTA's width in CSS pixels, i.e. retina-clean at the size
# the grid actually draws it, and roughly a tenth of the bytes of =s0.
CDN_SIZE = '=s800'

# The public page prefers YouTube's CDN (free, nothing to upload). But the CDN
# can drop a file — a post gets deleted, or YouTube reshuffles its URLs — and
# when it does the picture is gone for good, because we never uploaded a copy.
#
# So every <img> also carries data-fallback, its OWN file on Cloudflare R2, and
# a few lines of JS swap it in if the CDN copy fails. R2 is 10 GB free with no
# egress charges and no renewal price — see HOSTING.md.
#
# Leave this '' until the bucket is live: the page then behaves exactly as it
# did before, no fallback markup. Set it to the bucket's public base URL and
# re-run this script — nothing else changes.
#
#   FALLBACK_BASE = 'https://img.elsatv.fun'        # custom domain (preferred)
#   FALLBACK_BASE = 'https://pub-xxxx.r2.dev'       # free r2.dev endpoint
#
# Or pass it on the command line, which is easier than editing this file:
#
#   venv/bin/python .../build_posts_html.py --fallback-base https://pub-xxxx.r2.dev
#
# The bucket holds the WebP copies made by web_images.py, under web/
# (e.g. web/abc123_1.webp), so FALLBACK_DIR and FALLBACK_EXT below match that.
FALLBACK_BASE = ''
FALLBACK_DIR = 'web'
FALLBACK_EXT = '.webp'
# If the uploaded files sit directly in the bucket root instead of a web/
# prefix, pass --fallback-dir '' on the command line.
FALLBACK_SUBPREFIX = ''


# --------------------------------------------------------------------------- #
def esc(text):
    """HTML-escape, and keep the line breaks a post actually had."""
    return html.escape(text or '').replace('\n', '<br>')


def image_path(img):
    """Stamped copy if we have one, original otherwise."""
    return img.get('stamped') or f"{IMG_FALLBACK}/{img.get('file', '')}"


def cdn_path(url):
    """A yt3/yt4 ggpht URL at CDN_SIZE, or '' if it is not one.

    The stored URL ends in a size token like =s0; swapping it for =s800 asks
    YouTube for the same picture, smaller. The size token is the LAST component
    after the final '=', so this is a safe tail replacement.
    """
    if not url or 'ggpht.com' not in url:
        return ''
    head = url.rsplit('=', 1)[0] if '=' in url else url
    return head + CDN_SIZE


def fallback_path(img):
    """This file's URL on the R2 bucket, or '' when no bucket is configured.

    Only the stamped copy is uploaded — the one with the date bar — so the
    public page shows the date even in the picture, not just in the text line
    underneath it.
    """
    if not FALLBACK_BASE:
        return ''
    name = img.get('file', '')
    if not name:
        return ''
    # The bucket holds the WebP re-encode, not the original: same stem, new
    # suffix (web_images.py writes <stem>.webp for every file in datestamped/).
    stem = name.rsplit('.', 1)[0] if '.' in name else name
    parts = [FALLBACK_BASE.rstrip('/')]
    if FALLBACK_SUBPREFIX:
        parts.append(FALLBACK_SUBPREFIX.strip('/'))
    parts.append(stem + FALLBACK_EXT)
    return '/'.join(parts)


def render_image(img, idx, post=None):
    """
    One image, plus the text found inside it.

    `loading="lazy"` is deliberately NOT used: these files have no width/height
    in the markup, so a lazy image in a tall page never enters the viewport,
    never loads, and collapses to a 2px sliver. Loading eagerly plus the CSS
    aspect-ratio keeps the layout stable without measuring anything.
    """
    # CDN sentinel: 'youtube' in index.json means the URL is a real yt3.ggpht
    # URL. Anything else (a local path, the string 'webp', etc.) is not an
    # absolute URL, so it must never win over the local file.
    cdn = img.get('cdn') or ''
    src = cdn if cdn.startswith(('http://', 'https://')) else image_path(img)
    fallback = fallback_path(img)
    fallback_attr = (f'\n                 data-fallback="{html.escape(fallback)}"'
                     if fallback else '')

    # Order matters and is the user's: the LLM read comes first, then the first
    # tesseract pass, then the multi-pass reading. All three are verbatim.
    #
    # Each block carries a coloured badge naming the reader that produced it,
    # because the point is to show the different engines side by side: a vision
    # model sees what tesseract cannot (text burned over a busy photo) and
    # tesseract sees what a model paraphrases away. The label lives OUTSIDE the
    # text so the transcription itself stays untouched and copy-pasteable.
    def block(kind, label, text):
        return (f'<div class="ocr {kind}">'
                f'<span class="badge">{label}</span>'
                f'<span class="said">{esc(text)}</span></div>')

    blocks = []
    llm = (img.get('llm_text') or '').strip()
    if llm:
        blocks.append(block('llm', 'OpenAI · vision', llm))
    ocr = (img.get('ocr_text') or '').strip()
    if ocr:
        blocks.append(block('tess1', 'Tesseract · pass 1', ocr))
    extra = (img.get('ocr_extra') or '').strip()
    if extra:
        blocks.append(block('tess2', 'Tesseract · multi-pass', extra))
    text_html = ''.join(blocks)

    # The date, as text under the image. This is the point of the whole
    # exercise: what was said, and WHEN it was said. Keeping it in the markup
    # means it survives even when the photo itself is served without the black
    # date bar (the public page points at YouTube's copy of the picture, which
    # has no bar), it is searchable, and it is selectable for copy/paste.
    date_html = ''
    if post and post.get('published'):
        iso = post.get('published_iso', '')
        stamp = f'<time datetime="{html.escape(iso)}">{esc(post["published"])}</time>'
        if post.get('url'):
            stamp = (f'<a href="{html.escape(post["url"])}" target="_blank"'
                     f' rel="noopener">{stamp}</a>')
        date_html = f'<div class="shot-date">{stamp}</div>'

    return f'''
        <figure class="shot">
          <a href="{html.escape(src)}" class="zoom" data-i="{idx}">
            <img src="{html.escape(src)}"{fallback_attr}
                 alt="{html.escape(img.get('file', ''))}">
          </a>
          {date_html}
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
    imgs = ''.join(render_image(i, n, post)
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


def anchor_id(key):
    """The id a day is reachable at: d-YYYY-MM-DD.

    Already matches the homepage's links, so nothing there needs to change.
    """
    return f'd-{key}'


# How many of the newest days the sticky header offers as jump links.
JUMP_COUNT = 8


def render_jump(payload):
    """'Newest → oldest' shortcuts in the sticky header, plus one back
    to the homepage. Plain links: no JS needed, they work on any browser."""
    days = list(payload.get('days', {}).items())[:JUMP_COUNT]
    if not days:
        return ''
    first = days[0]
    links = ''.join(
        f'<a href="#{html.escape(anchor_id(k))}">{esc(d.get("display", k))}</a>'
        for k, d in days)
    last = list(payload.get('days', {}).items())
    oldest = ''
    if len(last) > JUMP_COUNT:
        ok, od = last[-1]
        oldest = (f'<a href="#{html.escape(anchor_id(ok))}"'
                  f' title="Jump to the oldest posts">oldest</a>')
    return (f'<div class="jump"><span>jump to</span>{links}{oldest}</div>')


def render_day(key, day):
    return f'''
    <section class="day" id="{html.escape(anchor_id(key))}">
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
display:flex;gap:18px;align-items:baseline;flex-wrap:wrap;
backdrop-filter:blur(6px);-webkit-backdrop-filter:blur(6px)}
header h1{margin:0;font-size:1.15rem;color:var(--lime);letter-spacing:.02em}
header .stat{color:var(--dim);font-size:.85rem}
header .src{color:var(--lime);font-size:.85rem}
header .src a{color:var(--lime);text-decoration:none;display:inline-flex;
align-items:center;gap:5px;border-bottom:1px solid rgba(184,255,67,.35)}
header .src a:hover{border-bottom-color:var(--lime)}
header .src svg{width:15px;height:15px;fill:#f00;flex:0 0 auto}
/* Way back: always visible, in the header, and fixed on screen while the
   reader is deep in the page. A real link, so it works with no JS, opens in
   this tab, and can be middle-clicked or copied like any other link. */
.nav{display:flex;gap:8px;align-items:center;margin-left:auto}
.nav a{display:inline-flex;align-items:center;gap:6px;font-size:.82rem;
color:var(--lime);text-decoration:none;border:1px solid rgba(184,255,67,.4);
border-radius:999px;padding:4px 11px;background:rgba(184,255,67,.06);
white-space:nowrap}
.nav a:hover{background:rgba(184,255,67,.14);border-color:var(--lime)}
.nav a svg{width:12px;height:12px;fill:currentColor}
/* Jump-to-day links, in the sticky header. Only used when the reader came
   from the homepage's <a href="posts.html#d-YYYY-MM-DD"> day links. */
header .jump{font-size:.8rem;color:var(--dim);display:flex;gap:8px;
  align-items:center;flex-wrap:wrap;flex:1 1 100%;margin-top:2px}
header .jump a{color:var(--acc);text-decoration:none;
  border-bottom:1px solid rgba(95,242,208,.35)}
header .jump a:hover{border-bottom-color:var(--acc)}
/* Anchor targets must not slide under the sticky header (58px tall on
   desktop, ~78px on a phone) when a #d-YYYY-MM-DD link is followed. */
.day{scroll-margin-top:96px}
main{max-width:1500px;margin:0 auto;padding:22px 18px 80px}
/* Floating round buttons, bottom right: up, down, home. */
#dock{position:fixed;right:16px;bottom:16px;z-index:30;display:flex;
flex-direction:column;gap:8px}
#dock a,#dock button{width:42px;height:42px;border-radius:50%;display:flex;
align-items:center;justify-content:center;cursor:pointer;
background:rgba(20,25,18,.92);border:1px solid var(--line);color:var(--lime);
-webkit-appearance:none;appearance:none;padding:0}
#dock a:hover,#dock button:hover{border-color:var(--lime);
background:rgba(184,255,67,.12)}
#dock svg{width:16px;height:16px;fill:currentColor}
#dock button[disabled]{opacity:.35;cursor:default}
@media (max-width:520px){
header{padding:10px 12px;gap:10px}
.nav a{padding:3px 9px;font-size:.76rem}
#dock{right:10px;bottom:10px}
#dock a,#dock button{width:38px;height:38px}
}
/* Phones: the sticky header is dense at ~78px, so a jump target clears 130px
   instead of sliding under it. */
@media (max-width:700px){.day{scroll-margin-top:130px}}
@media print{
header,#dock,#zoom,.jump{display:none!important}
.day h2{position:static}
body{background:#fff;color:#000}
}
.day{margin:0 0 34px}
.day h2{position:sticky;top:58px;z-index:4;margin:0 0 12px;padding:10px 12px;
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
.shot{margin:0;flex:1 1 190px;max-width:340px;min-height:120px}
/* The box is the MINIMUM: these photos are mostly portrait 9:16 screenshots, so
   a fixed 4:3 crop cut the top and bottom off every one of them (the date bar
   went with it). An unloaded or failed image keeps ~4:3 so lazy rows do not
   collapse to a sliver, and a loaded one simply grows to its real shape. */
.shot img{width:100%;height:auto;min-height:120px;object-fit:contain;display:block;
border-radius:6px;border:1px solid var(--line);cursor:zoom-in;
transition:transform .15s;background:#0d1109}
.shot a{display:block}
.shot a:hover img{transform:translateY(-2px)}
.shot-date{margin-top:5px;font-size:.8rem;color:var(--lime);
	letter-spacing:.02em}
.shot-date a{color:inherit;text-decoration:none;
	border-bottom:1px solid rgba(184,255,67,.35)}
.shot-date a:hover{border-bottom-color:var(--lime)}
.ocr{margin-top:6px;padding:8px 9px;background:#080b07;border:1px solid #22301e;
border-left:3px solid #22301e;border-radius:6px;
font:12px/1.45 ui-monospace,Menlo,monospace;color:#a9b8a2;
max-height:9.5em;overflow:auto;white-space:pre-wrap}
.ocr:empty{display:none}
.ocr .said{display:block}
/* one colour per reader — matches the legend in the sticky header */
.ocr.tess1{border-left-color:#8fa6c9}
.ocr.tess2{border-left-color:#c9a98f;opacity:.85}
.ocr.llm{color:#e8f0de;border-color:#3f5a36;border-left-color:#b8ff43;
background:#0b120a;max-height:14em}
.badge{display:inline-block;margin:0 0 4px;padding:1px 6px;border-radius:4px;
font:600 9.5px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif;
text-transform:uppercase;letter-spacing:.06em;color:#0a0c08;background:#8fa6c9;
vertical-align:middle}
.ocr.tess2 .badge{background:#c9a98f}
.ocr.llm .badge{background:#b8ff43}
.legend{display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center;
font-size:.72rem;color:var(--dim);margin-top:4px}
.legend .k{display:inline-block;width:9px;height:9px;border-radius:2px;
margin-right:5px;vertical-align:-1px;background:#8fa6c9}
.legend .k.t2{background:#c9a98f}
.legend .k.ll{background:#b8ff43}
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
footer.end{display:flex;gap:16px;flex-wrap:wrap;align-items:center;
justify-content:space-between;padding:34px 22px 90px;color:var(--dim);
font-size:.8rem;border-top:1px solid var(--line);margin-top:40px}
footer.end a{color:var(--acc);text-decoration:none;display:inline-flex;
align-items:center;gap:8px;font-weight:600}
footer.end a:hover{text-decoration:underline}
footer.end svg{width:16px;height:16px;fill:currentColor;flex:0 0 auto}
kbd{border:1px solid var(--line);border-bottom-width:2px;border-radius:4px;
padding:1px 5px;font:inherit;font-size:.72rem;color:var(--fg)}
@media (max-width:1000px){
.post{grid-template-columns:1fr}
.talk{border-left:0;border-top:1px solid var(--line);padding-left:0;padding-top:10px}
}
'''

JS = r'''
(function(){
  // If a picture fails to load from where it was first pointed, try its own
  // copy once. 'error' does not bubble, so this listens in the capture phase.
  document.addEventListener('error',function(e){
    var img=e.target;
    if(!img||img.tagName!=='IMG'||!img.dataset||!img.dataset.fallback)return;
    var alt=img.dataset.fallback;
    delete img.dataset.fallback;
    if(img.getAttribute('src')!==alt){img.setAttribute('src',alt);}
  },true);

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

  // Up / down. Both use the document element directly, because the page scrolls
  // on <html> in some browsers and on <body> in others. Smooth where supported.
  var top=document.getElementById('to-top'),
      bottom=document.getElementById('to-bottom'),
      prev=0;
  function scrollTo_(y){
    try{window.scrollTo({top:y,behavior:'smooth'});}
    catch(e){window.scrollTo(0,y);}
  }
  function y(){
    return window.pageYOffset||document.documentElement.scrollTop||
           document.body.scrollTop||0;
  }
  function maxY(){
    var d=document.documentElement,b=document.body;
    return Math.max(d.scrollHeight,b.scrollHeight)-
           (window.innerHeight||d.clientHeight);
  }
  // Keyboard: 'g' then 't' = top, 'g' then 'b' = bottom, 'g' then 'h' = home.
  // Two keys, so a single stray letter never throws the reader across a page
  // this long. Ignored while typing in a field (the day <select> is fine).
  var g=false;
  document.addEventListener('keydown',function(e){
    var t=e.target&&e.target.tagName;
    if(t==='INPUT'||t==='TEXTAREA'||t==='SELECT'){return;}
    if(e.metaKey||e.ctrlKey||e.altKey){return;}
    var k=(e.key||'').toLowerCase();
    if(g&&(k==='t'||k==='b'||k==='h')){g=false;e.preventDefault();
      if(k==='t'){scrollTo_(0);}
      else if(k==='b'){scrollTo_(maxY());}
      else{location.href=document.getElementById('to-home')
             .getAttribute('href')||'index.html';}
      return;}
    g=(k==='g');
  });
  if(top){top.addEventListener('click',function(){scrollTo_(0);});}
  if(bottom){bottom.addEventListener('click',function(){scrollTo_(maxY());});}

  // A #d-YYYY-MM-DD hash (the homepage's day links land here) needs the same
  // header offset; browsers honour scroll-margin-top, but only on a real
  // anchor jump, so re-apply it here for hash changes made in-page.
  function hashJump(){
    var h=location.hash;
    if(!h||h.length<2){return;}
    var el;
    try{el=document.querySelector(h);}catch(e){return;}
    if(!el){return;}
    var head=document.querySelector('header'),
        off=head?head.getBoundingClientRect().height:0;
    var y0=el.getBoundingClientRect().top+y()-off-10;
    scrollTo_(y0<0?0:y0);
  }
  window.addEventListener('hashchange',hashJump);
  window.addEventListener('load',hashJump);
  // The dock sits bottom-right; if the lightbox is open the dock would float on
  // top of the enlarged picture, so it steps aside until the lightbox closes.
  function dockUnderZoom(){
    var d=document.getElementById('dock'), z=document.getElementById('zoom');
    if(d&&z){d.style.visibility=z.classList.contains('on')?'hidden':'';}
  }
  document.addEventListener('click',dockUnderZoom);
  document.addEventListener('keydown',dockUnderZoom);

  function sync(){
    var cur=y(), bottomY=maxY(), goingDown=cur>prev;
    prev=cur;
    if(top){
      // Hide 'up' at the very top; it also doubles as a nudge toward 'down'.
      top.disabled = cur < 80;
    }
    if(bottom){
      bottom.disabled = cur >= bottomY - 80;
    }
    // On a phone the dock fades back while reading downward and returns when
    // scrolling up or at the top — same trick as a phone's scroll controls. The
    // HOME button never hides: leaving the page must always be one tap away.
    var hb=document.getElementById('to-home');
    if(hb){hb.style.opacity=(goingDown&&cur>400)&&window.innerWidth<520?'.35':'1';}
  }
  window.addEventListener('scroll',sync,{passive:true});
  window.addEventListener('resize',sync);
  sync();

  // --- back to the homepage, from either copy of this file ------------------
  // This page is written twice: /posts.html and /lore/YTelsaTVposts/posts.html.
  // A single relative href cannot be right for both, and an absolute '/index.html'
  // breaks when the file is opened straight from disk (file://). So work out the
  // depth from location.pathname: two folders down = the deep copy.
  // One rule works for https and for file://: if the two folders above this
  // file are lore/YTelsaTVposts, it is the deep copy, so the homepage is two
  // levels up. /posts.html at a site root gets 'index.html' beside it.
  var path=decodeURIComponent(location.pathname).replace(/\/+$/,''),
      inDeep=/\/lore\/YTelsaTVposts\/posts\.html$/i.test(path);
  var homeHref=inDeep?'../../index.html':'index.html';
  ['home-link','to-home'].forEach(function(id){
    var a=document.getElementById(id);
    if(a){a.setAttribute('href',homeHref);}
  });
  // Safety net: if the home link 404s (page copied to a host without an
  // index.html beside it), walk up so the reader is never stranded. This is a
  // plain GET of a tiny local file at click time, so it costs nothing on load.
  var homeA=document.getElementById('to-home');
  if(homeA){homeA.addEventListener('click',function(e){
    if(e.metaKey||e.ctrlKey||e.shiftKey||e.button)return;
    e.preventDefault();
    var dir=homeHref, tries=0, done=false;
    (function tryNext(){
      var x=new XMLHttpRequest();
      x.open('HEAD',dir,true);
      x.onload=function(){
        done=true;
        if(x.status>=200&&x.status<400){location.href=dir;}
        else if(++tries<4){dir='../'+dir;tryNext();}
        else{location.href=homeHref;}
      };
      x.onerror=function(){if(!done){location.href=homeHref;}};
      x.send();
    })();
  });}
})();
'''


def build_page(payload, remote_images=False):
    days = payload.get('days', {})
    # NOTE: the `cdn` key set in main() is intentionally NOT stripped here.
    # render_image() already prefers it only when it is an absolute URL, so the
    # local copy still shows datestamped/ files from disk (it opens with
    # file://, where a remote URL is useless) while the public copy — where
    # those relative paths cannot resolve on GitHub Pages — gets the CDN.
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
  <span class="src">Community posts on
    <a href="https://www.youtube.com/@elsaTVfun/posts" target="_blank"
       rel="noopener noreferrer">YT@elsaTVfun/posts<svg viewBox="0 0 24 24"
       aria-hidden="true"><path d="M23.5 6.2a3 3 0 0 0-2.1-2.1C19.5 3.6 12 3.6 12 3.6s-7.5 0-9.4.5A3 3 0 0 0 .5 6.2C0 8.1 0 12 0 12s0 3.9.5 5.8a3 3 0 0 0 2.1 2.1c1.9.5 9.4.5 9.4.5s7.5 0 9.4-.5a3 3 0 0 0 2.1-2.1C24 15.9 24 12 24 12s0-3.9-.5-5.8zM9.5 15.6V8.4l6.3 3.6-6.3 3.6z"/></svg></a>
  </span>
  <span class="stat">{esc(stats)}</span>
  <span class="stat">newest first · times in Mountain Time</span>
  <span class="legend" title="Which reader produced the text under each image">
    text under images read by
    <span><i class="k ll"></i>OpenAI vision</span>
    <span><i class="k"></i>Tesseract&nbsp;pass&nbsp;1</span>
    <span><i class="k t2"></i>Tesseract&nbsp;multi-pass</span>
  </span>
  <nav class="nav">
    <a href="{html.escape(HOME_HREF)}" id="home-link" title="Back to elsatv.fun">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3l9 8h-3v9h-5v-6H11v6H6v-9H3z"/></svg>
      &larr; back to elsatv.fun</a>
  </nav>
  {render_jump(payload)}
</header>
<main>{body}</main>
<footer class="end">
  <a href="{html.escape(HOME_HREF)}" id="end-home" title="Back to elsatv.fun">
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3l9 8h-3v9h-5v-6H11v6H6v-9H3z"/></svg>
    &larr; back to elsatv.fun homepage</a>
  <span>oldest post · press <kbd>g</kbd> then <kbd>t</kbd> for the top</span>
</footer>
<div id="zoom"></div>
<div id="dock">
  <button type="button" id="to-top" title="Back to top"
          aria-label="Back to top">
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4l8 8h-5v8H9v-8H4z"/></svg></button>
  <button type="button" id="to-bottom" title="Jump to the oldest posts"
          aria-label="Jump to the bottom">
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 20l-8-8h5V4h6v8h5z"/></svg></button>
  <a href="{html.escape(HOME_HREF)}" id="to-home" data-home="{html.escape(HOME_HREF)}"
     title="Back to elsatv.fun homepage"
     aria-label="Back to elsatv.fun homepage">
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3l9 8h-3v9h-5v-6H11v6H6v-9H3z"/></svg></a>
</div>
<script>{JS}</script>
</body>
</html>
'''


# --------------------------------------------------------------------------- #
def main():
    global FALLBACK_BASE, FALLBACK_SUBPREFIX
    parser = argparse.ArgumentParser(
        description='Render days.json into posts.html (twice: local + public).')
    parser.add_argument(
        '--fallback-base', default=FALLBACK_BASE, metavar='URL',
        help='Public base URL of the image backup bucket, e.g. '
             'https://pub-abc123.r2.dev or https://img.elsatv.fun. '
             'Empty = no fallback markup.')
    parser.add_argument(
        '--fallback-dir', default=FALLBACK_DIR, metavar='PREFIX',
        help="Object prefix inside the bucket ('datestamped' by default; "
             "pass '' when the files are at the bucket root).")
    args = parser.parse_args()
    FALLBACK_BASE = args.fallback_base.strip()
    FALLBACK_SUBPREFIX = args.fallback_dir if args.fallback_base else ''

    if not DAYS.exists():
        raise SystemExit('no days.json — run scripts/lore/yt_posts_lore_scripts/build_day_index.py first')
    payload = json.loads(DAYS.read_text())

    # Map file name -> original YouTube URL, so the public copy can hotlink it.
    index = json.loads(INDEX.read_text()) if INDEX.exists() else {}
    urls = {}
    for post in index.get('posts', []):
        for name, url in zip(post.get('image_files') or [],
                             post.get('image_urls') or []):
            if name and url:
                urls[name] = url
    for day in payload.get('days', {}).values():
        for post in day.get('posts', []):
            for img in post.get('images', []):
                img['cdn'] = cdn_path(urls.get(img.get('file'), ''))
    remote = sum(1 for day in payload.get('days', {}).values()
                 for post in day.get('posts', [])
                 for img in post.get('images', [])
                 if (img.get('cdn') or '').startswith(('http://', 'https://')))
    total = sum(1 for day in payload.get('days', {}).values()
                for post in day.get('posts', [])
                for img in post.get('images', []))

    # 1. Local copy, in ROOT, next to datestamped/ and images/ — opens from disk.
    page = build_page(payload, remote_images=False)
    OUT.write_text(page, encoding='utf-8')
    print(f'→ {OUT}  (local images)')

    # 2. Public copy at the repo root, served as elsatv.fun/posts.html. Its
    #    images come from YouTube's CDN, so there is nothing to upload and
    #    nothing for GitHub Pages to store. If an image has no recorded URL it
    #    falls back to the relative path, which simply will not resolve here.
    root_page = build_page(payload, remote_images=True)
    # Deliberately NO path rewriting. An earlier version prefixed every leftover
    # relative path with lore/YTelsaTVposts/ because that is where datestamped/
    # and images/ live on this machine — but that folder is gitignored, so on
    # GitHub Pages those URLs were guaranteed 404s pointing at a directory that
    # is never published. Left relative, the same few images fail the same way
    # (there is nothing at the repo root to serve them), but the markup no longer
    # lies about where a file is, and data-fallback takes over as soon as an
    # image host is configured.
    ROOT_COPY.write_text(root_page, encoding='utf-8')
    print(f'→ {ROOT_COPY}  ({remote}/{total} images from YouTube CDN, '
          f'{total - remote} with no URL)')
    if FALLBACK_BASE:
        print(f'  fallback: {FALLBACK_BASE.rstrip("/")}/'
              f'{"" if not FALLBACK_SUBPREFIX else FALLBACK_SUBPREFIX.strip("/") + "/"}'
              f'<file>  ({total} image(s))')
    else:
        print('  fallback: none (FALLBACK_BASE is empty — no data-fallback on images)')

    print(f'  {payload.get("day_count", 0)} days, '
          f'{payload.get("post_count", 0)} posts, {len(page)/1024:.0f} KB')


if __name__ == '__main__':
    main()

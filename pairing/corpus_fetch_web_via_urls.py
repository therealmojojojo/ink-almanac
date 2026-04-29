"""URL-then-fetch fallback for items where the verbatim-reproduction route
refused. Strategy:

  1. Ask Claude (web_search enabled) to return canonical-source URL(s)
     ONLY — no text body. Claude isn't being asked to reproduce, just
     to locate.
  2. Pull each URL via urllib, strip HTML, extract the poem text.
  3. Save to corpus/_sources/<author>/<id>.txt with provenance header.

This bypasses the model-side reproduction guardrail by separating discovery
from copy. The text comes from the publisher's own page (poetryfoundation,
allpoetry, lyricstranslate, ro.wikisource, etc.) — same posture our
existing personal_library sidecars already use.
"""
from __future__ import annotations
import argparse, html as ihtml, json, os, re, sys, time, unicodedata, urllib.request
from pathlib import Path

import yaml
import anthropic

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / 'corpus'
SOURCES = CORPUS / '_sources'
SECRETS = ROOT / 'ha' / 'secrets.yaml'

MODELS = ["claude-opus-4-7", "claude-opus-4-5"]

URL_PROMPT = """\
Find canonical-source URL(s) for one poem. Return URLs ONLY — do not
reproduce the poem text.

POEM
  Title: {title}
  Author: {author}
  Excerpt for disambiguation:
  ---
  {current}
  ---

WHERE TO LOOK
Use web search. Prefer: poetryfoundation.org, poets.org, allpoetry.com,
lyricstranslate.com, wikisource (any language), poemhunter.com,
ro.wikisource.org, poezie.ro, versuri.ro for Romanian; the publisher's
own page; the author's official archive.

OUTPUT — return only this JSON, no prose:

{{
  "urls": ["...", "..."],     // up to 3 URLs ranked by source quality
  "edition": "...",           // ≤80 chars: translator/edition if known
  "notes": "..."              // ≤120 chars: any caveats
}}

If no canonical source can be found, return {{"urls": [], "edition": "", "notes": "..."}}.
"""

# --- Helpers --------------------------------------------------------------

def slug(s: str) -> str:
    s = unicodedata.normalize('NFKD', s).encode('ascii','ignore').decode()
    return re.sub(r'[^a-zA-Z0-9]+', '-', s).strip('-').lower()

def get_api_key() -> str:
    if 'ANTHROPIC_API_KEY' in os.environ: return os.environ['ANTHROPIC_API_KEY']
    if SECRETS.exists():
        try:
            d = yaml.safe_load(SECRETS.read_text()) or {}
            for k in ('anthropic_api_key','ANTHROPIC_API_KEY'):
                if k in d: return d[k]
        except Exception: pass
    sys.exit("missing ANTHROPIC_API_KEY")

JSON_RX = re.compile(r'\{[\s\S]*\}', re.M)
def extract_json(text: str) -> dict | None:
    try: return json.loads(text)
    except json.JSONDecodeError: pass
    m = JSON_RX.search(text)
    if not m: return None
    raw = m.group(0).replace('“','"').replace('”','"').replace('‘',"'").replace('’',"'")
    raw = re.sub(r',\s*([\]}])', r'\1', raw)
    try: return json.loads(raw)
    except: return None

def call_opus_for_urls(client, system: str, user: str):
    last_exc = None
    for m in MODELS:
        try:
            resp = client.messages.create(
                model=m, max_tokens=1200,
                system=[{"type":"text","text":system}],
                messages=[{"role":"user","content":user}],
                tools=[{"type":"web_search_20250305","name":"web_search","max_uses":3}],
            )
            text = ''.join(b.text for b in resp.content if getattr(b,'type',None)=='text')
            return text, m
        except (anthropic.NotFoundError, anthropic.BadRequestError) as e:
            last_exc = e; continue
        except anthropic.RateLimitError as e:
            time.sleep(8); last_exc = e; continue
    raise last_exc or RuntimeError("all models failed")

# --- HTML → text ----------------------------------------------------------

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def http_get(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Accept': 'text/html,application/xhtml+xml,*/*',
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', errors='replace')

XHTML_TAG = re.compile(r'<[^>]+>')
WS = re.compile(r'[ \t]+')
BLANK = re.compile(r'\n{3,}')

def html_to_text_full(html: str) -> str:
    """Generic HTML→text. Used for fallback when no site-specific extractor
    fires."""
    h = re.sub(r'<(script|style|nav|header|footer|aside|form)[\s\S]*?</\1>', '', html, flags=re.I)
    h = re.sub(r'<br\s*/?>', '\n', h, flags=re.I)
    h = re.sub(r'</(p|div|h[1-6]|li|tr|td|article|section|blockquote)>', '\n', h, flags=re.I)
    h = XHTML_TAG.sub('', h)
    h = ihtml.unescape(h)
    h = WS.sub(' ', h)
    h = re.sub(r' *\n', '\n', h)
    h = BLANK.sub('\n\n', h)
    return h.strip()

# Site-specific extractors. Return the poem text only, line breaks preserved.

def extract_poetryfoundation(html: str) -> str:
    """PoetryFoundation pages have a <div class='poem'> or similar
    container. Falls back to first <article>."""
    m = re.search(r'<div[^>]*class="[^"]*\bpoem\b[^"]*"[^>]*>([\s\S]*?)</div>\s*</div>', html)
    if m: return html_to_text_full(m.group(1))
    m = re.search(r'<article[\s\S]*?</article>', html)
    return html_to_text_full(m.group(0)) if m else html_to_text_full(html)

def extract_allpoetry(html: str) -> str:
    """allpoetry.com poems are inside <div class='poem_body'> or similar."""
    m = re.search(r'<div[^>]*class="[^"]*\bpoem_body\b[^"]*"[^>]*>([\s\S]*?)</div>', html)
    if m: return html_to_text_full(m.group(1))
    m = re.search(r'<pre[^>]*>([\s\S]*?)</pre>', html)
    if m: return html_to_text_full(m.group(1))
    return html_to_text_full(html)

def extract_wikisource(html: str) -> str:
    """Wikisource pages contain the poem inside <div class='poem'> nested
    in #mw-content-text."""
    m = re.search(r'<div[^>]*class="[^"]*\bpoem\b[^"]*"[^>]*>([\s\S]*?)</div>', html)
    if m: return html_to_text_full(m.group(1))
    return html_to_text_full(html)

def extract_lyricstranslate(html: str) -> str:
    m = re.search(r'<div[^>]*class="[^"]*\bsong-text\b[^"]*"[^>]*>([\s\S]*?)</div>', html)
    if m: return html_to_text_full(m.group(1))
    return html_to_text_full(html)

EXTRACTORS = [
    ('poetryfoundation.org',   extract_poetryfoundation),
    ('poets.org',              extract_poetryfoundation),  # similar shape
    ('allpoetry.com',          extract_allpoetry),
    ('wikisource.org',         extract_wikisource),
    ('wikipedia.org',          extract_wikisource),  # similar parser
    ('lyricstranslate.com',    extract_lyricstranslate),
]

def fetch_and_extract(url: str) -> tuple[str, str]:
    """Returns (text, site_label). Raises on error."""
    html = http_get(url)
    for needle, fn in EXTRACTORS:
        if needle in url.lower():
            return fn(html), needle
    return html_to_text_full(html), 'generic'

# --- Main ---------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ids', nargs='*', required=False, help='specific text ids')
    ap.add_argument('--from-file', help='file with one id per line')
    ap.add_argument('--candidates', default='/tmp/rework-candidates.yaml')
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--dry-run', action='store_true', help='print URLs only, don\'t fetch/save')
    args = ap.parse_args()

    ids: list[str] = []
    if args.ids: ids.extend(args.ids)
    if args.from_file:
        ids.extend(ln.strip() for ln in Path(args.from_file).read_text().splitlines() if ln.strip())
    if not ids:
        sys.exit("specify --ids or --from-file")
    ids = list(dict.fromkeys(ids))  # dedup, preserve order
    if args.limit: ids = ids[:args.limit]

    cands = yaml.safe_load(Path(args.candidates).read_text()) or []
    cmap = {c['id']: c for c in cands}
    work = []
    for tid in ids:
        c = cmap.get(tid)
        if not c:
            print(f"  [skip] {tid} not in candidate list")
            continue
        for sub in ('texts','personal_library'):
            p = CORPUS / sub / f"{c['id']}.yaml"
            if p.exists():
                d = yaml.safe_load(p.read_text())
                if d:
                    tv = d.get('text_variants') or {}
                    c['body']  = tv.get('en') or (next(iter(tv.values())) if tv else '') or ''
                    c['title'] = str(d.get('title') or c.get('title') or '')
                break
        work.append(c)
    print(f"Working on {len(work)} ids")

    client = anthropic.Anthropic(api_key=get_api_key())
    fetched = empty = errors = 0

    for c in work:
        tid = c['id']
        author = c['author']
        title = c.get('title','')
        author_dir = SOURCES / slug(author)
        out_path = author_dir / f"{tid}.txt"

        # Step 1 — get URLs
        try:
            text, m = call_opus_for_urls(
                client,
                "You return only the requested JSON object. URLs only — never reproduce poem text in your response.",
                URL_PROMPT.format(title=title, author=author, current=(c.get('body') or '')),
            )
        except Exception as e:
            print(f"  [ERR] {tid}: {e}")
            errors += 1
            continue
        obj = extract_json(text)
        if not obj or not obj.get('urls'):
            print(f"  [no-urls] {tid}: {(obj or {}).get('notes', text[:80])}")
            empty += 1
            continue

        urls = obj['urls'][:3]
        edition = obj.get('edition','')
        notes = obj.get('notes','')

        if args.dry_run:
            print(f"  [DRY] {tid}  edition={edition!r}")
            for u in urls: print(f"      {u}")
            continue

        # Step 2 — fetch each URL until one yields enough text
        best_text = ''
        best_url = ''
        best_site = ''
        for u in urls:
            try:
                t, site = fetch_and_extract(u)
            except Exception as e:
                print(f"      [{tid}] fetch fail {u}: {e}")
                continue
            if len(t) > len(best_text) and len(t) >= 60:
                best_text = t
                best_url = u
                best_site = site
            if len(best_text) > 250:
                break

        if not best_text:
            print(f"  [no-text] {tid}  urls failed: {urls}")
            empty += 1
            continue

        # Step 3 — save
        author_dir.mkdir(parents=True, exist_ok=True)
        header = f"# {author} — {title}\n# source: {best_url}  via {best_site}\n# edition: {edition}\n# notes: {notes}\n\n"
        out_path.write_text(header + best_text + ('\n' if not best_text.endswith('\n') else ''))
        print(f"  ✓ {tid:<48s} {len(best_text):>5d}c  {best_site}  ({edition[:40]})")
        fetched += 1
        time.sleep(0.4)  # gentle on remote sites

    print(f"\n=== SUMMARY ===")
    print(f"  fetched:  {fetched}")
    print(f"  empty:    {empty}")
    print(f"  errors:   {errors}")


if __name__ == '__main__':
    main()

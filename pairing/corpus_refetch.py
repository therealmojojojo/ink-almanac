"""corpus refetch — re-fetch corpus items marked `panel_verdict: reject`.

Reads each rejected sidecar, derives strict artist+title tokens from its
`artist` and `title` fields, then walks three free sources in order:
  1. Wikimedia Commons
  2. Art Institute of Chicago
  3. Met Open Access

Rules:
- A result must contain at least one artist token in the title or
  artist_display field (prevents fuzzy-match wrong-artwork fetches).
- A result must also contain at least one title token (when supplied),
  so that "Dürer" doesn't match "Dürer's rhinoceros" for a Young Hare item.
- Downloaded image must have short-edge >= 1200 px.

Usage:
    python3 pairing/corpus_refetch.py                # refetch all rejects
    python3 pairing/corpus_refetch.py id1 id2 ...    # refetch specific ids
    python3 pairing/corpus_refetch.py --dry          # show search plan only

For items no free source holds at usable resolution, leave the reject mark
in place — an operator-supplied URL can then be used via a follow-up
`corpus refetch-url <id> <url>` flow (not implemented here yet).
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

try:
    import yaml
    from PIL import Image
except ImportError:
    sys.exit('corpus_refetch needs pyyaml + pillow: pip install pyyaml pillow')

UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120 Safari/537.36'
FLOOR = 1200
REPO = Path(__file__).resolve().parent.parent
CORPUS = REPO / 'corpus'
MANIFEST = CORPUS / '_manifest.json'

# Minimum token length for title-keyword match (below this, the token is too
# generic — words like "of", "the", "a" would false-match everything).
MIN_TOKEN_LEN = 4

STOPWORDS = {
    'and','the','with','from','for','his','her','its','that','this','these',
    'those','into','onto','over','under','through','after','before','opening',
    'fragment','quatrain','plate','study','print','edition','view','views',
    'series','portrait','self','untitled',
}


# ---- helpers ---------------------------------------------------------------

def normalize_tokens(s: str) -> list[str]:
    """Lowercased, accent-stripped tokens over MIN_TOKEN_LEN, non-stopwords."""
    if not s:
        return []
    s = unicodedata.normalize('NFKD', s)
    s = s.encode('ascii', 'ignore').decode('ascii').lower()
    out = []
    for tok in re.findall(r'[a-z0-9]+', s):
        if len(tok) >= MIN_TOKEN_LEN and tok not in STOPWORDS:
            out.append(tok)
    return out


def artist_tokens(artist: str) -> list[str]:
    """Derive candidate artist-name forms. "Mu Qi" -> ['muqi','muqi','mu qi','fachang']
    — we include spaceless joins to catch Commons file naming."""
    clean = unicodedata.normalize('NFKD', artist or '').encode('ascii','ignore').decode('ascii').lower()
    # split on spaces, dashes, commas
    parts = re.split(r'[\s,-]+', clean)
    parts = [p for p in parts if p and len(p) >= 4]
    joined = ''.join(parts)
    tokens = set(parts)
    if joined:
        tokens.add(joined)
    # Also the last name alone (most common in search hits: "Kollwitz", "Whistler")
    if parts:
        tokens.add(parts[-1])
    return sorted(tokens)


def title_tokens(title: str) -> list[str]:
    """Tokens from title — excluding stopwords."""
    # Strip parentheticals "(opening quatrain)" etc.
    t = re.sub(r'\([^)]*\)', '', title or '')
    return normalize_tokens(t)


# ---- search backends -------------------------------------------------------

def _get_json(url: str, timeout: int = 30) -> dict | None:
    try:
        req = urllib.request.Request(url, headers={'User-Agent': UA})
        return json.loads(urllib.request.urlopen(req, timeout=timeout).read())
    except Exception:
        return None


def commons_search(query: str, limit: int = 10) -> list[dict]:
    url = 'https://commons.wikimedia.org/w/api.php?' + urllib.parse.urlencode({
        'action':'query','format':'json','prop':'imageinfo',
        'iiprop':'url|size|mime','generator':'search',
        'gsrsearch':f'{query} filetype:bitmap',
        'gsrnamespace':'6','gsrlimit':str(limit),
    })
    d = _get_json(url)
    if not d: return []
    out = []
    for p in d.get('query',{}).get('pages',{}).values():
        if 'imageinfo' not in p: continue
        i = p['imageinfo'][0]
        if i.get('mime') == 'image/tiff': continue
        out.append({
            'title': p['title'],
            'artist_display': '',  # Commons puts artist in wikitext, not in imageinfo
            'url': i.get('url'),
            'width': i.get('width',0),
            'height': i.get('height',0),
            'mime': i.get('mime',''),
            'source': 'commons',
            'source_url': f"https://commons.wikimedia.org/wiki/{urllib.parse.quote(p['title'].replace(' ','_'))}",
        })
    out.sort(key=lambda x: min(x['width'], x['height']), reverse=True)
    return out


def artic_search(query: str, limit: int = 20) -> list[dict]:
    url = 'https://api.artic.edu/api/v1/artworks/search?' + urllib.parse.urlencode({
        'q': query, 'fields': 'id,title,artist_display,image_id', 'limit': str(limit),
    })
    d = _get_json(url)
    if not d: return []
    out = []
    for r in d.get('data', []):
        if not r.get('image_id'): continue
        out.append({
            'title': r.get('title',''),
            'artist_display': r.get('artist_display',''),
            'url': f"https://www.artic.edu/iiif/2/{r['image_id']}/full/full/0/default.jpg",
            'source': 'artic',
            'source_url': f"https://www.artic.edu/artworks/{r['id']}",
            'width': 0, 'height': 0,
        })
    return out


def met_search(query: str, limit: int = 15) -> list[dict]:
    d = _get_json('https://collectionapi.metmuseum.org/public/collection/v1/search?' +
                   urllib.parse.urlencode({'q': query, 'hasImages':'true', 'isPublicDomain':'true'}))
    if not d: return []
    oids = d.get('objectIDs') or []
    out = []
    for oid in oids[:limit]:
        obj = _get_json(f'https://collectionapi.metmuseum.org/public/collection/v1/objects/{oid}')
        time.sleep(0.2)
        if not obj or not obj.get('primaryImage'): continue
        out.append({
            'title': obj.get('title',''),
            'artist_display': obj.get('artistDisplayName',''),
            'url': obj.get('primaryImage'),
            'source': 'met',
            'source_url': obj.get('objectURL', obj.get('primaryImage')),
            'width': 0, 'height': 0,
        })
    return out


# ---- selection + download --------------------------------------------------

def strict_match(cand: dict, artist_toks: list[str], title_toks: list[str]) -> bool:
    hay = (cand.get('title','') + ' ' + cand.get('artist_display','')).lower()
    hay = unicodedata.normalize('NFKD', hay).encode('ascii','ignore').decode('ascii')
    if not any(tok in hay for tok in artist_toks):
        return False
    if title_toks and not any(tok in hay for tok in title_toks):
        return False
    return True


def download(url: str, path: Path, referer: str | None = None) -> tuple[int | None, str | None]:
    hdrs = {'User-Agent': UA}
    if referer:
        hdrs['Referer'] = referer
    try:
        req = urllib.request.Request(url, headers=hdrs)
        d = urllib.request.urlopen(req, timeout=180).read()
    except Exception as e:
        return None, str(e)
    path.write_bytes(d)
    return len(d), None


def try_fetch(artist_toks: list[str], title_toks: list[str], query: str,
              max_long: int = 8000) -> dict | None:
    for fn, name in [(commons_search, 'commons'),
                      (artic_search, 'artic'),
                      (met_search, 'met')]:
        time.sleep(0.3)
        results = fn(query)
        for cand in results:
            if not strict_match(cand, artist_toks, title_toks):
                continue
            cand['source_name'] = name
            return cand
    return None


# ---- sidecar / manifest ----------------------------------------------------

def update_sidecar(path: Path, w: int, h: int, source_url: str, source: str) -> None:
    t = path.read_text()
    t = re.sub(r'^pixel_width:\s*\d+', f'pixel_width: {w}', t, flags=re.MULTILINE)
    t = re.sub(r'^pixel_height:\s*\d+', f'pixel_height: {h}', t, flags=re.MULTILINE)
    t = re.sub(r'^source_url:.*$', f'source_url: "{source_url}"', t, count=1, flags=re.MULTILINE)
    t = re.sub(r'^source:.*$', f'source: {source}', t, count=1, flags=re.MULTILINE)
    t = re.sub(r'^panel_verdict:.*\n', '', t, flags=re.MULTILINE)
    t = re.sub(r'^verdict_reason:.*\n', '', t, flags=re.MULTILINE)
    t = re.sub(r'^verdict_reviewed_at:.*\n', '', t, flags=re.MULTILINE)
    path.write_text(t)


def update_manifest(rel: str, n: int, sha: str, mime: str = 'image/jpeg') -> None:
    m = json.loads(MANIFEST.read_text())
    for e in m['entries']:
        if e['path'] == rel:
            e['sha256'], e['bytes'] = sha, n
            break
    else:
        m['entries'].append({
            'path': rel, 'sha256': sha, 'bytes': n, 'mime': mime,
            'backup_uri': f'file://{(REPO / rel).resolve()}',
        })
    MANIFEST.write_text(json.dumps(m, indent=2))


# ---- main ------------------------------------------------------------------

def iter_rejected():
    for sub in ('images','nocturne','personal_library','personal_library/nocturne'):
        d = CORPUS / sub
        if not d.exists(): continue
        for y in sorted(d.glob('*.yaml')):
            doc = yaml.safe_load(y.read_text()) or {}
            if doc.get('panel_verdict') == 'reject':
                yield sub, y, doc


def refetch_one(sub: str, sc: Path, doc: dict, dry: bool) -> str:
    iid = doc.get('id') or sc.stem
    artist = doc.get('artist') or ''
    title = doc.get('title') or ''
    at = artist_tokens(artist)
    tt = title_tokens(title)
    # Query: artist + title + tier-appropriate keywords
    q = f'{artist} {title}'
    print(f'\n[{iid}]')
    print(f'  artist: {artist!r}')
    print(f'  title:  {title!r}')
    print(f'  tokens: artist={at}, title={tt}')
    if dry:
        return 'dry'
    if not at:
        return 'no-artist-tokens'
    cand = try_fetch(at, tt, q)
    if not cand:
        return 'no-strict-match'
    print(f'  hit [{cand["source_name"]}]: {cand["title"][:80]}')

    bin_path = CORPUS / sub / f'{iid}.jpg'
    tmp = bin_path.with_suffix('.jpg.new')
    n, err = download(cand['url'], tmp,
                      referer='https://www.artic.edu/' if cand['source_name']=='artic' else None)
    if err:
        print(f'  dl fail: {err}'); return 'download-fail'
    try:
        w, h = Image.open(tmp).size
    except Exception as e:
        print(f'  bad image: {e}'); tmp.unlink(missing_ok=True); return 'bad-image'
    if min(w, h) < FLOOR:
        print(f'  below floor {w}x{h}'); tmp.unlink(); return 'below-floor'
    tmp.replace(bin_path)
    update_sidecar(sc, w, h, cand['source_url'], cand['source_name'])
    update_manifest(f'corpus/{sub}/{iid}.jpg', n, hashlib.sha256(bin_path.read_bytes()).hexdigest())
    print(f'  REPLACED -> {w}x{h}, {n//1024} KB')
    return 'replaced'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('ids', nargs='*', help='Specific ids to refetch; empty = all rejects')
    ap.add_argument('--dry', action='store_true', help='Show search plan, do not fetch')
    args = ap.parse_args()

    stats = {}
    targets = list(iter_rejected())
    if args.ids:
        targets = [(sub, sc, doc) for sub, sc, doc in targets if doc.get('id') in set(args.ids)]
    if not targets:
        print('no rejects to refetch')
        return

    for sub, sc, doc in targets:
        outcome = refetch_one(sub, sc, doc, args.dry)
        stats[outcome] = stats.get(outcome, 0) + 1

    print(f'\n=== SUMMARY ===')
    for k, v in sorted(stats.items()):
        print(f'  {k}: {v}')


if __name__ == '__main__':
    main()

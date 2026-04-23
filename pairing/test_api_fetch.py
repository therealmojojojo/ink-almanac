"""test-bench for the API-first fetcher targeting the bw-graphic-arts canon.

Exercises three distinct primary sources on three pending works each:
  1. Met Open Access       — Dürer (engravings / woodcut / drawing)
  2. Art Institute Chicago — Redon (noirs / lithographs)
  3. Wikimedia Commons     — Daumier (Charivari lithographs)

Per work: strict artist + title token match, long-edge >= 1800, short-edge
>= 1200. Reports match URL, dimensions, file bytes. Does not write into the
corpus; all fetches land under /tmp/apifetch-test/.

Usage:  python3 pairing/test_api_fetch.py
"""
from __future__ import annotations
import json
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from PIL import Image
import io

UA = "inkplate-corpus-test/1.0 (kitchen fridge device; single operator)"
OUT = Path("/tmp/apifetch-test")
OUT.mkdir(exist_ok=True)

FLOOR_SHORT = 1200
PREF_LONG = 1800
MIN_TOKEN_LEN = 4
STOPWORDS = {
    "and","the","with","from","for","his","her","plate","series","study","view",
    "les","der","die","das","von","del","della","de",
}


# ───────── tokenisation ─────────

def norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


def tokens(s: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", norm(s))
            if len(t) >= MIN_TOKEN_LEN and t not in STOPWORDS]


def artist_tokens(name: str) -> list[str]:
    toks = set(tokens(name))
    parts = [p for p in re.split(r"\s+", norm(name)) if len(p) >= 4]
    if parts:
        toks.add(parts[-1])   # surname alone
    return sorted(toks)


def strict_match(artist: str, title: str, hay: str) -> bool:
    hay = norm(hay)
    if not any(a in hay for a in artist_tokens(artist)):
        return False
    ttoks = tokens(title)
    if ttoks and not any(t in hay for t in ttoks):
        return False
    return True


# ───────── HTTP ─────────

def get_json(url: str, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def fetch_bytes(url: str, timeout=120) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=timeout).read()


def measure(img_bytes: bytes):
    with Image.open(io.BytesIO(img_bytes)) as im:
        return im.size   # (w, h)


# ───────── source adapters ─────────

def met_search(q: str, limit=25):
    base = "https://collectionapi.metmuseum.org/public/collection/v1"
    res = get_json(f"{base}/search?" + urllib.parse.urlencode(
        {"q": q, "hasImages": "true", "isPublicDomain": "true"}))
    oids = (res.get("objectIDs") or [])[:limit]
    out = []
    for oid in oids:
        try:
            obj = get_json(f"{base}/objects/{oid}")
        except Exception:
            continue
        time.sleep(0.15)
        if not obj.get("primaryImage"):
            continue
        out.append({
            "title": obj.get("title", ""),
            "artist": obj.get("artistDisplayName", ""),
            "hay": f"{obj.get('title','')} {obj.get('artistDisplayName','')}",
            "url": obj.get("primaryImage"),
            "source": "met",
            "source_url": obj.get("objectURL", ""),
        })
    return out


def artic_search(q: str, limit=25):
    res = get_json("https://api.artic.edu/api/v1/artworks/search?" +
                   urllib.parse.urlencode(
                       {"q": q, "fields": "id,title,artist_display,image_id,classification_title",
                        "limit": str(limit)}))
    out = []
    for r in res.get("data", []):
        if not r.get("image_id"):
            continue
        out.append({
            "title": r.get("title", ""),
            "artist": r.get("artist_display", ""),
            "hay": f"{r.get('title','')} {r.get('artist_display','')}",
            # AIC IIIF returns 403 for requested sizes > max; /full/!2000,2000/
            # is IIIF v2 "fit within 2000×2000" syntax — always served.
            "url": f"https://www.artic.edu/iiif/2/{r['image_id']}/full/!2400,2400/0/default.jpg",
            "source": "artic",
            "source_url": f"https://www.artic.edu/artworks/{r['id']}",
        })
    return out


def commons_search(q: str, limit=25):
    res = get_json("https://commons.wikimedia.org/w/api.php?" +
                   urllib.parse.urlencode(
                       {"action": "query", "format": "json", "prop": "imageinfo",
                        "iiprop": "url|size|mime", "generator": "search",
                        "gsrsearch": f"{q} filetype:bitmap",
                        "gsrnamespace": "6", "gsrlimit": str(limit)}))
    out = []
    for p in res.get("query", {}).get("pages", {}).values():
        if "imageinfo" not in p:
            continue
        i = p["imageinfo"][0]
        if i.get("mime") == "image/tiff":
            continue
        out.append({
            "title": p["title"],
            "artist": "",
            "hay": p["title"],
            "url": i["url"],
            "source": "commons",
            "source_url": f"https://commons.wikimedia.org/wiki/{urllib.parse.quote(p['title'].replace(' ','_'))}",
            "_w": i.get("width", 0),
            "_h": i.get("height", 0),
        })
    # Rank: (1) prefer Rijks-sourced scans (RP-P-OB-*, RP-F-*, SK-A-* or
    # explicit "Rijksmuseum" in filename), (2) then by short-edge size.
    def rijks_rank(c):
        t = c["title"].lower()
        rijks = any(k in t for k in ("rp-p-ob", "rp-p-1", "rp-f-", "sk-a-",
                                      "rijksmuseum"))
        return (1 if rijks else 0, min(c["_w"], c["_h"]))
    out.sort(key=rijks_rank, reverse=True)
    return out


SOURCES = {"met": met_search, "artic": artic_search, "commons": commons_search}


# ───────── driver ─────────

@dataclass
class Target:
    work_id: str
    artist: str
    title: str
    query: str
    source: str   # primary source to exercise


def try_target(t: Target):
    print(f"\n── {t.work_id}  [{t.source}]")
    print(f"   query: {t.query!r}")
    search = SOURCES[t.source]
    try:
        cands = search(t.query)
    except Exception as e:
        print(f"   ERR search: {e}")
        return None
    print(f"   {len(cands)} candidates")
    for c in cands:
        if not strict_match(t.artist, t.title, c["hay"]):
            continue
        try:
            data = fetch_bytes(c["url"])
        except Exception as e:
            print(f"   skip (download error): {e}")
            continue
        try:
            w, h = measure(data)
        except Exception as e:
            print(f"   skip (not an image): {e}")
            continue
        short, long_ = min(w, h), max(w, h)
        if short < FLOOR_SHORT:
            print(f"   skip — {w}×{h} below floor {FLOOR_SHORT}")
            continue
        out = OUT / f"{t.work_id}.jpg"
        out.write_bytes(data)
        flag_pref = "✓" if long_ >= PREF_LONG else "⚠ below 1800 long-edge pref"
        print(f"   HIT — {w}×{h}  {len(data):,} bytes  {flag_pref}")
        print(f"        {c['source_url']}")
        print(f"        saved: {out}")
        return {"work_id": t.work_id, "w": w, "h": h, "bytes": len(data),
                "source": c["source"], "source_url": c["source_url"],
                "image_url": c["url"]}
    print("   NO MATCH")
    return None


TARGETS = [
    # Dürer via Met Open Access
    Target("durer-praying-hands", "Albrecht Dürer", "Praying Hands",
           "Durer Praying Hands", "met"),
    Target("durer-nemesis-great-fortune", "Albrecht Dürer", "Nemesis",
           "Durer Nemesis Great Fortune", "met"),
    Target("durer-apocalypse-whore-of-babylon", "Albrecht Dürer", "Whore of Babylon",
           "Durer Whore of Babylon", "met"),

    # Redon via AIC
    Target("redon-origins-germination", "Odilon Redon", "Germination",
           "Redon Origins Germination", "artic"),
    Target("redon-origins-gnome", "Odilon Redon", "vision",
           "Redon Origins vision", "artic"),
    Target("redon-hommage-a-goya-marsh-flower", "Odilon Redon", "Hommage Goya",
           "Redon Hommage Goya", "artic"),

    # Daumier via Wikimedia Commons
    Target("daumier-gargantua", "Honoré Daumier", "Gargantua",
           "Daumier Gargantua 1831", "commons"),
    Target("daumier-legislative-belly", "Honoré Daumier", "Ventre législatif",
           "Daumier Ventre Législatif", "commons"),
    Target("daumier-ratapoil", "Honoré Daumier", "Ratapoil",
           "Daumier Ratapoil", "commons"),
]


def main():
    results = []
    for t in TARGETS:
        r = try_target(t)
        if r:
            results.append(r)
        time.sleep(0.5)

    # Summary
    print("\n" + "=" * 60)
    print(f"SUMMARY — {len(results)}/{len(TARGETS)} hits")
    by_source = {}
    for r in results:
        by_source.setdefault(r["source"], []).append(r)
    for src, rs in by_source.items():
        print(f"\n  {src}: {len(rs)}")
        for r in rs:
            pref = "" if max(r["w"], r["h"]) >= PREF_LONG else "  ⚠below pref"
            print(f"    {r['work_id']:40s}  {r['w']}×{r['h']}  {r['bytes']:>10,}B{pref}")
    miss = [t.work_id for t in TARGETS
            if not any(r["work_id"] == t.work_id for r in results)]
    if miss:
        print(f"\n  MISS: {miss}")

    (OUT / "report.json").write_text(json.dumps(results, indent=2))
    print(f"\n  report: {OUT / 'report.json'}")


if __name__ == "__main__":
    main()

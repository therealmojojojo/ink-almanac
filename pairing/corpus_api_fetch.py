"""corpus-api-fetch — stage-2 museum-API fetcher for the bw-graphic-arts canon.

Reads `openspec/changes/add-bw-graphic-arts-canon/lists/works-*.yaml`, fetches
every `status: pending` item via the per-creator source chain documented in
`design.md`, writes sidecar + binary under the right tier folder, and appends
the manifest entry.

Routing (primary → fallback):
  Old Masters / Hopper / Lewis / Seurat / Picasso / Sesshū / Hakuin   met → commons
  19c print (Daumier, Redon, Whistler, Meryon, Blake)                 commons → met
  Doré / Lynd Ward                                                    internet_archive → commons
  Fin-de-siècle (Beardsley, Lautrec, Munch)                           met → commons
  Kollwitz / Dix / Kirchner                                           commons → met
  Schiele                                                             commons → met

Commons is searched with Rijks-preference ranking (boosts filenames containing
`RP-P-OB-*`, `RP-F-*`, `SK-A-*`, or `Rijksmuseum`) — this recovers Rijks-quality
scans without needing the classic API key.

Usage:
    python3 pairing/corpus_api_fetch.py                       # dry run
    python3 pairing/corpus_api_fetch.py --commit              # actually write
    python3 pairing/corpus_api_fetch.py --commit --lineage old-master-print
    python3 pairing/corpus_api_fetch.py --commit --creator albrecht-durer
"""
from __future__ import annotations
import argparse
import datetime
import hashlib
import io
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

import yaml
from PIL import Image

REPO = Path(__file__).resolve().parent.parent
CORPUS = REPO / "corpus"
MANIFEST = CORPUS / "_manifest.json"
LISTS_DIRS = [
    REPO / "openspec" / "changes" / "add-bw-graphic-arts-canon" / "lists",
    REPO / "openspec" / "changes" / "add-contemporary-pen-canon" / "lists",
]

UA = "inkplate-corpus/1.0 (kitchen fridge; one-operator household)"
FLOOR_SHORT = 1200
PREF_LONG = 1800
MIN_TOKEN_LEN = 4
COMMONS_THROTTLE = 12.0  # seconds between image downloads on commons (tight)
COMMONS_429_BACKOFF = 75.0
MET_THROTTLE = 0.4
MET_403_BACKOFF = 45.0

STOPWORDS = {
    "and","the","with","from","for","his","her","plate","series","study","view",
    "les","der","die","das","von","del","della","les","versus",
}

# Per-creator canonical citation (only personal_library needs it, but we fill
# all so the field is uniform).
CITATIONS = {
    "edvard-munch":         "Munch, *Edvard Munch: Complete Paintings*, Taschen, 2008",
    "kathe-kollwitz":       "Kollwitz, *Käthe Kollwitz: Prints and Drawings*, Dover, 1969",
    "otto-dix":             "Dix, *Otto Dix: Der Krieg*, Hatje Cantz, 2014",
    "ernst-ludwig-kirchner":"Kirchner, *Ernst Ludwig Kirchner: The Graphic Work*, Prestel, 1990",
    "edward-hopper":        "Hopper, *Edward Hopper: The Complete Prints*, Whitney Museum, 1988",
    "lynd-ward":            "Ward, *Storyteller Without Words: The Wood Engravings of Lynd Ward*, Abrams, 1974",
    "pablo-picasso":        "Picasso, *Picasso: The Complete Engraved Work*, Abrams, 1988",
    # Contemporary pen canon — manga
    "osamu-tezuka":         "Tezuka, *Astro Boy*, Dark Horse, 2002",
    "akira-toriyama":       "Toriyama, *Dragon Ball*, Viz Media, 2002",
    "hayao-miyazaki":       "Miyazaki, *Nausicaä of the Valley of the Wind*, Viz Media, 2012",
    "jiro-taniguchi":       "Taniguchi, *The Walking Man*, Fanfare / Ponent Mon, 2004",
    "taiyo-matsumoto":      "Matsumoto, *Tekkonkinkreet*, Viz Media, 2007",
    "naoki-urasawa":        "Urasawa, *Monster*, Viz Media, 2006",
    "fujiko-f-fujio":       "Fujiko F. Fujio, *Doraemon*, Shogakukan, 1974",
    # Western comic-strip / cartoon
    "bill-watterson":       "Watterson, *The Complete Calvin and Hobbes*, Andrews McMeel, 2005",
    "charles-schulz":       "Schulz, *The Complete Peanuts*, Fantagraphics, 2004",
    "gary-larson":          "Larson, *The Complete Far Side*, Andrews McMeel, 2003",
    "scott-adams":          "Adams, *Dilbert: Best of the Pointy-Haired Boss*, Andrews McMeel, 2018",
    "herge":                "Hergé, *The Adventures of Tintin*, Casterman, 1930",
    "quentin-blake":        "Blake, *Quentin Blake: In the Theatre of the Imagination*, Jonathan Cape, 2014",
    # Caricature + contemporary ink
    "al-hirschfeld":        "Hirschfeld, *The Hirschfeld Century*, Knopf, 2015",
    "ronald-searle":        "Searle, *St Trinian's: The Entire Appalling Business*, Overlook, 2008",
    "sempe":                "Sempé, *Sempé in America*, Denoël, 2013",
    "david-shrigley":       "Shrigley, *Anonymous Drawings*, David Shrigley studio, 2017",
    "ralph-steadman":       "Steadman, *The Joke's Over*, Harcourt, 2006",
    "art-spiegelman":       "Spiegelman, *Maus: A Survivor's Tale*, Pantheon, 1986",
}

# Routing table: lineage/creator → ordered source chain.
ROUTING = {
    "old-master-print":      ["met", "commons"],
    "american-20c-graphic":  ["met", "commons"],
    "modernist-drawing":     ["met", "commons"],
    "japanese-ink":          ["met", "commons"],
    "19c-print":             ["commons", "met"],
    "fin-de-siecle":         ["met", "commons"],
    "german-expressionist":  ["commons", "met"],
    # Contemporary pen canon (all in-copyright; commons-primary)
    "manga":                 ["commons"],
    "comic-strip":           ["commons"],
    "caricature":            ["commons"],
}
# creator-level override
ROUTING_CREATOR = {
    # Doré/Ward: IA book-reader lookup is complex; Commons has separate plate
    # scans at good resolution so route there.
    "gustave-dore":    ["commons", "met"],
    "lynd-ward":       ["commons", "internet_archive"],
    "egon-schiele":    ["commons", "met"],
    "pablo-picasso":   ["commons", "met"],  # Met PD-filter otherwise blocks
    "william-blake":   ["commons", "met"],
}

# Track last-hit times per source for throttling.
_last = {"commons": 0.0, "met": 0.0, "artic": 0.0, "cleveland": 0.0,
         "internet_archive": 0.0}


# ───────── tokenisation / strict match ─────────

def norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


def tokens(s: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", norm(s))
            if len(t) >= MIN_TOKEN_LEN and t not in STOPWORDS]


def artist_tokens(name: str) -> list[str]:
    toks = set(tokens(name))
    parts = [p for p in re.split(r"\s+", norm(name)) if len(p) >= 4]
    if parts:
        toks.add(parts[-1])
    return sorted(toks)


def strict_match(artist: str, title: str, hay: str, loose: bool = False) -> bool:
    hay_n = norm(hay)
    a_toks = artist_tokens(artist)
    if not any(a in hay_n for a in a_toks):
        return False
    if loose:
        return True
    t_toks = tokens(title)
    if t_toks and not any(t in hay_n for t in t_toks):
        return False
    return True


# ───────── HTTP ─────────

def get_json(url: str, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def fetch_bytes(url: str, timeout=180) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        return urllib.request.urlopen(req, timeout=timeout).read()
    except urllib.error.HTTPError as e:
        if e.code == 429:
            print(f"     429 — cooling {COMMONS_429_BACKOFF}s then retry once")
            time.sleep(COMMONS_429_BACKOFF)
            return urllib.request.urlopen(req, timeout=timeout).read()
        raise


def throttle(src: str):
    min_gap = {"commons": COMMONS_THROTTLE, "met": MET_THROTTLE,
               "artic": 0.4, "cleveland": 0.3, "internet_archive": 0.6}.get(src, 0.3)
    now = time.time()
    wait = min_gap - (now - _last[src])
    if wait > 0:
        time.sleep(wait)
    _last[src] = time.time()


# ───────── source adapters ─────────

def met_search(query: str, limit=25):
    """Search Met. Never passes isPublicDomain — rights are handled at
    sidecar time, not at fetch time."""
    throttle("met")
    base = "https://collectionapi.metmuseum.org/public/collection/v1"
    params = {"q": query, "hasImages": "true"}
    try:
        res = get_json(f"{base}/search?" + urllib.parse.urlencode(params))
    except urllib.error.HTTPError as e:
        if e.code == 403:
            print(f"     met 403 — cooling {MET_403_BACKOFF}s, retry once")
            time.sleep(MET_403_BACKOFF)
            res = get_json(f"{base}/search?" + urllib.parse.urlencode(params))
        else:
            raise
    oids = (res.get("objectIDs") or [])[:limit]
    out = []
    for oid in oids:
        throttle("met")
        try:
            obj = get_json(f"{base}/objects/{oid}")
        except Exception:
            continue
        if not obj.get("primaryImage"):
            continue
        out.append({
            "title": obj.get("title", ""),
            "artist": obj.get("artistDisplayName", ""),
            "hay": f"{obj.get('title','')} {obj.get('artistDisplayName','')}",
            "url": obj.get("primaryImage"),
            "source": "met_open_access",
            "source_url": obj.get("objectURL", ""),
            "medium": obj.get("medium", ""),
        })
    return out


def commons_search(query: str, limit=25):
    throttle("commons")
    res = get_json("https://commons.wikimedia.org/w/api.php?" +
                   urllib.parse.urlencode(
                       {"action": "query", "format": "json", "prop": "imageinfo",
                        "iiprop": "url|size|mime", "generator": "search",
                        "gsrsearch": f"{query} filetype:bitmap",
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
            "source": "wikimedia_commons",
            "source_url": f"https://commons.wikimedia.org/wiki/{urllib.parse.quote(p['title'].replace(' ','_'))}",
            "_w": i.get("width", 0),
            "_h": i.get("height", 0),
            "medium": "",
        })
    def rijks_rank(c):
        t = c["title"].lower()
        rijks = any(k in t for k in ("rp-p-ob", "rp-p-1", "rp-f-", "sk-a-",
                                      "rijksmuseum"))
        return (1 if rijks else 0, min(c["_w"], c["_h"]))
    out.sort(key=rijks_rank, reverse=True)
    return out


def internet_archive_search(query: str, limit=10):
    """For Doré / Lynd Ward book scans, search IA for the book itself."""
    throttle("internet_archive")
    try:
        url = "https://archive.org/advancedsearch.php?" + urllib.parse.urlencode(
            {"q": query, "fl[]": "identifier", "fl[]": "title",
             "rows": str(limit), "output": "json"})
        res = get_json(url)
    except Exception:
        return []
    out = []
    for r in res.get("response", {}).get("docs", []):
        ident = r.get("identifier")
        if not ident:
            continue
        # IA doesn't give per-page images directly here; placeholder for manual
        # follow-up. For now emit a link-only stub.
        out.append({
            "title": r.get("title", ""),
            "artist": "",
            "hay": r.get("title", ""),
            "url": "",   # must be resolved per-page via IA book-reader API
            "source": "internet_archive",
            "source_url": f"https://archive.org/details/{ident}",
            "medium": "",
            "_ia_identifier": ident,
        })
    return out


SOURCES = {
    "met": met_search,
    "commons": commons_search,
    "internet_archive": internet_archive_search,
}


# ───────── image inspection ─────────

def measure(data: bytes):
    with Image.open(io.BytesIO(data)) as im:
        return im.size, (im.format or "JPEG").lower()


# ───────── sidecar authoring ─────────

def sidecar_for(work: dict, creator_id: str, creator_name: str, default_rights: str,
                img_bytes: bytes, cand: dict, pix_w: int, pix_h: int) -> str:
    """Render YAML sidecar text per corpus-schema."""
    rights = work.get("rights_tier", default_rights)
    year = work.get("year")
    form = work.get("form", "drawing")
    medium = cand.get("medium") or form
    title = work.get("title") or work["id"].replace(creator_id + "-", "").replace("-", " ").title()
    def _q(s: str) -> str:
        # Quote string for YAML scalar — escape double-quote and backslash.
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    lines = [
        f"id: {work['id']}",
        f"title: {_q(title)}",
        f"artist: {_q(creator_name)}",
        f"year: {year if year is not None else 'null'}",
        f"rights_tier: {rights}",
        f"source: {cand['source']}",
        f"source_url: {cand['source_url'] or 'null'}",
    ]
    if rights == "personal_library":
        cit = CITATIONS.get(creator_id, f"{creator_name}, *Canonical reproduction*, publisher, year")
        lines.append(f"citation: {_q(cit)}")
    lines += [
        f"medium: {medium}",
        f"pixel_width: {pix_w}",
        f"pixel_height: {pix_h}",
        f"panel_fidelity: native",
        f"form: {form}",
        f"themes:",
        *[f"- {t}" for t in work.get("themes", [])],
        f"mood:",
        *[f"- {m}" for m in work.get("mood", [])],
        f"register:",
        *[f"- {r}" for r in work.get("register", [])],
        f"added: '{datetime.date.today().isoformat()}'",
    ]
    return "\n".join(lines) + "\n"


# ───────── manifest ─────────

def append_manifest(rel_path: str, data: bytes, mime: str):
    m = json.loads(MANIFEST.read_text())
    sha = hashlib.sha256(data).hexdigest()
    # Remove any prior entry with same path (idempotent re-run)
    m["entries"] = [e for e in m["entries"] if e["path"] != rel_path]
    m["entries"].append({
        "path": rel_path,
        "sha256": sha,
        "bytes": len(data),
        "mime": f"image/{'png' if mime == 'png' else 'jpeg'}",
        "backup_uri": f"file://{(REPO / rel_path)}",
    })
    MANIFEST.write_text(json.dumps(m, indent=2) + "\n")


# ───────── driver ─────────

def route_for(lineage: str, creator_id: str) -> list[str]:
    return ROUTING_CREATOR.get(creator_id, ROUTING.get(lineage, ["commons", "met"]))


def fetch_work(work: dict, creator_id: str, creator_name: str, lineage: str,
               default_rights: str, commit: bool, loose: bool = False) -> dict:
    qtitle = work.get("title") or work["id"].replace(creator_id + "-", "").replace("-", " ")
    artist_display = creator_name
    query = f"{artist_display} {qtitle}"
    chain = route_for(lineage, creator_id)
    tier = work.get("rights_tier", default_rights)
    for src in chain:
        search = SOURCES.get(src)
        if search is None:
            continue
        try:
            cands = search(query)
        except Exception as e:
            print(f"     {src}: search error: {e}")
            continue
        for c in cands:
            if not strict_match(artist_display, qtitle, c["hay"], loose=loose):
                continue
            if not c.get("url"):
                continue
            try:
                data = fetch_bytes(c["url"])
            except Exception as e:
                print(f"     {src}: dl error ({str(e)[:60]})")
                continue
            try:
                (w, h), fmt = measure(data)
            except Exception as e:
                print(f"     {src}: not an image ({e})")
                continue
            short, long_ = min(w, h), max(w, h)
            if short < FLOOR_SHORT:
                continue
            tier = work.get("rights_tier", default_rights)
            folder = "corpus/personal_library" if tier == "personal_library" else "corpus/images"
            ext = "png" if fmt == "png" else "jpg"
            rel_img = f"{folder}/{work['id']}.{ext}"
            rel_yml = f"{folder}/{work['id']}.yaml"
            pref_ok = long_ >= PREF_LONG
            status = "ok" if pref_ok else "below-pref"
            print(f"     ✓ {src} · {w}×{h} · {len(data):,}B {('' if pref_ok else '⚠below 1800pref')}")
            if commit:
                yaml_text = sidecar_for(work, creator_id, creator_name, default_rights,
                                         data, c, w, h)
                (REPO / rel_img).write_bytes(data)
                (REPO / rel_yml).write_text(yaml_text)
                append_manifest(rel_img, data, fmt)
            return {"work_id": work["id"], "status": status, "source": c["source"],
                    "source_url": c["source_url"], "w": w, "h": h, "bytes": len(data)}
        else:
            print(f"     {src}: no strict match in {len(cands)} candidates")
    return {"work_id": work["id"], "status": "miss"}


def run(commit: bool, filter_lineage: str | None, filter_creator: str | None,
        loose: bool = False):
    results = []
    files = []
    for d in LISTS_DIRS:
        if d.exists():
            files += sorted(d.glob("works-*.yaml"))
    for path in files:
        # skip the xkcd list — fetched by its own dedicated script
        if path.name == "works-xkcd.yaml":
            continue
        doc = yaml.safe_load(path.read_text())
        lineage = doc.get("lineage", "")
        if filter_lineage and lineage != filter_lineage:
            continue
        print(f"\n══ lineage: {lineage}  [{path.name}]")
        for creator_id, cr in doc.get("creators", {}).items():
            if filter_creator and creator_id != filter_creator:
                continue
            creator_name = cr.get("name", "")
            # recover display name from top-28 shortlist if not on the works file
            if not creator_name:
                # look up creator display name in either top-*.yaml shortlist
                for shortlist in ("top-bw-graphic-arts.yaml", "top-contemporary-pen.yaml"):
                    for d in LISTS_DIRS:
                        sp = d / shortlist
                        if sp.exists():
                            sd = yaml.safe_load(sp.read_text())
                            hit = next((it["name"] for it in (sd.get("items") or [])
                                        if it.get("id") == creator_id), None)
                            if hit:
                                creator_name = hit
                                break
                    if creator_name:
                        break
                if not creator_name:
                    creator_name = creator_id
            default_rights = (cr.get("defaults") or {}).get(
                "rights_tier",
                doc.get("defaults", {}).get("rights_tier", "public_domain"))
            # Skip works already on disk (idempotent re-run)
            default_rights_here = default_rights
            def _already_have(w):
                if not isinstance(w, dict) or "id" not in w:
                    return False
                tier = w.get("rights_tier", default_rights_here)
                folder = "corpus/personal_library" if tier == "personal_library" else "corpus/images"
                return (REPO / folder / f"{w['id']}.yaml").exists()
            pending = [w for w in cr.get("works", [])
                       if not (isinstance(w, dict) and w.get("in_corpus"))
                       and (isinstance(w, dict) and w.get("status") != "done")
                       and not _already_have(w)]
            if not pending:
                continue
            print(f"\n── {creator_id}  ({creator_name})  [{len(pending)} pending, tier={default_rights}]")
            for w in pending:
                if not isinstance(w, dict) or "id" not in w:
                    continue
                print(f"  • {w['id']}  — {w.get('title','')[:55]}")
                r = fetch_work(w, creator_id, creator_name, lineage,
                                default_rights, commit, loose=loose)
                results.append(r)
    # summary
    print("\n" + "=" * 60)
    hits = [r for r in results if r["status"] in ("ok", "below-pref")]
    miss = [r for r in results if r["status"] == "miss"]
    print(f"SUMMARY  attempted={len(results)}  hits={len(hits)}  misses={len(miss)}")
    by_src = {}
    for r in hits:
        by_src.setdefault(r.get("source", "?"), []).append(r)
    for s, rs in by_src.items():
        print(f"  {s}: {len(rs)}")
    if miss:
        print("\n  MISSES:")
        for r in miss:
            print(f"    {r['work_id']}")
    rpt = REPO / "corpus" / "_staging" / f"bw-graphic-arts-fetch-{datetime.datetime.now():%Y%m%d-%H%M%S}.json"
    rpt.parent.mkdir(exist_ok=True)
    rpt.write_text(json.dumps(results, indent=2))
    print(f"\n  report: {rpt}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--lineage", default=None)
    ap.add_argument("--creator", default=None)
    ap.add_argument("--loose", action="store_true",
                    help="skip title-token match; keep artist filter — catches foreign-language titles")
    args = ap.parse_args()
    run(args.commit, args.lineage, args.creator, loose=args.loose)


if __name__ == "__main__":
    main()

"""Generate a browseable HTML contact sheet for the bw-graphic-arts canon.

Renders every sidecar under corpus/images/ and corpus/personal_library/ whose
id matches one of the 25 graphic-arts creator prefixes. Each card shows a
thumbnail (from the local binary), id, artist, title, form, resolution, source,
and a click-through to the full-resolution local file.

Usage:
    python3 pairing/contact_sheet.py > corpus/_staging/bw-graphic-arts-contact-sheet.html
    open corpus/_staging/bw-graphic-arts-contact-sheet.html
"""
from __future__ import annotations
import html
import hashlib
from pathlib import Path

import yaml
from PIL import Image

REPO = Path(__file__).resolve().parent.parent
CORPUS = REPO / "corpus"
THUMBS = REPO / "corpus" / "_staging" / "contact-sheet-thumbs"
THUMB_MAX = 480

CREATORS = [
    ("durer",      "Albrecht Dürer",             "old-master-print"),
    ("rembrandt",  "Rembrandt van Rijn",         "old-master-print"),
    ("callot",     "Jacques Callot",             "old-master-print"),
    ("piranesi",   "Giovanni Battista Piranesi", "old-master-print"),
    ("goya",       "Francisco Goya",             "old-master-print"),
    ("blake",      "William Blake",              "19c-print"),
    ("daumier",    "Honoré Daumier",             "19c-print"),
    ("dore",       "Gustave Doré",               "19c-print"),
    ("meryon",     "Charles Meryon",             "19c-print"),
    ("redon",      "Odilon Redon",               "19c-print"),
    ("whistler",   "James McNeill Whistler",     "19c-print"),
    ("beardsley",  "Aubrey Beardsley",           "fin-de-siecle"),
    ("lautrec",    "Henri de Toulouse-Lautrec",  "fin-de-siecle"),
    ("munch",      "Edvard Munch",               "fin-de-siecle"),
    ("kollwitz",   "Käthe Kollwitz",             "german-expressionist"),
    ("dix",        "Otto Dix",                   "german-expressionist"),
    ("kirchner",   "Ernst Ludwig Kirchner",      "german-expressionist"),
    ("hopper",     "Edward Hopper",              "american-20c-graphic"),
    ("lewis",      "Martin Lewis",               "american-20c-graphic"),
    ("ward",       "Lynd Ward",                  "american-20c-graphic"),
    ("seurat",     "Georges Seurat",             "modernist-drawing"),
    ("schiele",    "Egon Schiele",               "modernist-drawing"),
    ("picasso",    "Pablo Picasso",              "modernist-drawing"),
    ("sesshu",     "Sesshū Tōyō",                "japanese-ink"),
    ("hakuin",     "Hakuin Ekaku",               "japanese-ink"),
    # Contemporary pen canon — manga
    ("tezuka",     "Osamu Tezuka",               "manga"),
    ("toriyama",   "Akira Toriyama",             "manga"),
    ("miyazaki",   "Hayao Miyazaki",             "manga"),
    ("taniguchi",  "Jirō Taniguchi",             "manga"),
    ("matsumoto",  "Taiyō Matsumoto",            "manga"),
    ("urasawa",    "Naoki Urasawa",              "manga"),
    ("fujio",      "Fujiko F. Fujio",            "manga"),
    ("chiba",      "Chiba Tetsuya",              "manga"),
    ("oda",        "Eiichiro Oda",               "manga"),
    ("takahashi",  "Rumiko Takahashi",           "manga"),
    ("araki",      "Hirohiko Araki",             "manga"),
    ("miura",      "Kentaro Miura",              "manga"),
    ("inoue",      "Takehiko Inoue",             "manga"),
    ("asano",      "Inio Asano",                 "manga"),
    # Contemporary pen canon — comic-strip
    ("watterson",  "Bill Watterson",             "comic-strip"),
    ("schulz",     "Charles Schulz",             "comic-strip"),
    ("larson",     "Gary Larson",                "comic-strip"),
    ("adams",      "Scott Adams",                "comic-strip"),
    ("herge",      "Hergé",                      "comic-strip"),
    # Contemporary pen canon — caricature
    ("hirschfeld", "Al Hirschfeld",              "caricature"),
    ("searle",     "Ronald Searle",              "caricature"),
    ("sempe",      "Jean-Jacques Sempé",         "caricature"),
    ("shrigley",   "David Shrigley",             "caricature"),
    ("steadman",   "Ralph Steadman",             "caricature"),
    ("spiegelman", "Art Spiegelman",             "caricature"),
    # XKCD
    ("xkcd",       "Randall Munroe (xkcd)",      "xkcd"),
]


def ensure_thumb(src: Path) -> Path | None:
    """Generate a ≤480 px thumbnail keyed on source path + mtime.
    Returns path to thumb (in _staging/contact-sheet-thumbs/), or None on error.
    Skips work if thumb already exists and is newer than source."""
    if not src.exists():
        return None
    THUMBS.mkdir(parents=True, exist_ok=True)
    # Key by path hash so differently-named files don't collide
    key = hashlib.md5(str(src).encode()).hexdigest()[:12]
    thumb = THUMBS / f"{key}-{src.stem}.jpg"
    if thumb.exists() and thumb.stat().st_mtime >= src.stat().st_mtime:
        return thumb
    try:
        with Image.open(src) as im:
            im.thumbnail((THUMB_MAX, THUMB_MAX), Image.LANCZOS)
            if im.mode in ("RGBA", "P"):
                im = im.convert("RGB")
            im.save(thumb, format="JPEG", quality=82, optimize=True)
        return thumb
    except Exception as e:
        print(f"  thumb failed for {src.name}: {e}")
        return None


def load_items():
    items = []
    for prefix, artist, lineage in CREATORS:
        for folder in ("images", "personal_library"):
            for yml in (CORPUS / folder).glob(f"{prefix}-*.yaml"):
                # Filter out photographer collisions like "lewis-hine-*"
                if prefix == "lewis" and yml.stem.startswith("lewis-hine"):
                    continue
                if prefix == "ward" and not yml.stem.startswith("ward-"):
                    continue
                try:
                    data = yaml.safe_load(yml.read_text())
                except Exception:
                    continue
                if not isinstance(data, dict):
                    continue
                # skip text-only items that happen to share a prefix
                if not any(data.get(k) for k in ("pixel_width",)):
                    continue
                img = None
                for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
                    p = yml.with_suffix(ext)
                    if p.exists():
                        img = p
                        break
                thumb = ensure_thumb(img) if img else None
                items.append({
                    "id": data.get("id", yml.stem),
                    "title": data.get("title", ""),
                    "artist": data.get("artist", artist),
                    "artist_key": prefix,
                    "lineage": lineage,
                    "form": data.get("form", ""),
                    "year": data.get("year", ""),
                    "w": data.get("pixel_width", 0),
                    "h": data.get("pixel_height", 0),
                    "source": data.get("source", ""),
                    "source_url": data.get("source_url", ""),
                    "tier": data.get("rights_tier", ""),
                    "img_path": str(img.resolve()) if img else "",
                    "thumb_path": str(thumb.resolve()) if thumb else "",
                    "yaml_path": str(yml.resolve()),
                })
    items.sort(key=lambda r: (r["lineage"], r["artist_key"], r["id"]))
    return items


def render(items) -> str:
    by_creator = {}
    for i in items:
        by_creator.setdefault(i["artist_key"], []).append(i)

    creator_filters = ""
    for prefix, artist, lineage in CREATORS:
        n = len(by_creator.get(prefix, []))
        creator_filters += (
            f'<button class="filter-btn" data-filter="{prefix}">'
            f'{html.escape(artist)} <span class="count">{n}</span></button>\n'
        )

    cards = ""
    for r in items:
        full_src = f"file://{r['img_path']}" if r["img_path"] else ""
        thumb_src = f"file://{r['thumb_path']}" if r["thumb_path"] else full_src
        title = html.escape(str(r["title"]))
        artist = html.escape(str(r["artist"]))
        src = html.escape(str(r["source"]))
        url = html.escape(str(r["source_url"] or ""))
        lineage = r["lineage"]
        tier = r["tier"]
        tier_badge = "PD" if tier == "public_domain" else ("PL" if tier == "personal_library" else tier)
        form = html.escape(r["form"])
        res = f"{r['w']}×{r['h']}"
        pref_ok = max(r["w"], r["h"]) >= 1800
        res_class = "res-ok" if pref_ok else "res-low"
        cards += f'''
<div class="card" data-creator="{r["artist_key"]}" data-lineage="{lineage}" data-tier="{tier}">
  <a href="{html.escape(full_src)}" target="_blank" class="thumb-link">
    <img class="thumb" src="{html.escape(thumb_src)}" loading="lazy" alt="{html.escape(r["id"])}">
  </a>
  <div class="meta">
    <div class="id">{html.escape(r["id"])}</div>
    <div class="title">{title}</div>
    <div class="artist">{artist} · <span class="year">{r["year"] or ""}</span></div>
    <div class="row">
      <span class="tag tag-form">{form}</span>
      <span class="tag tag-{tier}">{tier_badge}</span>
      <span class="tag {res_class}">{res}</span>
      <span class="tag tag-src">{src}</span>
    </div>
    <div class="links">
      <a href="{url}" target="_blank">source</a> ·
      <a href="file://{html.escape(r["yaml_path"])}" target="_blank">yaml</a>
    </div>
  </div>
</div>'''.strip() + "\n"

    return f"""<!doctype html>
<html><head><meta charset="utf-8">
<title>B&amp;W graphic-arts canon — contact sheet</title>
<style>
  body {{ font: 13px/1.4 -apple-system, sans-serif; margin: 0; background: #111; color: #eee; }}
  header {{ padding: 12px 20px; background: #1a1a1a; border-bottom: 1px solid #333; position: sticky; top: 0; z-index: 10; }}
  h1 {{ font-size: 15px; font-weight: 600; margin: 0 0 8px; }}
  .stats {{ color: #888; font-size: 12px; margin-bottom: 8px; }}
  .filters {{ display: flex; flex-wrap: wrap; gap: 4px; }}
  .filter-btn {{
    background: #222; color: #ccc; border: 1px solid #333; padding: 4px 8px;
    border-radius: 3px; font-size: 11px; cursor: pointer; font-family: inherit;
  }}
  .filter-btn:hover {{ background: #333; }}
  .filter-btn.active {{ background: #3a6ea5; color: white; border-color: #3a6ea5; }}
  .filter-btn .count {{ color: #888; margin-left: 4px; }}
  .filter-btn.active .count {{ color: #cde; }}
  #reset-btn {{ background: #2a2a2a; }}

  .grid {{
    display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: 12px; padding: 20px;
  }}
  .card {{ background: #181818; border-radius: 4px; overflow: hidden; display: flex; flex-direction: column; }}
  .card.hidden {{ display: none; }}
  .thumb-link {{ display: block; background: #0a0a0a; aspect-ratio: 1; overflow: hidden; }}
  .thumb {{ width: 100%; height: 100%; object-fit: contain; display: block; }}
  .meta {{ padding: 8px; font-size: 11px; flex: 1; display: flex; flex-direction: column; gap: 4px; }}
  .id {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; color: #7a9; font-size: 10px; word-break: break-all; }}
  .title {{ color: #eee; font-weight: 500; }}
  .artist {{ color: #999; }}
  .year {{ color: #666; }}
  .row {{ display: flex; flex-wrap: wrap; gap: 3px; margin-top: 4px; }}
  .tag {{ font-size: 9px; padding: 2px 5px; border-radius: 2px; background: #2a2a2a; color: #bbb; }}
  .tag-form {{ background: #2a3b4d; color: #9cd; }}
  .tag-public_domain {{ background: #2d3d2a; color: #acc; }}
  .tag-personal_library {{ background: #3d3a2a; color: #dca; }}
  .tag-src {{ background: #2a2a35; color: #aab; }}
  .res-ok {{ background: #2a3d2a; color: #ada; }}
  .res-low {{ background: #3d2a2a; color: #daa; }}
  .links {{ margin-top: auto; padding-top: 4px; color: #666; font-size: 10px; }}
  .links a {{ color: #7a9; text-decoration: none; }}
  .links a:hover {{ text-decoration: underline; }}
</style>
</head><body>
<header>
  <h1>B&amp;W graphic-arts canon — stage-2 fetched items</h1>
  <div class="stats"><b>{len(items)}</b> items across <b>{len([c for c in by_creator if by_creator[c]])}</b> creators · click a thumbnail to open full-res · click a chip to filter</div>
  <div class="filters">
    <button id="reset-btn" class="filter-btn active" data-filter="">all <span class="count">{len(items)}</span></button>
    {creator_filters}
  </div>
</header>
<div class="grid" id="grid">
{cards}
</div>
<script>
  const btns = document.querySelectorAll('.filter-btn');
  const cards = document.querySelectorAll('.card');
  btns.forEach(b => b.addEventListener('click', () => {{
    btns.forEach(x => x.classList.remove('active'));
    b.classList.add('active');
    const f = b.dataset.filter;
    cards.forEach(c => {{
      c.classList.toggle('hidden', f && c.dataset.creator !== f);
    }});
  }}));
</script>
</body></html>
"""


def main():
    items = load_items()
    html_out = render(items)
    out = REPO / "corpus" / "_staging" / "bw-graphic-arts-contact-sheet.html"
    out.write_text(html_out)
    print(f"wrote {out}  ({len(items)} items)")


if __name__ == "__main__":
    main()

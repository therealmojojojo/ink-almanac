"""Triplet generator v2 — recency + cap + text-only-summary + dark-nocturne.

Rules (2026-04-21):
  1. Every triplet has summary = text (zone-fit: ≤4 lines, ≤24 chars/line).
  2. Gallery split: 65% visual-day (image) / 35% text-day (text, hero-density).
  3. Per-item cap: 5 total appearances across all generated triplets.
  4. Recency window: no item re-appears in any triplet within 100 positions
     of its last use. Triplets carry `sequence` so the device scheduler
     can run them in order.
  5. Nocturne eligibility: image is portrait/square AND has ≥50% dark pixels
     (threshold 128 on 0–255 luminance). Theme no longer gates nocturne.
  6. No theme-matching preference — random pick within the available pool.
     Themes still required as a basic eligibility filter (item must have ≥1).
  7. Existing triplet verdicts (`triplet_verdict`, `_reason`, `_reviewed_at`)
     are preserved on any surviving id. Orphaned verdicts are dropped.

Usage:
  python corpus_build_triplets_v2.py          # dry-run + stats
  python corpus_build_triplets_v2.py --apply  # wipe + regenerate _triplets/
"""
from __future__ import annotations
import argparse, datetime, json, random, sys
from collections import Counter, deque
from pathlib import Path

import yaml

try:
    from PIL import Image
except ImportError:
    sys.exit("PIL/Pillow required: pip install Pillow")

CORPUS = Path(__file__).resolve().parent.parent / "corpus"
TRIPLETS_DIR = CORPUS / "_triplets"
CACHE_DIR = CORPUS / "_caches"
DARK_CACHE = CACHE_DIR / "dark-fractions.json"

ANCHOR_FORMS = {"haiku", "aphorism", "fragment", "quote", "song-chorus", "lyric"}
# Generic "bucket" themes that describe context rather than subject. Almost
# every item has at least one of these (34% tagged everyday-life, 25% urban),
# so a shared theme that's only in this set isn't a real thematic bridge —
# it's taxonomic noise.
GENERIC_THEMES = {"everyday-life", "urban"}
# Visual-quality themes — describe HOW an image looks, not WHAT it depicts.
# These crowd position-0 on photography items (an image's most salient
# surface is often chiaroscuro or a decisive-moment gesture) but texts
# rarely tag on them, so matching across modalities works better when
# they're stripped. From the themes taxonomy's "Motion, weather,
# orientation" section — the two descriptive-rather-than-subject entries.
VISUAL_THEMES = {"light-shadow", "motion-and-gesture"}
# Themes stripped when computing an item's DOMINANT themes for pairing:
# subjects only, no bucket tags, no visual-property tags.
NON_SUBJECT_THEMES = GENERIC_THEMES | VISUAL_THEMES


def dominant_themes(themes, k=2):
    """First `k` themes after stripping bucket + visual-quality tags.
    Used for thematic matching between summary and gallery; ensures the
    shared theme is a real subject (solitude, mortality, journey, …),
    not taxonomic noise or a formal property."""
    return [t for t in (themes or []) if t not in NON_SUBJECT_THEMES][:k]
SUMMARY_MAX_LINES = 4
SUMMARY_MAX_CHARS = 24
GALLERY_MIN_LINES = 4
GALLERY_SHORT_EXEMPT = {"haiku", "tanka"}

DARK_THRESHOLD = 128
DARK_AREA_MIN = 0.50
PER_ITEM_CAP = 5
TEXT_DAY_SHARE = 0.35
ALIGNED_NOCTURNE_SHARE = 0.50
RECENCY_WINDOW = 100

NOTE_TEMPLATES_VISUAL = [
    "The poem listens; the image watches.",
    "Two ways of attending to the same quiet.",
    "Where the line ends and the shape begins.",
    "A small weight of attention held between them.",
    "The text names, the image lets stand.",
    "What the poem carries, the image grounds.",
    "Quiet company.",
    "Each makes the other stranger.",
]
NOTE_TEMPLATES_TEXT = [
    "The image holds; the poem sings.",
    "The picture grounds; the poem carries.",
    "Two ways of keeping still.",
    "What the poem names, the image remembers.",
    "The summary image grounds; the poem carries.",
    "One frame, one voice.",
]

# ---------- Loaders ----------

def body_of(doc: dict) -> str:
    tv = doc.get("text_variants")
    if isinstance(tv, dict) and tv:
        return tv.get("en") or next(iter(tv.values())) or ""
    return doc.get("text") or ""


def orient(w: int, h: int) -> str:
    if not (w and h):
        return "unknown"
    if w > h:
        return "landscape"
    if h > w:
        return "portrait"
    return "square"


def find_binary(yaml_path: Path) -> Path | None:
    for ext in (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"):
        bp = yaml_path.with_suffix(ext)
        if bp.exists():
            return bp
    return None


def load_items():
    items = {}
    for folder in ("texts", "personal_library"):
        d = CORPUS / folder
        if not d.is_dir():
            continue
        for p in sorted(d.glob("*.yaml")):
            if p.stem.startswith("EXAMPLE"):
                continue
            try:
                doc = yaml.safe_load(p.read_text())
            except yaml.YAMLError:
                continue
            if not isinstance(doc, dict) or "id" not in doc:
                continue
            binary = find_binary(p)
            is_image = bool(binary) or (doc.get("pixel_width") and doc.get("pixel_height"))
            kind = "image" if is_image else "text"
            body = body_of(doc) if kind == "text" else ""
            lines = [ln for ln in body.splitlines() if ln.strip()] if body else []
            items[doc["id"]] = {
                "id": doc["id"],
                "kind": kind,
                "form": doc.get("form"),
                "folder": folder,
                "themes": list(doc.get("themes") or []),
                "fid": doc.get("panel_fidelity"),
                "binary": str(binary) if binary else None,
                "pw": doc.get("pixel_width") or 0,
                "ph": doc.get("pixel_height") or 0,
                "orient": orient(doc.get("pixel_width") or 0,
                                  doc.get("pixel_height") or 0),
                "n_lines": len(lines),
                "max_chars": max((len(ln) for ln in lines), default=0),
            }
    return items


# ---------- Dark-fraction cache ----------

def compute_dark_fraction(binary_path: str) -> float:
    try:
        im = Image.open(binary_path).convert("L")
        im.thumbnail((200, 200))
        px = list(im.getdata())
        if not px:
            return 0.0
        return sum(1 for v in px if v < DARK_THRESHOLD) / len(px)
    except Exception:
        return 0.0


def load_dark_cache() -> dict:
    if DARK_CACHE.exists():
        try:
            return json.loads(DARK_CACHE.read_text())
        except json.JSONDecodeError:
            pass
    return {}


def save_dark_cache(cache: dict) -> None:
    CACHE_DIR.mkdir(exist_ok=True)
    DARK_CACHE.write_text(json.dumps(cache, indent=2, sort_keys=True))


def attach_dark_fractions(items: dict) -> None:
    cache = load_dark_cache()
    changed = False
    for it in items.values():
        if it["kind"] != "image" or not it["binary"]:
            it["dark_frac"] = 0.0
            continue
        key = it["id"]
        if key in cache:
            it["dark_frac"] = cache[key]
            continue
        it["dark_frac"] = compute_dark_fraction(it["binary"])
        cache[key] = it["dark_frac"]
        changed = True
    if changed:
        save_dark_cache(cache)


# ---------- Pool derivation ----------

def derive_pools(items: dict):
    vals = list(items.values())
    anchors = [
        it for it in vals
        if it["kind"] == "text"
        and it["form"] in ANCHOR_FORMS
        and it["themes"]
    ]
    summary_texts = [
        it for it in vals
        if it["kind"] == "text"
        and it["themes"]
        and 0 < it["n_lines"] <= SUMMARY_MAX_LINES
        and it["max_chars"] <= SUMMARY_MAX_CHARS
    ]
    gallery_texts = [
        it for it in vals
        if it["kind"] == "text"
        and it["themes"]
        and (it["n_lines"] >= GALLERY_MIN_LINES or it["form"] in GALLERY_SHORT_EXEMPT)
    ]
    day_images = [
        it for it in vals
        if it["kind"] == "image"
        and it["fid"] in ("native", "robust")
        and it["themes"]
    ]
    gallery_image_pool = day_images
    nocturne_pool = [
        it for it in day_images
        if it["orient"] in ("portrait", "square")
        and it["dark_frac"] >= DARK_AREA_MIN
    ]
    return {
        "anchors": anchors,
        "summary_texts": summary_texts,
        "gallery_texts": gallery_texts,
        "gallery_image_pool": gallery_image_pool,
        "nocturne_pool": nocturne_pool,
    }


# ---------- Triplet themes ----------

def triplet_themes(anchor, summary, gallery):
    seen = set()
    out = []
    shared = set(anchor["themes"]) & (set(summary["themes"]) | set(gallery["themes"]))
    for t in shared:
        if t not in seen and len(out) < 3:
            out.append(t); seen.add(t)
    for item in (anchor, gallery, summary):
        for t in item["themes"]:
            if t not in seen and len(out) < 3:
                out.append(t); seen.add(t)
    if not out and anchor["themes"]:
        out = anchor["themes"][:2]
    return out[:3]


# ---------- Generator ----------

def generate(items, pools, seed=42, max_attempts=1_000_000):
    rng = random.Random(seed)
    anchors = pools["anchors"]
    summary_texts = pools["summary_texts"]
    gallery_texts = pools["gallery_texts"]
    gallery_image_pool = pools["gallery_image_pool"]
    nocturne_pool = pools["nocturne_pool"]

    use = Counter()
    window = deque()        # each elt = frozenset(ids) of one triplet
    recent_block = set()    # union of the ids in window

    def avail(pool, exclude=()):
        return [it for it in pool
                if use[it["id"]] < PER_ITEM_CAP
                and it["id"] not in recent_block
                and it["id"] not in exclude]

    def refresh_block():
        nonlocal recent_block
        recent_block = set().union(*window) if window else set()

    triplets = []
    seen_keys = set()
    flavor_c = Counter()
    aligned_c = 0
    attempts = 0
    while attempts < max_attempts:
        attempts += 1
        flavor = rng.choices(
            ["visual-day", "text-day"],
            weights=[1 - TEXT_DAY_SHARE, TEXT_DAY_SHARE],
        )[0]

        a_pool = avail(anchors)
        if not a_pool:
            # early exit once no anchor has capacity outside the window
            if all(use[a["id"]] >= PER_ITEM_CAP for a in anchors):
                break
            continue
        anchor = rng.choice(a_pool)

        s_pool = avail(summary_texts, exclude=(anchor["id"],))
        if not s_pool:
            continue
        summary = rng.choice(s_pool)

        g_src = gallery_image_pool if flavor == "visual-day" else gallery_texts
        g_pool = avail(g_src, exclude=(anchor["id"], summary["id"]))
        # Thematic coherence: summary's dominant subject themes (first
        # 2 after stripping generic buckets and visual-quality tags)
        # must intersect gallery's dominant subject themes. Symmetric
        # for text-day and visual-day — because the exclusion set
        # already strips the photo-biased tags that were pushing
        # images' real subjects out of their top-2.
        s_dominant = set(dominant_themes(summary.get("themes")))
        if not s_dominant:
            continue
        g_pool = [
            g for g in g_pool
            if set(dominant_themes(g.get("themes"))) & s_dominant
        ]
        if not g_pool:
            continue
        gallery = rng.choice(g_pool)

        key = (anchor["id"], summary["id"], gallery["id"])
        if len(set(key)) != 3 or key in seen_keys:
            continue

        aligned_id = None
        if rng.random() < ALIGNED_NOCTURNE_SHARE:
            n_pool = avail(nocturne_pool, exclude=key)
            if n_pool:
                aligned_id = rng.choice(n_pool)["id"]

        trip_ids = set(key)
        if aligned_id:
            trip_ids.add(aligned_id)

        themes = triplet_themes(anchor, summary, gallery)
        if not themes:
            continue

        note_pool = NOTE_TEMPLATES_VISUAL if flavor == "visual-day" else NOTE_TEMPLATES_TEXT
        trip_id = f"{anchor['id'][:18]}-{summary['id'][:18]}-{gallery['id'][:18]}"
        triplet = {
            "id": trip_id,
            "sequence": len(triplets) + 1,
            "anchor": anchor["id"],
            "summary": summary["id"],
            "gallery": gallery["id"],
            "flavor": flavor,
            "themes": themes,
            "note": rng.choice(note_pool),
            "added": datetime.date.today().isoformat(),
        }
        if aligned_id:
            triplet["aligned_nocturne"] = aligned_id

        triplets.append(triplet)
        seen_keys.add(key)
        flavor_c[flavor] += 1
        for i in trip_ids:
            use[i] += 1
        window.append(frozenset(trip_ids))
        recent_block |= trip_ids
        if len(window) > RECENCY_WINDOW:
            window.popleft()
            refresh_block()

    stats = {
        "triplets": len(triplets),
        "attempts": attempts,
        "visual_day": flavor_c["visual-day"],
        "text_day": flavor_c["text-day"],
        "aligned_nocturne": sum(1 for t in triplets if "aligned_nocturne" in t),
        "items_at_cap": sum(1 for c in use.values() if c >= PER_ITEM_CAP),
    }
    return triplets, stats


# ---------- Verdict preservation ----------

def snapshot_verdicts():
    verdicts = {}
    if not TRIPLETS_DIR.is_dir():
        return verdicts
    for p in TRIPLETS_DIR.glob("*.yaml"):
        try:
            doc = yaml.safe_load(p.read_text())
        except yaml.YAMLError:
            continue
        if not isinstance(doc, dict):
            continue
        v = doc.get("triplet_verdict")
        if v:
            verdicts[doc.get("id", p.stem)] = {
                "triplet_verdict": v,
                "triplet_verdict_reason": doc.get("triplet_verdict_reason"),
                "triplet_verdict_reviewed_at": doc.get("triplet_verdict_reviewed_at"),
            }
    return verdicts


def apply_verdict(triplet, verdict_snapshot):
    v = verdict_snapshot.get(triplet["id"])
    if not v:
        return
    triplet["triplet_verdict"] = v["triplet_verdict"]
    if v.get("triplet_verdict_reason"):
        triplet["triplet_verdict_reason"] = v["triplet_verdict_reason"]
    if v.get("triplet_verdict_reviewed_at"):
        triplet["triplet_verdict_reviewed_at"] = v["triplet_verdict_reviewed_at"]


# ---------- Writer ----------

def write_triplets(triplets):
    TRIPLETS_DIR.mkdir(exist_ok=True)
    for p in TRIPLETS_DIR.glob("*.yaml"):
        p.unlink()
    for t in triplets:
        out = TRIPLETS_DIR / f"{t['id']}.yaml"
        out.write_text(yaml.safe_dump(t, sort_keys=False, allow_unicode=True,
                                       default_flow_style=False, width=200))


# ---------- CLI ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="wipe corpus/_triplets/ and write the new pool")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    print("Loading items…")
    items = load_items()
    print(f"  {len(items)} items")
    print("Computing dark-fractions (cached)…")
    attach_dark_fractions(items)
    pools = derive_pools(items)
    print(f"POOLS: anchors={len(pools['anchors'])}  "
          f"summary={len(pools['summary_texts'])}  "
          f"gal-text={len(pools['gallery_texts'])}  "
          f"gal-image={len(pools['gallery_image_pool'])}  "
          f"nocturne={len(pools['nocturne_pool'])}")

    triplets, stats = generate(items, pools, seed=args.seed)
    print(f"\nGenerated: {stats['triplets']} triplets")
    print(f"  visual-day:  {stats['visual_day']}")
    print(f"  text-day:    {stats['text_day']}")
    print(f"  w/ nocturne: {stats['aligned_nocturne']}")
    print(f"  items at cap: {stats['items_at_cap']}")
    print(f"  attempts:    {stats['attempts']}")
    print(f"  years of daily content: {stats['triplets']/365:.1f}")

    if args.apply:
        print("\nPreserving existing verdicts…")
        snap = snapshot_verdicts()
        carried = 0
        for t in triplets:
            if t["id"] in snap:
                apply_verdict(t, snap)
                carried += 1
        dropped = len(snap) - carried
        print(f"  carried forward: {carried}")
        print(f"  dropped (id not in new pool): {dropped}")
        print("Writing _triplets/…")
        write_triplets(triplets)
        print(f"  wrote {len(triplets)} triplet sidecars")

if __name__ == "__main__":
    main()

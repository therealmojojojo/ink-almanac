"""Triplet generator v2 — recency + cap + text-only-summary + dark-nocturne.

Rules (2026-04-21):
  1. Every triplet has summary = text. Eligibility is wrap-aware: simulate
     greedy word-wrap at 24 cols/line and admit when the resulting visual
     line count is ≤ 4. Replaces the older 1:1 `n_lines ≤ 4 AND
     max_chars ≤ 24` gate, which rejected canonical lines that were one
     or two chars over (Blake "Hold infinity in the palm of your hand,"
     etc.) even though `white-space: pre-line` in the renderer would have
     wrapped them cleanly.
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
import argparse, datetime, json, math, random, sys
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
GALLERY_MIN_LINES = 4
GALLERY_SHORT_EXEMPT = {"haiku", "tanka"}

# Mirror renderer/src/modes/summary.ts:DELIGHT_TIERS verbatim.
# (font_u, line_height_u, soft_cpl, max_visual_lines)
DELIGHT_TIERS: dict[int, tuple[int, int, int, int]] = {
    1: (36, 48, 34,  7),
    2: (32, 44, 38,  8),
    3: (30, 40, 41,  9),
    4: (28, 34, 44, 11),
    5: (28, 30, 44, 12),
    6: (24, 32, 52, 11),
    7: (22, 28, 57, 13),
}
PILL_FLOOR_TIERS = (1, 2, 3, 4, 5)   # ≥28u — picker's admissible band
WRAP_TIERS_AT_FLOOR = (4, 5)         # 28u with wrap (Phase 2)
SUB_FLOOR_TIERS = (6, 7)             # below 28u — escape only, picker excludes


def _visual_lines_at(lines: list[str], cpl: int) -> int:
    return sum(max(1, math.ceil(len(ln) / cpl)) for ln in lines)


def pick_fit_tier(body: str) -> int | None:
    """Mirror renderer/src/modes/summary.ts:pickFitTier. Returns the largest
    tier that fits the body without last-resort sub-floor wrap, or None when
    no tier in phases 1–3 fits (the renderer would still render via tier-7
    wrap, but the picker will not surface such items)."""
    lines = [ln.rstrip() for ln in body.splitlines() if ln.strip()]
    if not lines:
        return None
    longest = max(len(ln) for ln in lines)
    n = len(lines)
    # Phase 1 — unwrapped at ≥28u
    for t in PILL_FLOOR_TIERS:
        _, _, cpl, mvl = DELIGHT_TIERS[t]
        if longest <= cpl and n <= mvl:
            return t
    # Phase 2 — wrap at 28u (tiers 4, 5)
    for t in WRAP_TIERS_AT_FLOOR:
        _, _, cpl, mvl = DELIGHT_TIERS[t]
        if _visual_lines_at(lines, cpl) <= mvl:
            return t
    # Phase 3 — sub-floor unwrapped escape (tiers 6, 7)
    for t in SUB_FLOOR_TIERS:
        _, _, cpl, mvl = DELIGHT_TIERS[t]
        if longest <= cpl and n <= mvl:
            return t
    return None

DARK_THRESHOLD = 128
DARK_AREA_MIN = 0.50
# Per-slot caps for TEXT items. Anchor is the triplet's invisible spine
# (used for thematic matching and daily-rotation identity, but never rendered
# to any face), so its reuse doesn't read as duplication to the viewer.
# Summary and gallery are user-visible (delight cell, smart pill, gallery
# hero) — repeat use there IS duplication. Nocturne renders on the Night
# face.
SLOT_CAP = {
    "anchor":   999,   # effectively uncapped (invisible)
    "summary":    3,
    "gallery":    3,
    "nocturne":   3,
}
# Images never repeat at the gallery slot — that's the visible hero, and
# the corpus has 1100+ gallery-eligible images, so duplication there reads
# as "we already saw this." Nocturne is the least-visible face (Night-only,
# narrow daily window) and its dark/portrait pool is smaller (~420), so
# allowing a single repeat there keeps the night face populated without
# bottoming out coverage.
IMAGE_CAP = {"gallery": 1, "nocturne": 2}
# Generic constant for backward-compat references and stat reporting.
PER_ITEM_CAP = 3


def cap_for(item, slot):
    """Effective per-(item, slot) cap. Images cap by slot (gallery=1,
    nocturne=2). Texts use the per-slot cap from SLOT_CAP."""
    if item.get("kind") == "image":
        return IMAGE_CAP.get(slot, 1)
    return SLOT_CAP.get(slot, PER_ITEM_CAP)
TEXT_DAY_SHARE = 0.40
ALIGNED_NOCTURNE_SHARE = 0.50
RECENCY_WINDOW = 100
# Cap on per-pass random-draw failures before that pass gives up. Tuned to
# admit reasonable thrashing without burning a million attempts on a search
# that's converged on "no valid pairing exists for the remaining state".
MAX_CONSECUTIVE_FAILURES = 50_000

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
    # `images` (PD print canon — Dürer/Rembrandt/Piranesi/etc.) was missing
    # from v2's folder list; restored 2026-04-28 (picker-coverage-fix). The
    # 119 sidecars there were ingested by add-bw-graphic-arts-canon as the
    # non-photograph spine and dropping them was a regression vs v1.
    for folder in ("texts", "personal_library", "images"):
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
                # `summary_eligible: false` opts a sidecar out of the
                # delight-cell pool (item still gallery/anchor-eligible).
                # Default-true semantics: absence = eligible.
                "summary_eligible": doc.get("summary_eligible", True),
                "binary": str(binary) if binary else None,
                "pw": doc.get("pixel_width") or 0,
                "ph": doc.get("pixel_height") or 0,
                "orient": orient(doc.get("pixel_width") or 0,
                                  doc.get("pixel_height") or 0),
                "n_lines": len(lines),
                "max_chars": max((len(ln) for ln in lines), default=0),
                "fit_tier": pick_fit_tier(body) if body else None,
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
    # Eligibility mirrors the renderer's tier ladder: admit any text that
    # fits at one of the pill-floor tiers (1–5, ≥28u) or at the sub-floor
    # unwrapped escape (6–7, 24u/22u). Items where the renderer would have
    # to fall back to tier-7 wrap are still rejected — the picker should
    # never surface a delight cell that reads as smaller than the pill.
    summary_texts = [
        it for it in vals
        if it["kind"] == "text"
        and it["themes"]
        and it.get("summary_eligible", True)
        and it.get("fit_tier") is not None
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

def generate(items, pools, seed=42):
    """Two-pass generation with min-use coverage bias.

    Pass 1 (coverage): every eligible item used at most once. The picker
    walks anchors / summaries / galleries with `use[id] == 0` filters and
    the same theme constraint. Caps out when no new unique-item triplet
    is possible (no anchor / summary / matching gallery with use==0).

    Pass 2 (fill): continue to `triplet_target` with PER_ITEM_CAP=3 reuse.
    `avail()` returns only items at `min(use[id])` within the eligible
    pool, so use=0 items are picked before use=1 before use=2 — a strict
    coverage bias rather than uniform-random over the eligible set.

    Target = min(anchor_pool, summary_pool) * PER_ITEM_CAP — the math
    upper bound of the system. Both passes give up after
    MAX_CONSECUTIVE_FAILURES rejected attempts.
    """
    rng = random.Random(seed)
    anchors = pools["anchors"]
    summary_texts = pools["summary_texts"]
    gallery_texts = pools["gallery_texts"]
    gallery_image_pool = pools["gallery_image_pool"]
    nocturne_pool = pools["nocturne_pool"]

    # Per-slot use counter: an item playing different roles across triplets
    # is fresh content (anchor / summary delight / gallery hero are three
    # different visual treatments). Cap applies per (id, slot) pair, not
    # per id globally. Recency window stays per-item (don't show the same
    # TEXT three days running, even in different roles).
    use = Counter()                # key: (item_id, slot)
    window = deque()
    recent_block = set()

    def refresh_block():
        nonlocal recent_block
        recent_block = set().union(*window) if window else set()

    triplets = []
    seen_keys = set()
    flavor_c = Counter()

    def pick_eligible(pool, slot: str, exclude=(), post_filter=None,
                      strict_unique: bool = False):
        """Return (candidates, weights) for the random-weighted choice at
        the call site. Min-use bias is applied via weights, NOT a hard
        tier filter — items at higher use levels stay available so a
        theme-rare summary at use=0 can't deadlock the picker.

        Anchor (cap≥100): no bias, uniform pick.
        Capped slots: weight = (cap - use), so use=0 → weight 3,
        use=1 → weight 2, use=2 → weight 1.
        strict_unique=True (pass 1): hard-filter to use=0 only.
        post_filter runs after the use/recency/exclude filter."""
        candidates = [it for it in pool
                      if use[(it["id"], slot)] < cap_for(it, slot)
                      and it["id"] not in recent_block
                      and it["id"] not in exclude]
        if strict_unique:
            candidates = [it for it in candidates if use[(it["id"], slot)] == 0]
        if post_filter:
            candidates = post_filter(candidates)
        if not candidates:
            return [], []
        # Anchor pool is uncapped — uniform pick. For everything else, weight
        # = (cap - use) so use=0 is preferred over use=1 over use=2. Images
        # are always cap=1 (weight 1 when eligible, 0 once used).
        slot_cap = SLOT_CAP.get(slot, PER_ITEM_CAP)
        if slot_cap >= 100:
            weights = [1.0] * len(candidates)
        else:
            weights = [cap_for(it, slot) - use[(it["id"], slot)]
                       for it in candidates]
        return candidates, weights

    def attempt(summary_strict: bool) -> bool:
        """Try to make one triplet.

        Pass 1 (summary_strict=True): every summary must be at use=0.
        Forces every summary text to appear once before any reuse. Anchor
        and gallery use min-use weighted bias (not strict). After pass 1
        every summary that CAN pair has paired.

        Pass 2 (summary_strict=False): summary uses weighted bias too,
        with falls-through naturally to higher use levels when theme-
        rare summaries deadlock at use=0."""
        nonlocal recent_block

        flavor = rng.choices(
            ["visual-day", "text-day"],
            weights=[1 - TEXT_DAY_SHARE, TEXT_DAY_SHARE],
        )[0]

        a_pool, a_w = pick_eligible(anchors, slot="anchor")
        if not a_pool:
            return False
        anchor = rng.choices(a_pool, weights=a_w, k=1)[0]

        s_pool, s_w = pick_eligible(summary_texts, slot="summary",
                                    exclude=(anchor["id"],),
                                    strict_unique=summary_strict)
        if not s_pool:
            return False
        summary = rng.choices(s_pool, weights=s_w, k=1)[0]

        g_src = gallery_image_pool if flavor == "visual-day" else gallery_texts
        s_dominant = set(dominant_themes(summary.get("themes")))
        if not s_dominant:
            return False
        # Theme constraint: summary's dominant subjects must intersect
        # gallery's dominant subjects. Stripped of generic / visual-only
        # tags so the match is on real subjects.
        def themed(pool):
            return [g for g in pool
                    if set(dominant_themes(g.get("themes"))) & s_dominant]
        g_pool, g_w = pick_eligible(g_src, slot="gallery",
                                    exclude=(anchor["id"], summary["id"]),
                                    post_filter=themed)
        # Soft theme preference: when no theme-matched candidate is
        # available (image-cap-1 + dwindling pool exhausts the themed
        # subset fast), fall back to any unused gallery item rather than
        # dropping the attempt. Keeps visual-day from collapsing into
        # text-day when the image pool is theme-mismatched but otherwise
        # plentiful.
        if not g_pool:
            g_pool, g_w = pick_eligible(g_src, slot="gallery",
                                        exclude=(anchor["id"], summary["id"]))
        if not g_pool:
            return False
        gallery = rng.choices(g_pool, weights=g_w, k=1)[0]

        key = (anchor["id"], summary["id"], gallery["id"])
        if len(set(key)) != 3 or key in seen_keys:
            return False

        aligned_id = None
        if rng.random() < ALIGNED_NOCTURNE_SHARE:
            n_pool, n_w = pick_eligible(nocturne_pool, slot="nocturne", exclude=key)
            if n_pool:
                aligned_id = rng.choices(n_pool, weights=n_w, k=1)[0]["id"]

        trip_ids = set(key)
        if aligned_id:
            trip_ids.add(aligned_id)

        themes = triplet_themes(anchor, summary, gallery)
        if not themes:
            return False

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
        # Per-slot use counters — same item playing different roles is
        # fresh content, not duplication.
        use[(anchor["id"], "anchor")] += 1
        use[(summary["id"], "summary")] += 1
        use[(gallery["id"], "gallery")] += 1
        if aligned_id:
            use[(aligned_id, "nocturne")] += 1
        window.append(frozenset(trip_ids))
        recent_block |= trip_ids
        if len(window) > RECENCY_WINDOW:
            window.popleft()
            refresh_block()
        return True

    # Target: bounded by the *visible* slots' cap. Summary is the gating
    # visible slot (anchors are the invisible thematic spine and may reuse
    # freely). Setting target = summary_pool * PER_ITEM_CAP lets the picker
    # ride the full summary capacity even when the anchor pool is smaller.
    triplet_target = len(summary_texts) * PER_ITEM_CAP

    pass1_attempts = pass1_failures = 0
    pass2_attempts = pass2_failures = 0

    # Pass 1 — summary coverage. Force every summary text to use=0 first,
    # while anchor and gallery use weighted bias. Guarantees 100% summary
    # coverage (the bottleneck) before pass 2 starts allowing reuse.
    while len(triplets) < triplet_target:
        pass1_attempts += 1
        if attempt(summary_strict=True):
            pass1_failures = 0
        else:
            pass1_failures += 1
            if pass1_failures >= MAX_CONSECUTIVE_FAILURES:
                break

    pass1_count = len(triplets)

    # Pass 2 — fill the rest with weighted-bias picks across all slots.
    # Theme-rare summaries that couldn't pair in pass 1 get retried with
    # less weight; the bulk of fill comes from re-using items at low use.
    while len(triplets) < triplet_target:
        pass2_attempts += 1
        if attempt(summary_strict=False):
            pass2_failures = 0
        else:
            pass2_failures += 1
            if pass2_failures >= MAX_CONSECUTIVE_FAILURES:
                break

    stats = {
        "triplets": len(triplets),
        "target": triplet_target,
        "pass1_count": pass1_count,
        "pass2_count": len(triplets) - pass1_count,
        "pass1_attempts": pass1_attempts,
        "pass2_attempts": pass2_attempts,
        "visual_day": flavor_c["visual-day"],
        "text_day": flavor_c["text-day"],
        "aligned_nocturne": sum(1 for t in triplets if "aligned_nocturne" in t),
        # Per-slot stats: one (id, slot) pair = one slot occupancy. An item
        # playing 3 different roles contributes 3 entries to `use`, not 1.
        "slot_at_cap":     sum(1 for c in use.values() if c >= PER_ITEM_CAP),
        "slot_used_once":  sum(1 for c in use.values() if c == 1),
        "slot_used_2x":    sum(1 for c in use.values() if c == 2),
        "slot_used_3x":    sum(1 for c in use.values() if c == 3),
        # Distinct items touched (across any slot) — true coverage figure.
        "distinct_items_used": len({k[0] for k in use}),
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
    print(f"\nGenerated: {stats['triplets']} of target {stats['target']} triplets")
    print(f"  pass1 (coverage):  {stats['pass1_count']}  (attempts {stats['pass1_attempts']})")
    print(f"  pass2 (fill):      {stats['pass2_count']}  (attempts {stats['pass2_attempts']})")
    print(f"  visual-day:        {stats['visual_day']}")
    print(f"  text-day:          {stats['text_day']}")
    print(f"  w/ nocturne:       {stats['aligned_nocturne']}")
    print(f"  slot-uses 1/2/3:   {stats['slot_used_once']} / {stats['slot_used_2x']} / {stats['slot_used_3x']}")
    print(f"  slots at cap:      {stats['slot_at_cap']}  (per (id,slot) pair)")
    print(f"  distinct items:    {stats['distinct_items_used']}  (touched across any slot)")
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

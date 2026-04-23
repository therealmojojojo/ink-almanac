"""corpus build-triplets — heuristic triplet generator.

Promoted from the /tmp/gen_triplets.py used during build-seed-corpus (2026-04-18).
This version enforces the **ratified** orientation rules from
`openspec/specs/corpus-triplets/spec.md` (Requirement "Image slot orientation"):

    summary slot (if image):           W ≥ H   (landscape or square)
    gallery slot (any):                any orientation
    aligned_nocturne slot:             H ≥ W   (portrait or square)

Plus all prior invariants: flavor/gallery-type consistency, panel_fidelity
native|robust on all image slots, unique slot ids within a triplet, triplet
id unique across the pool, theme overlap preferred, cross-modal pairings.

Usage:
    python3 pairing/corpus_build_triplets.py --dry             # preview only
    python3 pairing/corpus_build_triplets.py --target 300      # write to disk
    python3 pairing/corpus_build_triplets.py --target 300 --seed 42
"""
from __future__ import annotations
import argparse
import datetime
import random
import sys
from collections import Counter
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
CORPUS = REPO / "corpus"
TRIPLETS_DIR = CORPUS / "_triplets"
TAX_DIR = CORPUS / "_taxonomy"

ANCHOR_FORMS = {"haiku", "aphorism", "fragment", "quote", "song-chorus", "lyric"}

# Nocturne eligibility (post 2026-04-19 merge): an image qualifies as
# aligned-nocturne if it is portrait or square AND carries the
# `night-and-lamplight` theme. The `corpus/nocturne/` folder no longer
# exists as a separate store.
NOCTURNE_THEME = "night-and-lamplight"

# Text-zone budgets (mirror renderer/src/zones.ts + corpus_validate.py).
SUMMARY_DELIGHT_MAX_LINES = 4
SUMMARY_DELIGHT_MAX_CHARS = 24
GALLERY_MIN_TEXT_LINES = 4
GALLERY_TEXT_SHORT_EXEMPT_FORMS = {"haiku", "tanka"}


# ───────── load ─────────

def classify(doc: dict) -> str:
    if doc.get("text") or doc.get("text_variants") or doc.get("body_files"):
        return "text"
    return "image"


def orientation(w: int, h: int) -> str:
    if not (w and h):
        return "unknown"
    if w > h:
        return "landscape"
    if h > w:
        return "portrait"
    return "square"


def load_items():
    """Return dict[id] → {kind, folder, themes, form, fid, orient, is_nocturne}."""
    tax_themes = set(yaml.safe_load((TAX_DIR / "themes.yaml").read_text()).keys())
    items: dict = {}
    folders = ("images", "texts", "nocturne", "personal_library",
               "personal_library/nocturne")
    for folder in folders:
        d = CORPUS / folder
        if not d.is_dir():
            continue
        for p in sorted(d.glob("*.yaml")):
            if p.stem.startswith("EXAMPLE"):
                continue
            try:
                doc = yaml.safe_load(p.read_text())
            except Exception:
                continue
            if not isinstance(doc, dict) or "id" not in doc:
                continue
            kind = classify(doc)
            w, h = doc.get("pixel_width", 0), doc.get("pixel_height", 0)
            themes = [t for t in (doc.get("themes") or []) if t in tax_themes]
            form = doc.get("form")
            # text body → compute line count + max char width for zone fit.
            n_lines = 0
            max_chars = 0
            if kind == "text":
                body = doc.get("text") or ""
                if not body and isinstance(doc.get("text_variants"), dict):
                    body = next(iter(doc["text_variants"].values()), "")
                if body:
                    lines = [ln for ln in body.splitlines() if ln.strip()]
                    n_lines = len(lines)
                    max_chars = max((len(ln) for ln in lines), default=0)
            summary_text_ok = (kind == "text"
                                and 0 < n_lines <= SUMMARY_DELIGHT_MAX_LINES
                                and max_chars <= SUMMARY_DELIGHT_MAX_CHARS)
            gallery_text_ok = (kind == "text"
                                and (n_lines >= GALLERY_MIN_TEXT_LINES
                                     or form in GALLERY_TEXT_SHORT_EXEMPT_FORMS))
            items[doc["id"]] = {
                "id": doc["id"],
                "kind": kind,
                "folder": folder,
                "themes": themes,
                "form": form,
                "fid": doc.get("panel_fidelity"),
                "year": doc.get("year"),
                "is_nocturne_eligible": (kind == "image"
                                          and NOCTURNE_THEME in themes
                                          and orientation(w, h) in ("portrait", "square")),
                "orient": orientation(w, h) if kind == "image" else None,
                "n_lines": n_lines,
                "max_chars": max_chars,
                "summary_text_ok": summary_text_ok,
                "gallery_text_ok": gallery_text_ok,
            }
    return items, tax_themes


# ───────── helpers ─────────

def theme_overlap(a: dict, b: dict) -> set:
    return set(a["themes"]) & set(b["themes"])


def pick_with_theme(pool: list, refs: list, rng: random.Random,
                     fallback: bool = True):
    preferred = [i for i in pool if any(theme_overlap(i, r) for r in refs)]
    if preferred:
        return rng.choice(preferred)
    if fallback and pool:
        return rng.choice(pool)
    return None


def triplet_themes(anchor: dict, summary: dict, gallery: dict) -> list:
    all_themes: list = []
    seen: set = set()
    shared = set(anchor["themes"]) & (set(summary["themes"]) | set(gallery["themes"]))
    for t in shared:
        if t not in seen and len(all_themes) < 4:
            all_themes.append(t); seen.add(t)
    for item in (anchor, gallery, summary):
        for t in item["themes"]:
            if t not in seen and len(all_themes) < 3:
                all_themes.append(t); seen.add(t)
    if not all_themes and anchor["themes"]:
        all_themes = anchor["themes"][:2]
    return all_themes[:3]


NOTE_TEMPLATES_VISUAL = [
    "The poem listens; the image watches.",
    "Two ways of attending to the same quiet.",
    "Where the line ends and the shape begins.",
    "A small weight of attention held between them.",
    "The picture remembers what the poem keeps.",
    "Two takes on the same hour.",
    "A shared stillness.",
    "What the poem names, the image lets stand.",
    "The image goes first; the poem acknowledges.",
    "Quiet company.",
    "One looking; one listening.",
    "Both say: hold.",
    "Two ways of standing in a room.",
    "Shared silence.",
    "The image waits; the poem breathes through it.",
]

NOTE_TEMPLATES_TEXT = [
    "Two voices meeting at an edge.",
    "The summary image grounds; the poem carries.",
    "What the photograph saw, the poem says.",
    "A kinship of small attentions.",
    "Two paths to the same stillness.",
    "Both written under the same weather.",
    "The picture opens a door; the text walks through.",
    "A steady exchange.",
    "One ends where the other begins.",
    "The frame and the sentence hold each other up.",
    "Both made in the same key.",
    "Two observations in quiet dialogue.",
    "The image is the first word; the poem is the second.",
    "They share a posture.",
    "Each finds what the other nearly says.",
]


# ───────── generate ─────────

def build(target: int, seed: int, dry: bool, visual_share: float = 0.60,
          aligned_nocturne_share: float = 0.50) -> tuple[list, dict]:
    rng = random.Random(seed)
    items, tax_themes = load_items()

    anchor_texts = [i for i in items.values()
                    if i["kind"] == "text" and i["form"] in ANCHOR_FORMS
                    and i["themes"]]
    # Separate text pools per slot so zone budgets are respected by construction.
    summary_texts = [i for i in items.values()
                     if i["kind"] == "text" and i["themes"] and i["summary_text_ok"]]
    gallery_texts = [i for i in items.values()
                     if i["kind"] == "text" and i["themes"] and i["gallery_text_ok"]]
    # Any image usable in a day-slot: panel_fidelity native|robust, has themes.
    day_images = [i for i in items.values()
                  if i["kind"] == "image"
                  and i["fid"] in ("native", "robust")
                  and i["themes"]]

    # Orientation partitions — the ratified rules:
    #   summary (image): landscape OR square (W ≥ H)
    #   gallery (any image): any orientation
    #   aligned_nocturne: portrait OR square (H ≥ W) AND has NOCTURNE_THEME
    summary_image_pool = [i for i in day_images if i["orient"] in ("landscape", "square")]
    gallery_image_pool = day_images
    aligned_nocturne_pool = [i for i in day_images if i["is_nocturne_eligible"]]

    # ── existing triplets, so we don't duplicate ──
    existing_combos: set = set()
    existing_ids: set = set()
    for p in TRIPLETS_DIR.glob("*.yaml"):
        try:
            d = yaml.safe_load(p.read_text())
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        existing_ids.add(d.get("id", p.stem))
        existing_combos.add((d.get("anchor"), d.get("summary"), d.get("gallery")))

    stats = {
        "anchor_eligible": len(anchor_texts),
        "summary_texts": len(summary_texts),
        "gallery_texts": len(gallery_texts),
        "day_images_total": len(day_images),
        "summary_image_pool": len(summary_image_pool),
        "gallery_image_pool": len(gallery_image_pool),
        "aligned_nocturne_pool": len(aligned_nocturne_pool),
        "existing_triplets": len(existing_ids),
    }

    print(f"anchors: {stats['anchor_eligible']}")
    print(f"texts — summary-eligible (≤4 lines, ≤24 chars/line): {stats['summary_texts']}")
    print(f"texts — gallery-eligible (≥4 lines OR haiku/tanka): {stats['gallery_texts']}")
    print(f"day images: {stats['day_images_total']}  "
          f"→ summary-eligible (landscape/square): {stats['summary_image_pool']}  "
          f"(gallery-any: {stats['gallery_image_pool']})")
    print(f"aligned-nocturne pool "
          f"(night-and-lamplight + portrait/square): "
          f"{stats['aligned_nocturne_pool']}")
    print(f"existing triplets: {stats['existing_triplets']}")

    need = max(0, target - len(existing_ids))
    print(f"target {target} → need {need} new")
    if need == 0:
        return [], stats

    new_triplets: list = []
    attempts = 0
    flavor_mix = Counter()
    aligned_count = 0
    rejected_orient = 0

    while len(new_triplets) < need and attempts < need * 25:
        attempts += 1
        flavor = rng.choices(["visual-day", "text-day"],
                              weights=[visual_share, 1 - visual_share])[0]

        anchor = rng.choice(anchor_texts)

        if flavor == "visual-day":
            # gallery = image (any orientation); summary = text that fits delight_text
            gallery = pick_with_theme(gallery_image_pool, [anchor], rng)
            summary_pool = [t for t in summary_texts if t["id"] != anchor["id"]]
            summary = pick_with_theme(summary_pool, [anchor, gallery] if gallery else [anchor], rng)
        else:
            # gallery = hero text (≥4 lines OR haiku/tanka); summary = image (landscape/square)
            gallery_pool = [t for t in gallery_texts if t["id"] != anchor["id"]]
            gallery = pick_with_theme(gallery_pool, [anchor], rng)
            summary = pick_with_theme(summary_image_pool,
                                       [anchor, gallery] if gallery else [anchor], rng)

        if not (gallery and summary):
            continue

        # Defensive orientation guards (should be impossible given pool selection
        # above, but enforce to catch any logic slip).
        if summary.get("kind") == "image" and summary.get("orient") == "portrait":
            rejected_orient += 1
            continue

        if len({anchor["id"], summary["id"], gallery["id"]}) != 3:
            continue

        key = (anchor["id"], summary["id"], gallery["id"])
        if key in existing_combos:
            continue

        trip_id = f"{anchor['id'][:18]}-{summary['id'][:18]}-{gallery['id'][:18]}"
        if trip_id in existing_ids:
            continue

        aligned_id = None
        if rng.random() < aligned_nocturne_share and aligned_nocturne_pool:
            noct = pick_with_theme(aligned_nocturne_pool,
                                    [anchor, summary, gallery], rng)
            if noct and noct["id"] not in key:
                # Defensive: re-check orientation
                if noct.get("orient") in ("portrait", "square"):
                    aligned_id = noct["id"]

        themes = [t for t in triplet_themes(anchor, summary, gallery)
                  if t in tax_themes]
        if not themes:
            continue

        trip = {
            "id": trip_id,
            "anchor": anchor["id"],
            "summary": summary["id"],
            "gallery": gallery["id"],
            "flavor": flavor,
        }
        if aligned_id:
            trip["aligned_nocturne"] = aligned_id
            aligned_count += 1
        note_pool = NOTE_TEMPLATES_VISUAL if flavor == "visual-day" else NOTE_TEMPLATES_TEXT
        trip["note"] = rng.choice(note_pool)
        trip["themes"] = themes
        trip["added"] = datetime.date.today().isoformat()

        new_triplets.append(trip)
        existing_combos.add(key)
        existing_ids.add(trip_id)
        flavor_mix[flavor] += 1

    stats.update({
        "generated": len(new_triplets),
        "attempts": attempts,
        "visual_day": flavor_mix["visual-day"],
        "text_day": flavor_mix["text-day"],
        "aligned_nocturne_generated": aligned_count,
        "rejected_orientation": rejected_orient,
    })
    return new_triplets, stats


def build_exhaust(seed: int, dry: bool,
                   aligned_nocturne_share: float = 0.50) -> tuple[list, dict]:
    """Generate enough triplets so every day-image is used in ≥1 triplet
    (as gallery on visual-day, or as summary on text-day when eligible).
    Texts reuse freely; anchors and text-side slots cycle through their
    own pools theme-preferred."""
    rng = random.Random(seed)
    items, tax_themes = load_items()

    anchor_texts = [i for i in items.values()
                    if i["kind"] == "text" and i["form"] in ANCHOR_FORMS
                    and i["themes"]]
    summary_texts = [i for i in items.values()
                     if i["kind"] == "text" and i["themes"] and i["summary_text_ok"]]
    gallery_texts = [i for i in items.values()
                     if i["kind"] == "text" and i["themes"] and i["gallery_text_ok"]]
    day_images = [i for i in items.values()
                  if i["kind"] == "image"
                  and i["fid"] in ("native", "robust")
                  and i["themes"]]
    aligned_nocturne_pool = [i for i in day_images if i["is_nocturne_eligible"]]

    # Which images are already in an image slot on an existing triplet?
    used_image_ids: set = set()
    existing_combos: set = set()
    existing_ids: set = set()
    for p in TRIPLETS_DIR.glob("*.yaml"):
        try:
            d = yaml.safe_load(p.read_text())
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        existing_ids.add(d.get("id", p.stem))
        existing_combos.add((d.get("anchor"), d.get("summary"), d.get("gallery")))
        for slot in ("summary", "gallery", "aligned_nocturne"):
            v = d.get(slot)
            if v in items and items[v]["kind"] == "image":
                used_image_ids.add(v)

    # Images still unused (across day + nocturne-eligible images).
    unused_images = [i for i in day_images if i["id"] not in used_image_ids]
    print(f"day images: {len(day_images)}")
    print(f"already used: {len(used_image_ids)}")
    print(f"unused (target this run): {len(unused_images)}")
    print(f"existing triplets: {len(existing_ids)}")

    if not unused_images:
        return [], {"unused": 0, "generated": 0}

    rng.shuffle(unused_images)
    new_triplets: list = []
    flavor_mix = Counter()
    aligned_count = 0
    skipped = 0

    for img in unused_images:
        # Decide flavor: if the image is landscape/square, 50% chance it's a
        # text-day summary; otherwise visual-day gallery. Portrait images can
        # only be gallery on visual-day (summary requires landscape/square).
        can_be_summary = img["orient"] in ("landscape", "square")
        if can_be_summary and rng.random() < 0.4:
            flavor = "text-day"
        else:
            flavor = "visual-day"

        anchor = pick_with_theme(anchor_texts, [img], rng) or rng.choice(anchor_texts)

        if flavor == "visual-day":
            gallery = img
            summary_pool = [t for t in summary_texts if t["id"] != anchor["id"]]
            summary = pick_with_theme(summary_pool, [anchor, gallery], rng)
        else:
            summary = img
            gallery_pool = [t for t in gallery_texts if t["id"] != anchor["id"]]
            gallery = pick_with_theme(gallery_pool, [anchor, summary], rng)

        if not (gallery and summary):
            skipped += 1
            continue
        if len({anchor["id"], summary["id"], gallery["id"]}) != 3:
            skipped += 1
            continue

        key = (anchor["id"], summary["id"], gallery["id"])
        if key in existing_combos:
            skipped += 1
            continue

        base_id = f"{anchor['id'][:18]}-{summary['id'][:18]}-{gallery['id'][:18]}"
        # Guard against truncation collisions
        trip_id = base_id
        suffix = 2
        while trip_id in existing_ids:
            trip_id = f"{base_id}-{suffix}"
            suffix += 1

        aligned_id = None
        if rng.random() < aligned_nocturne_share and aligned_nocturne_pool:
            noct = pick_with_theme(aligned_nocturne_pool,
                                    [anchor, summary, gallery], rng)
            if noct and noct["id"] not in key and noct.get("orient") in ("portrait", "square"):
                aligned_id = noct["id"]

        themes = [t for t in triplet_themes(anchor, summary, gallery)
                  if t in tax_themes]
        if not themes:
            skipped += 1
            continue

        trip = {
            "id": trip_id,
            "anchor": anchor["id"],
            "summary": summary["id"],
            "gallery": gallery["id"],
            "flavor": flavor,
        }
        if aligned_id:
            trip["aligned_nocturne"] = aligned_id
            aligned_count += 1
        note_pool = NOTE_TEMPLATES_VISUAL if flavor == "visual-day" else NOTE_TEMPLATES_TEXT
        trip["note"] = rng.choice(note_pool)
        trip["themes"] = themes
        trip["added"] = datetime.date.today().isoformat()

        new_triplets.append(trip)
        existing_combos.add(key)
        existing_ids.add(trip_id)
        flavor_mix[flavor] += 1

    stats = {
        "unused_images": len(unused_images),
        "generated": len(new_triplets),
        "visual_day": flavor_mix["visual-day"],
        "text_day": flavor_mix["text-day"],
        "aligned_nocturne_generated": aligned_count,
        "skipped": skipped,
    }
    return new_triplets, stats


def write_triplets(triplets: list) -> int:
    TRIPLETS_DIR.mkdir(exist_ok=True)
    wrote = 0
    for t in triplets:
        p = TRIPLETS_DIR / f"{t['id']}.yaml"
        if p.exists():
            continue
        p.write_text(yaml.safe_dump(t, sort_keys=False, allow_unicode=True,
                                     default_flow_style=False))
        wrote += 1
    return wrote


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=300,
                    help="total pool size (existing + new). default 300.")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--dry", action="store_true",
                    help="preview only; do not write yaml files")
    ap.add_argument("--visual-share", type=float, default=0.60,
                    help="target share of visual-day triplets (0..1)")
    ap.add_argument("--aligned-share", type=float, default=0.50,
                    help="target share of triplets with aligned_nocturne")
    ap.add_argument("--exhaust-images", action="store_true",
                    help="keep generating until every image appears in at "
                         "least one triplet as summary or gallery. Texts "
                         "reuse freely across triplets (spec-permitted).")
    args = ap.parse_args()

    if args.exhaust_images:
        triplets, stats = build_exhaust(args.seed, args.dry,
                                         aligned_nocturne_share=args.aligned_share)
    else:
        triplets, stats = build(args.target, args.seed, args.dry,
                                  visual_share=args.visual_share,
                                  aligned_nocturne_share=args.aligned_share)

    print()
    print("── stats ──")
    for k, v in stats.items():
        print(f"  {k}: {v}")

    if args.dry:
        print("\n(dry run — no files written)")
        return

    wrote = write_triplets(triplets)
    print(f"\nwrote {wrote} triplets → {TRIPLETS_DIR}")


if __name__ == "__main__":
    main()

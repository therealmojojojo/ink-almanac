"""Shared logic: load corpus items + prepare renderer inputs from a triplet.

Used by both `corpus_review` (interactive walk) and `publish_today` (daily
cron). Keeping this in one module so the two callers can't drift on the
pairing-to-inputs mapping (companion modality, gallery flavor, nocturne
fallback, anthology haiku side-by-side, etc.).
"""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parent.parent
CORPUS = REPO / "corpus"
TRIPLETS_DIR = CORPUS / "_triplets"
RENDERER_INPUTS = REPO / "renderer" / "inputs"

SCHEMA_TEXT_FORMS = {
    "haiku", "tanka", "sonnet", "free-verse", "stanzaic",
    "fragment", "aphorism", "prose-poem", "quote",
}
IMG_EXTS = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp")


def load_yaml(p: Path) -> dict:
    return yaml.safe_load(p.read_text()) or {}


def load_items() -> dict[str, dict]:
    """All corpus items, keyed by id, annotated with `_path`, `_folder`, and
    `_binary` (when an image binary lives next to the YAML)."""
    items: dict[str, dict] = {}
    for folder in ("images", "texts", "nocturne",
                   "personal_library", "personal_library/nocturne"):
        d = CORPUS / folder
        if not d.is_dir():
            continue
        for p in d.glob("*.yaml"):
            if p.stem.startswith("EXAMPLE"):
                continue
            try:
                doc = load_yaml(p)
            except yaml.YAMLError:
                continue
            if not isinstance(doc, dict) or not doc.get("id"):
                continue
            doc["_path"] = str(p)
            doc["_folder"] = folder
            for ext in IMG_EXTS:
                bp = p.with_suffix(ext)
                if bp.exists():
                    doc["_binary"] = str(bp)
                    break
            items[doc["id"]] = doc
    return items


def load_triplets_sorted() -> list[dict]:
    """All triplets, sorted by sequence (ascending)."""
    out: list[dict] = []
    for p in sorted(TRIPLETS_DIR.glob("*.yaml")):
        try:
            d = load_yaml(p)
        except yaml.YAMLError:
            continue
        if not isinstance(d, dict) or not d.get("id"):
            continue
        d["_path"] = str(p)
        out.append(d)
    out.sort(key=lambda t: int(t.get("sequence") or 0))
    return out


def prepare_renderer_inputs(triplet: dict, items: dict[str, dict]) -> dict:
    """Write `renderer/inputs/pairing.json` + companion.jpg / gallery.jpg /
    nocturne.jpg + news.json (smart-pill body) for the given triplet.

    Returns the pairing dict written, for diagnostics."""
    summary = items.get(triplet.get("summary") or "")
    gallery = items.get(triplet.get("gallery") or "")
    nocturne = items.get(triplet.get("aligned_nocturne") or "")

    flavor_full = triplet.get("flavor", "visual-day")
    render_flavor = "visual" if flavor_full == "visual-day" else "text"

    # Render as if scheduled for today — the night face's weekday otherwise
    # drifts from the summary face's weekday.
    pairing: dict[str, Any] = {
        "date": dt.date.today().isoformat(),
        "theme": (triplet.get("themes") or ["—"])[0],
        "gallery": {"flavor": render_flavor},
    }

    # --- Summary delight (companion — opposite modality of the gallery hero) -
    if summary:
        is_summary_image = "text" not in summary and "text_variants" not in summary
        if is_summary_image and summary.get("_binary"):
            shutil.copy2(summary["_binary"], RENDERER_INPUTS / "companion.jpg")
            companion: dict[str, Any] = {
                "kind": "visual",
                "image_path": "/inputs/companion.jpg",
                "artist": summary.get("artist") or summary.get("author") or "—",
            }
            if summary.get("title"):
                companion["title"] = summary["title"]
            sy = summary.get("year")
            if sy is not None:
                companion["year"] = str(sy)
            pairing["gallery"]["companion"] = companion
        elif not is_summary_image:
            form = summary.get("form") or "fragment"
            if form not in SCHEMA_TEXT_FORMS:
                form = "fragment"
            tv = summary.get("text_variants") or {}
            langs = summary.get("language") or []
            lang_pref = "ro" if "ro" in langs else (langs[0] if langs else "en")
            body = ""
            if isinstance(tv, dict) and tv:
                body = tv.get(lang_pref) or next(iter(tv.values()))
            elif summary.get("text"):
                body = summary["text"]
            companion_text: dict[str, Any] = {
                "kind": "text",
                "form": form,
                "body": body or "(no text body)",
                "poet": summary.get("author") or "—",
                "language": "ro" if lang_pref == "ro" else "en",
            }
            if summary.get("title"):
                companion_text["title"] = summary["title"]
            if form in ("haiku", "tanka") and isinstance(tv, dict):
                ja_body = tv.get("ja")
                if ja_body and lang_pref != "ja":
                    companion_text["body_ja"] = ja_body
            pairing["gallery"]["companion"] = companion_text

    # --- Gallery slot ----------------------------------------------------
    if render_flavor == "visual" and gallery and gallery.get("_binary"):
        shutil.copy2(gallery["_binary"], RENDERER_INPUTS / "gallery.jpg")
        visual: dict[str, Any] = {
            "image_path": "/inputs/gallery.jpg",
            "title": gallery.get("title") or gallery["id"],
            "artist": gallery.get("artist") or gallery.get("author") or "",
        }
        year = gallery.get("year")
        if year is not None:
            visual["year"] = str(year)
        if gallery.get("display_title"):
            visual["display_title"] = gallery["display_title"]
        if gallery.get("display_attribution"):
            visual["display_attribution"] = gallery["display_attribution"]
        if gallery.get("pixel_width") and gallery.get("pixel_height"):
            visual["pixel_width"] = int(gallery["pixel_width"])
            visual["pixel_height"] = int(gallery["pixel_height"])
        pairing["gallery"]["visual"] = visual
    elif render_flavor == "text" and gallery:
        form = gallery.get("form") or "fragment"
        if form not in SCHEMA_TEXT_FORMS:
            form = "fragment"
        body = ""
        tv = gallery.get("text_variants") or {}
        langs = gallery.get("language") or []
        lang_pref = "ro" if "ro" in langs else (langs[0] if langs else "en")
        if isinstance(tv, dict) and tv:
            body = tv.get(lang_pref) or next(iter(tv.values()))
        elif gallery.get("text"):
            body = gallery["text"]
        language = "ro" if lang_pref == "ro" else "en"
        pairing["gallery"]["text"] = {
            "form": form,
            "body": body or "(no text body)",
            "poet": gallery.get("author") or "",
            "language": language,
        }
        if gallery.get("title"):
            pairing["gallery"]["text"]["title"] = gallery["title"]
        if form in ("haiku", "tanka") and isinstance(tv, dict):
            ja_body = tv.get("ja")
            if ja_body and lang_pref != "ja":
                pairing["gallery"]["text"]["body_ja"] = ja_body

    # --- Night slot (aligned nocturne, or deterministic fallback by id-hash) -
    night_item = nocturne if (nocturne and nocturne.get("_binary")) else None
    if night_item is None:
        def _portrait_or_square(it: dict) -> bool:
            pw, ph = it.get("pixel_width"), it.get("pixel_height")
            return bool(pw and ph and int(ph) >= int(pw))

        def _is_image(it: dict) -> bool:
            return not ("text" in it or "text_variants" in it)

        pool = [
            it for it in items.values()
            if it.get("_binary")
            and _is_image(it)
            and "night-and-lamplight" in (it.get("themes") or [])
            and _portrait_or_square(it)
        ]
        if pool:
            pool.sort(key=lambda it: it["id"])
            tid = triplet.get("id", "")
            idx = int(hashlib.sha1(tid.encode("utf-8")).hexdigest(), 16) % len(pool)
            night_item = pool[idx]

    if night_item and night_item.get("_binary"):
        shutil.copy2(night_item["_binary"], RENDERER_INPUTS / "nocturne.jpg")
        artist = (night_item.get("artist") or night_item.get("author") or "").upper()
        year = night_item.get("year")
        parts = []
        if artist:
            parts.append(artist)
        if year is not None:
            parts.append(str(year))
        pairing["night"] = {
            "image_path": "/inputs/nocturne.jpg",
            "title": night_item.get("title") or "",
            "fragment": " · ".join(parts) if parts else "—",
        }
    else:
        pairing["night"] = {}

    (RENDERER_INPUTS / "pairing.json").write_text(
        json.dumps(pairing, indent=2, ensure_ascii=False) + "\n")

    # --- Smart pill body (from summary item's YAML sidecar) --------------
    sp_body = ""
    if summary and isinstance(summary.get("smart_pill"), dict):
        sp_body = (summary["smart_pill"].get("body") or "").strip()
    news = {"count": 1, "items": [{"body": sp_body}]} if sp_body else {"count": 0, "items": []}
    (RENDERER_INPUTS / "news.json").write_text(
        json.dumps(news, indent=2, ensure_ascii=False) + "\n")

    return pairing

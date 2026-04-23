"""corpus validate - first-pass validator for the Inkplate corpus.

Standalone script; run from repo root:

    python3 pairing/corpus_validate.py

Checks:
  - sidecar required fields and types
  - tags (themes / mood / register / form) are in the taxonomy
  - tier/folder consistency (personal_library items under personal_library/, etc.)
  - image items carry pixel_width, pixel_height, panel_fidelity
  - panel_fidelity not 'color-dependent'
  - image short-edge >= 1200 (resolution floor)
  - file pairings: sidecar has a matching binary where required
  - triplet refs point to existing items, anchor is anchor-eligible,
    flavor matches gallery type, no slot duplication, image slots are
    native or robust panel_fidelity
  - manifest / filesystem consistency (each binary has a manifest entry
    and vice versa; sha256 check is OFF by default - pass --full to enable)

This is scope (b) from the session plan: the validation layer only.
Fetch/propose/prune/restore are separate work under `add-corpus-ingestion`.
"""

from __future__ import annotations
import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    sys.exit("corpus_validate requires PyYAML. Install: pip install pyyaml")


REPO_ROOT = Path(__file__).resolve().parent.parent
CORPUS = REPO_ROOT / "corpus"
TAXONOMY_DIR = CORPUS / "_taxonomy"
TRIPLETS_DIR = CORPUS / "_triplets"
MANIFEST = CORPUS / "_manifest.json"

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}
IMAGE_TIERS = {"public_domain", "cc0", "personal_library"}
PANEL_FIDELITY_OK = {"native", "robust"}
# Summary face's delight_text zone budget (mirror renderer/src/zones.ts).
# If this file drifts from the renderer, the authoring and runtime contracts
# split silently. Keep the two in sync when the zone is retuned.
SUMMARY_DELIGHT_MAX_LINES = 4
SUMMARY_DELIGHT_MAX_CHARS = 24
# Gallery-text form → (maxChars, maxLines). Mirrors renderer/src/zones.ts
# plus the form→zone mapping in renderer/src/modes/gallery.ts.
GALLERY_TEXT_BUDGET = {
    "haiku":      (24, 3),
    "tanka":      (24, 3),
    "sonnet":     (64, 32),
    "free-verse": (64, 32),
    "stanzaic":   (64, 32),
    "fragment":   (64, 32),
    "prose-poem": (64, 32),
    "aphorism":   (48, 6),
    "quote":      (56, 10),
}
# Practical vertical-fit cap for forms that flow into poem_body. The
# multi-column flow caps at 2 columns × 8 lines/col = 16 lines; past this,
# content overflows vertically on the gallery face even though it's within
# the hard maxLines budget.
POEM_BODY_SOFT_LINE_CAP = 16
POEM_BODY_FORMS = {"sonnet", "free-verse", "stanzaic", "fragment", "prose-poem"}
# Gallery hero-density rule: short texts (≤ 3 lines) are too sparse for the
# gallery face's hero zones and belong in the Summary face's delight_text
# zone instead. Haiku and tanka are exempt — the 3-line form is canonical
# and the gallery has a dedicated haiku_body zone sized for exactly that.
GALLERY_MIN_TEXT_LINES = 4  # strict inequality: lines >= 4 OR haiku/tanka
GALLERY_TEXT_SHORT_EXEMPT_FORMS = {"haiku", "tanka"}
SHORT_EDGE_FLOOR = 1200         # legacy cover-mode floor (kept for reference)
LONG_EDGE_PREFERRED = 1800
# Orientation-aware floors: under matted display, only the fill-axis needs to
# meet panel resolution. Landscape images fill width; portrait/square fill height
# (on a landscape panel, pillarboxed). Mat inset ~60px, so effective image box
# ~1080x693 in panel-native orientation.
FILL_AXIS_LANDSCAPE = 1080      # width requirement for landscape images
FILL_AXIS_PORTRAIT = 693        # height requirement for portrait/square images

# Forms considered anchor-eligible for triplets (from form.yaml anchor_eligible
# flag; also enumerated here defensively).
ANCHOR_ELIGIBLE_FORMS = {"haiku", "fragment", "aphorism", "quote", "song-chorus", "lyric"}


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def err(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def summarize(self) -> int:
        print(f"\n  errors:   {len(self.errors)}")
        print(f"  warnings: {len(self.warnings)}")
        if self.errors:
            print("\n--- ERRORS ---")
            for e in self.errors:
                print(f"  {e}")
        if self.warnings:
            print("\n--- WARNINGS ---")
            for w in self.warnings:
                print(f"  {w}")
        return 1 if self.errors else 0


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open() as f:
        return yaml.safe_load(f) or {}


def load_taxonomy() -> dict[str, set[str]]:
    out = {}
    for name in ("themes", "mood", "register", "form"):
        p = TAXONOMY_DIR / f"{name}.yaml"
        if not p.exists():
            out[name] = set()  # caller sees empty set; per-item tag checks will flag
            continue
        data = load_yaml(p)
        out[name] = set(data.keys()) if isinstance(data, dict) else set()
    return out


def is_image_item(sidecar: Path, tier: str) -> bool:
    """Sidecar belongs to image pool if it lives in images/, nocturne/, or
    personal_library/ (top or nested nocturne/) AND has no text fields."""
    rel = sidecar.relative_to(CORPUS).parts
    if rel[0] == "texts":
        return False
    if rel[0] == "personal_library":
        # Could be image or text — disambiguate by presence of `artist` field.
        return True  # classified at field-check time
    return rel[0] in {"images", "nocturne"}


def validate_sidecar(path: Path, tax: dict[str, set[str]], report: Report, known_ids: set[str]) -> None:
    try:
        doc = load_yaml(path)
    except yaml.YAMLError as e:
        report.err(f"{path}: YAML parse failure: {e}")
        return

    if not isinstance(doc, dict):
        report.err(f"{path}: top-level is not a mapping")
        return

    basename = path.stem

    # Required common fields
    for k in ("id", "title", "year", "rights_tier", "source", "form", "themes", "mood", "register", "added"):
        if k not in doc:
            report.err(f"{path}: missing required field `{k}`")

    _id = doc.get("id")
    if _id != basename:
        report.err(f"{path}: `id` ({_id!r}) must match basename ({basename!r})")
    if _id in known_ids:
        report.err(f"{path}: duplicate id {_id!r}")
    elif _id:
        known_ids.add(_id)

    tier = doc.get("rights_tier")
    if tier and tier not in IMAGE_TIERS:
        report.err(f"{path}: rights_tier must be public_domain|cc0|personal_library, got {tier!r}")

    # tier/folder consistency
    rel = path.relative_to(CORPUS).parts
    top = rel[0]
    if tier == "personal_library" and top not in {"personal_library"}:
        report.err(f"{path}: personal_library item must live under corpus/personal_library/")
    if tier in {"public_domain", "cc0"}:
        if top == "personal_library":
            report.err(f"{path}: PD/CC0 item should not live under corpus/personal_library/")

    # Source URL / citation
    source_url = doc.get("source_url")
    if tier in {"public_domain", "cc0"} and not source_url:
        report.err(f"{path}: source_url required for {tier}")
    if tier == "personal_library" and not doc.get("citation"):
        report.err(f"{path}: citation required for personal_library")

    # Taxonomy membership
    for key in ("themes", "mood", "register"):
        vals = doc.get(key)
        if vals is None:
            continue
        if not isinstance(vals, list) or len(vals) == 0:
            report.err(f"{path}: `{key}` must be a non-empty list")
            continue
        for v in vals:
            if v not in tax[key]:
                report.err(f"{path}: `{key}` value {v!r} not in taxonomy")

    form = doc.get("form")
    if form is not None and form not in tax["form"]:
        report.err(f"{path}: `form` {form!r} not in taxonomy")

    # Work-type dispatch
    #  - if `artist` present -> image item
    #  - if `author` present -> text item
    is_image = "artist" in doc or (top in {"images", "nocturne"})
    is_text = "author" in doc or top == "texts"
    if is_image and is_text:
        report.err(f"{path}: carries both artist (image) and author (text)")
        return
    if is_image:
        validate_image(path, doc, report)
    elif is_text:
        validate_text(path, doc, report)
    else:
        report.err(f"{path}: cannot classify as image or text (no artist/author)")


def validate_image(path: Path, doc: dict[str, Any], report: Report) -> None:
    for k in ("artist", "medium", "pixel_width", "pixel_height", "panel_fidelity"):
        if k not in doc:
            report.err(f"{path}: image item missing `{k}`")

    # Visual-review verdict (optional). `reject` is a hard fail; `flag` is a warning.
    verdict = doc.get("panel_verdict")
    reason = doc.get("verdict_reason", "")
    if verdict == "reject":
        report.err(f"{path}: panel_verdict=reject — {reason}")
    elif verdict == "flag":
        report.warn(f"{path}: panel_verdict=flag — {reason}")
    elif verdict is not None and verdict not in ("keep",):
        report.err(f"{path}: panel_verdict must be keep|flag|reject, got {verdict!r}")

    pf = doc.get("panel_fidelity")
    if pf == "color-dependent":
        report.err(f"{path}: panel_fidelity `color-dependent` not allowed (drop or reclassify)")
    elif pf is not None and pf not in PANEL_FIDELITY_OK:
        report.err(f"{path}: panel_fidelity must be native|robust (or color-dependent which is rejected), got {pf!r}")

    w = doc.get("pixel_width")
    h = doc.get("pixel_height")
    if isinstance(w, int) and isinstance(h, int) and w > 0 and h > 0:
        # Orientation-aware fill-axis floor (matched to renderer's matted display).
        is_landscape = w > h
        fill_axis = w if is_landscape else h
        required = FILL_AXIS_LANDSCAPE if is_landscape else FILL_AXIS_PORTRAIT
        orient = "landscape" if is_landscape else ("portrait" if h > w else "square")
        if fill_axis < required:
            report.err(f"{path}: {orient} fill-axis {fill_axis} < {required} (dims {w}x{h})")
        elif max(w, h) < LONG_EDGE_PREFERRED:
            report.warn(f"{path}: long edge {max(w, h)} < {LONG_EDGE_PREFERRED} preferred (dims {w}x{h})")

    # Sidecar-binary pairing: expect a file with same basename and an image extension
    binary = find_binary(path)
    if binary is None:
        report.err(f"{path}: no image binary found with matching basename (expected .jpg/.png/etc.)")


def validate_text(path: Path, doc: dict[str, Any], report: Report) -> None:
    if "author" not in doc:
        report.err(f"{path}: text item missing `author`")
    has_text = "text" in doc
    has_variants = "text_variants" in doc
    has_bodyfiles = "body_files" in doc
    if sum(map(bool, [has_text, has_variants, has_bodyfiles])) == 0:
        report.err(f"{path}: text item requires one of `text`, `text_variants`, or `body_files`")
    if has_text and has_variants:
        report.err(f"{path}: specify either `text` or `text_variants`, not both")
    lang = doc.get("language")
    if lang is None or not isinstance(lang, list) or len(lang) == 0:
        report.err(f"{path}: text item requires `language` as non-empty list")

    # Zone-fit: a text item SHALL fit its form's gallery-text zone budget.
    # Overflow items cannot be used as gallery slots without VERSE_OVERFLOW
    # at render time, so ingestion rejects them outright.
    form = doc.get("form")
    if form is not None and form not in GALLERY_TEXT_BUDGET:
        report.err(f"{path}: text item has form {form!r} outside the gallery-text taxonomy {sorted(GALLERY_TEXT_BUDGET)}")
        return
    if form is None:
        return  # missing-form is flagged by the schema layer
    body = None
    tv = doc.get("text_variants") or {}
    if isinstance(tv, dict) and tv:
        body = next(iter(tv.values()))
    elif doc.get("text"):
        body = doc["text"]
    if not body:
        return  # body_files path — body-fit check runs after body hydration
    mc, ml = GALLERY_TEXT_BUDGET[form]
    lines = str(body).strip().split("\n")
    n_lines = len(lines)
    max_line = max((len(l) for l in lines), default=0)
    if n_lines > ml or max_line > mc:
        report.err(
            f"{path}: text body overflows {form} zone budget "
            f"({n_lines} lines, max line {max_line} chars; budget {ml} lines / {mc} chars per line)"
        )
    elif form in POEM_BODY_FORMS and n_lines > POEM_BODY_SOFT_LINE_CAP:
        report.err(
            f"{path}: text body exceeds practical 2-column cap "
            f"({n_lines} lines > {POEM_BODY_SOFT_LINE_CAP}; fits hard budget {ml} but overflows vertically on gallery face)"
        )


def find_binary(sidecar: Path) -> Path | None:
    for ext in IMAGE_EXTS:
        cand = sidecar.with_suffix(ext)
        if cand.exists():
            return cand
    return None


def validate_triplets(tax: dict[str, set[str]], items_by_id: dict[str, dict], report: Report) -> None:
    if not TRIPLETS_DIR.exists():
        return
    seen_ids: set[str] = set()
    for path in sorted(TRIPLETS_DIR.glob("*.yaml")):
        try:
            doc = load_yaml(path)
        except yaml.YAMLError as e:
            report.err(f"{path}: triplet YAML parse failure: {e}")
            continue
        basename = path.stem
        # Rejected triplets remain in the repo as a record but are excluded
        # from the active pool. Integrity checks (refs, forms, orientation,
        # panel-fidelity, zone fit) are skipped for them — they will never
        # render, so dangling data doesn't matter.
        if doc.get("triplet_verdict") in ("reject-content", "reject-layout"):
            continue
        for k in ("id", "anchor", "summary", "gallery", "flavor", "note", "themes", "added"):
            if k not in doc:
                report.err(f"{path}: triplet missing `{k}`")
        tid = doc.get("id")
        if tid != basename:
            report.err(f"{path}: triplet id {tid!r} != basename {basename!r}")
        if tid in seen_ids:
            report.err(f"{path}: duplicate triplet id")
        elif tid:
            seen_ids.add(tid)

        # Refs to items
        anchor = doc.get("anchor")
        summary = doc.get("summary")
        gallery = doc.get("gallery")
        flavor = doc.get("flavor")
        noct = doc.get("aligned_nocturne")
        for slot_name, ref in [("anchor", anchor), ("summary", summary), ("gallery", gallery)]:
            if ref is not None and ref not in items_by_id:
                report.err(f"{path}: triplet `{slot_name}` references unknown item {ref!r}")
        if noct is not None and noct not in items_by_id:
            report.err(f"{path}: triplet `aligned_nocturne` references unknown item {noct!r}")

        # Anchor form eligibility
        if anchor and anchor in items_by_id:
            form = items_by_id[anchor].get("form")
            if form not in ANCHOR_ELIGIBLE_FORMS:
                report.err(f"{path}: anchor {anchor!r} form {form!r} is not anchor-eligible")

        # Flavor / gallery-type consistency
        if gallery in items_by_id:
            g = items_by_id[gallery]
            is_img = "artist" in g
            if flavor == "visual-day" and not is_img:
                report.err(f"{path}: visual-day gallery must be image; {gallery!r} is text")
            if flavor == "text-day" and is_img:
                report.err(f"{path}: text-day gallery must be text; {gallery!r} is image")
            # Gallery hero-density: a text gallery SHALL have ≥ 4 body lines
            # unless it's a haiku/tanka. Short texts belong in summary.
            if flavor == "text-day" and not is_img:
                body = None
                tv = g.get("text_variants") or {}
                if isinstance(tv, dict) and tv:
                    body = next(iter(tv.values()))
                elif g.get("text"):
                    body = g["text"]
                if body:
                    n = len(str(body).strip().split("\n"))
                    form = g.get("form")
                    if n < GALLERY_MIN_TEXT_LINES and form not in GALLERY_TEXT_SHORT_EXEMPT_FORMS:
                        report.err(
                            f"{path}: gallery slot -> {gallery!r} is too short for hero zone "
                            f"({n} lines, form={form!r}); short texts (< {GALLERY_MIN_TEXT_LINES} lines) "
                            f"belong in the summary slot, not gallery (haiku/tanka are exempt)"
                        )

        # Panel-fidelity on image slots (gallery if visual-day, summary if image, aligned_nocturne)
        for slot_name, ref in [("gallery" if flavor == "visual-day" else None, gallery),
                               ("summary", summary),
                               ("aligned_nocturne", noct)]:
            if slot_name is None or ref is None or ref not in items_by_id:
                continue
            item = items_by_id[ref]
            if "artist" not in item:
                continue  # text slot, not bound by panel_fidelity
            pf = item.get("panel_fidelity")
            if pf not in PANEL_FIDELITY_OK:
                report.err(f"{path}: image slot `{slot_name}` -> {ref!r} has panel_fidelity {pf!r}, must be native|robust")
            # Block rejected images from being used as triplet slots
            if item.get("panel_verdict") == "reject":
                report.err(f"{path}: image slot `{slot_name}` -> {ref!r} has panel_verdict=reject")
            # Orientation rule per image slot (see corpus-triplets
            # "Image slot orientation"):
            #   summary  — landscape/square (W >= H); reject portrait
            #   nocturne — portrait/square (H >= W); reject landscape
            #   gallery  — any
            if slot_name in ("summary", "aligned_nocturne"):
                pw, ph = item.get("pixel_width"), item.get("pixel_height")
                if isinstance(pw, int) and isinstance(ph, int):
                    if slot_name == "summary" and ph > pw:
                        report.err(f"{path}: summary slot -> {ref!r} is portrait ({pw}x{ph}); summary requires landscape/square")
                    elif slot_name == "aligned_nocturne" and pw > ph:
                        report.err(f"{path}: aligned_nocturne slot -> {ref!r} is landscape ({pw}x{ph}); aligned_nocturne requires portrait/square")

        # Text fit on the Summary face's delight_text zone: a text summary
        # slot SHALL fit the zone budget (see renderer/src/zones.ts).
        # Overflow causes VERSE_OVERFLOW at render time and a failed face.
        if summary and summary in items_by_id:
            item = items_by_id[summary]
            body = None
            tv = item.get("text_variants") or {}
            if isinstance(tv, dict) and tv:
                body = next(iter(tv.values()))
            elif item.get("text"):
                body = item["text"]
            if body:
                lines = str(body).strip().split("\n")
                max_line_chars = max((len(l) for l in lines), default=0)
                if len(lines) > SUMMARY_DELIGHT_MAX_LINES or max_line_chars > SUMMARY_DELIGHT_MAX_CHARS:
                    report.err(
                        f"{path}: summary slot -> {summary!r} text overflows delight_text budget "
                        f"({len(lines)} lines, max line {max_line_chars} chars; "
                        f"budget {SUMMARY_DELIGHT_MAX_LINES} lines / {SUMMARY_DELIGHT_MAX_CHARS} chars per line)"
                    )

        # Slot duplication
        slots = [s for s in [anchor, summary, gallery, noct] if s]
        if len(set(slots)) != len(slots):
            report.err(f"{path}: duplicate slot assignment {slots}")

        # Themes
        themes = doc.get("themes") or []
        if not isinstance(themes, list) or len(themes) == 0:
            report.err(f"{path}: triplet `themes` must be non-empty list")
        else:
            for t in themes:
                if t not in tax["themes"]:
                    report.err(f"{path}: triplet theme {t!r} not in taxonomy")


def validate_manifest(report: Report, full: bool) -> None:
    if not MANIFEST.exists():
        report.warn(f"{MANIFEST}: missing; skipping manifest checks")
        return
    try:
        m = json.loads(MANIFEST.read_text())
    except json.JSONDecodeError as e:
        report.err(f"{MANIFEST}: invalid JSON: {e}")
        return
    entries = m.get("entries", [])
    manifest_paths = {e["path"] for e in entries if "path" in e}

    # Every image binary on disk should have a manifest entry
    on_disk = set()
    for sub in ("images", "nocturne", "personal_library", "personal_library/nocturne"):
        d = CORPUS / sub
        if not d.exists():
            continue
        for f in d.iterdir():
            if f.is_file() and f.suffix.lower() in IMAGE_EXTS:
                on_disk.add(f"corpus/{sub}/{f.name}")
    missing_in_manifest = on_disk - manifest_paths
    for p in sorted(missing_in_manifest):
        report.err(f"manifest: on-disk binary `{p}` has no manifest entry")
    missing_on_disk = manifest_paths - on_disk
    for p in sorted(missing_on_disk):
        report.err(f"manifest: entry `{p}` points to a file not on disk")

    if full:
        for e in entries:
            p = REPO_ROOT / e["path"]
            if not p.exists():
                continue  # already reported
            h = hashlib.sha256(p.read_bytes()).hexdigest()
            if h != e.get("sha256"):
                report.err(f"manifest: sha256 mismatch for {e['path']}")


def iter_sidecars():
    for sub in ("images", "texts", "nocturne", "personal_library", "personal_library/nocturne"):
        d = CORPUS / sub
        if not d.exists():
            continue
        for f in sorted(d.glob("*.yaml")):
            yield f


def main():
    ap = argparse.ArgumentParser(description="Validate the Inkplate corpus.")
    ap.add_argument("--full", action="store_true", help="Enable sha256 verification of manifest entries (slow).")
    args = ap.parse_args()

    report = Report()
    tax = load_taxonomy()
    for name in ("themes", "mood", "register", "form"):
        if not tax[name]:
            report.warn(f"taxonomy/{name}.yaml is empty or missing")

    # Pass 1: parse every sidecar, collect by id for triplet refs
    items_by_id: dict[str, dict] = {}
    known_ids: set[str] = set()
    sidecars = list(iter_sidecars())
    for p in sidecars:
        validate_sidecar(p, tax, report, known_ids)
        try:
            doc = load_yaml(p)
            if isinstance(doc, dict) and doc.get("id"):
                items_by_id[doc["id"]] = doc
        except yaml.YAMLError:
            pass

    # Pass 2: triplets
    validate_triplets(tax, items_by_id, report)

    # Pass 3: manifest <-> filesystem
    validate_manifest(report, args.full)

    print(f"\nscanned {len(sidecars)} sidecars, "
          f"{len(list(TRIPLETS_DIR.glob('*.yaml')) if TRIPLETS_DIR.exists() else [])} triplets, "
          f"{len(items_by_id)} items in pool")
    sys.exit(report.summarize())


if __name__ == "__main__":
    main()

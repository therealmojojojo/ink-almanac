"""corpus audit — read-only inventory & gate-status report for the Inkplate corpus.

Standalone, single file, one dependency (PyYAML), like corpus_validate.py.

Reports:
  - Totals per folder and per rights tier
  - Theme, mood, register, form histograms (each side: image / text)
  - Theme coverage (how many items per theme on each side; flags < 15 floor)
  - Language distribution across text items (flags Romanian share < 25%)
  - Nocturne pool size (flags < 30 floor)
  - Panel-fidelity distribution + panel_verdict distribution
  - Resolution status (orientation-aware: landscape ≥ 1080, portrait ≥ 693)
  - Progress toward 300+300 and outstanding floors

Run from repo root:

    python3 pairing/corpus_audit.py
    python3 pairing/corpus_audit.py --out corpus/_audits/audit-YYYY-MM-DD.md
    python3 pairing/corpus_audit.py --format json

Exit code is always 0; audits report state, they don't fail. Use `corpus_validate.py`
to fail the build on invariant violations.
"""

from __future__ import annotations
import argparse
import datetime as dt
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    sys.exit("corpus_audit requires PyYAML. Install: pip install pyyaml")


REPO_ROOT = Path(__file__).resolve().parent.parent
CORPUS = REPO_ROOT / "corpus"
TAXONOMY_DIR = CORPUS / "_taxonomy"

# Floors per openspec/changes/build-seed-corpus/specs/corpus-seed/spec.md
THEME_FLOOR_PER_SIDE = 10
ROMANIAN_SHARE_FLOOR = 0.25
NOCTURNE_FLOOR = 30
SEED_TARGET_PER_SIDE = 200
ANCHOR_ELIGIBLE_FLOOR = 80
BW_PHOTO_SHARE_FLOOR = 0.50
TRIPLET_POOL_FLOOR = 300
ALIGNED_NOCTURNE_FLOOR = 0.40
FILL_AXIS_LANDSCAPE = 1080
FILL_AXIS_PORTRAIT = 693
LONG_EDGE_PREFERRED = 1800

SIDEBARS = {
    "images": "image",
    "nocturne": "image",
    "personal_library": "mixed",
    "personal_library/nocturne": "image",
    "texts": "text",
}
TEMPLATE_STEMS = {"EXAMPLE", "EXAMPLE-BILINGUAL"}


@dataclass
class Item:
    path: Path
    folder: str              # top-level folder under corpus/
    kind: str                # "image" | "text"
    doc: dict[str, Any]

    @property
    def tier(self) -> str:
        return self.doc.get("rights_tier") or "unknown"

    @property
    def is_nocturne(self) -> bool:
        return self.folder.endswith("nocturne") or self.folder == "nocturne"


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open() as f:
        return yaml.safe_load(f) or {}


def classify_kind(folder: str, doc: dict[str, Any]) -> str:
    """Items under personal_library/ can be image or text — disambiguate by field."""
    if folder == "personal_library" and ("text" in doc or "text_variants" in doc):
        return "text"
    if SIDEBARS.get(folder) == "text":
        return "text"
    return "image"


def iter_sidecars() -> list[Item]:
    items: list[Item] = []
    folders = [
        ("images", CORPUS / "images"),
        ("texts", CORPUS / "texts"),
        ("nocturne", CORPUS / "nocturne"),
        ("personal_library", CORPUS / "personal_library"),
        ("personal_library/nocturne", CORPUS / "personal_library" / "nocturne"),
    ]
    for folder, d in folders:
        if not d.is_dir():
            continue
        for p in sorted(d.glob("*.yaml")):
            if p.stem in TEMPLATE_STEMS:
                continue
            try:
                doc = load_yaml(p)
            except yaml.YAMLError:
                continue
            if not isinstance(doc, dict):
                continue
            items.append(Item(path=p, folder=folder, kind=classify_kind(folder, doc), doc=doc))
    return items


def load_taxonomy() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for name in ("themes", "mood", "register", "form"):
        p = TAXONOMY_DIR / f"{name}.yaml"
        if not p.exists():
            out[name] = []
            continue
        data = load_yaml(p)
        out[name] = list(data.keys()) if isinstance(data, dict) else []
    return out


def histogram(items: list[Item], field_name: str) -> Counter:
    h: Counter = Counter()
    for it in items:
        v = it.doc.get(field_name)
        if isinstance(v, list):
            for x in v:
                h[str(x)] += 1
        elif v is not None:
            h[str(v)] += 1
    return h


def coverage_by_side(items: list[Item], taxonomy_terms: list[str]) -> dict[str, dict[str, int]]:
    """Per-theme counts split into image-side and text-side."""
    cov: dict[str, dict[str, int]] = {t: {"image": 0, "text": 0} for t in taxonomy_terms}
    for it in items:
        themes = it.doc.get("themes") or []
        if not isinstance(themes, list):
            continue
        side = "image" if it.kind == "image" else "text"
        for t in themes:
            if t in cov:
                cov[t][side] += 1
            else:
                cov.setdefault(t, {"image": 0, "text": 0})[side] += 1
    return cov


def resolution_status(items: list[Item]) -> dict[str, Any]:
    below_floor: list[str] = []
    below_long_edge: list[str] = []
    missing_dims: list[str] = []
    for it in items:
        if it.kind != "image":
            continue
        w = it.doc.get("pixel_width")
        h = it.doc.get("pixel_height")
        if not isinstance(w, int) or not isinstance(h, int) or w <= 0 or h <= 0:
            missing_dims.append(it.doc.get("id") or it.path.stem)
            continue
        if w > h:
            if w < FILL_AXIS_LANDSCAPE:
                below_floor.append(f"{it.doc.get('id')} (landscape {w}x{h}, fill {w} < {FILL_AXIS_LANDSCAPE})")
        else:
            if h < FILL_AXIS_PORTRAIT:
                below_floor.append(f"{it.doc.get('id')} (portrait {w}x{h}, fill {h} < {FILL_AXIS_PORTRAIT})")
        if max(w, h) < LONG_EDGE_PREFERRED:
            below_long_edge.append(f"{it.doc.get('id')} ({w}x{h})")
    return {
        "below_floor": below_floor,
        "below_long_edge": below_long_edge,
        "missing_dims": missing_dims,
    }


def romanian_share(items: list[Item]) -> tuple[int, int]:
    text_items = [i for i in items if i.kind == "text"]
    ro = 0
    for it in text_items:
        langs = it.doc.get("language") or []
        if isinstance(langs, list) and any(str(l).lower().startswith("ro") for l in langs):
            ro += 1
    return ro, len(text_items)


def panel_fidelity_distribution(items: list[Item]) -> Counter:
    h: Counter = Counter()
    for it in items:
        if it.kind != "image":
            continue
        h[str(it.doc.get("panel_fidelity") or "absent")] += 1
    return h


def panel_verdict_distribution(items: list[Item]) -> Counter:
    h: Counter = Counter()
    for it in items:
        if it.kind != "image":
            continue
        h[str(it.doc.get("panel_verdict") or "absent")] += 1
    return h


def format_md(items: list[Item], taxonomy: dict[str, list[str]]) -> str:
    today = dt.date.today().isoformat()
    images = [i for i in items if i.kind == "image"]
    texts = [i for i in items if i.kind == "text"]
    nocturne = [i for i in items if i.is_nocturne and i.kind == "image"]

    ro, texts_total = romanian_share(items)
    ro_pct = (ro / texts_total * 100) if texts_total else 0.0
    res = resolution_status(items)
    pf = panel_fidelity_distribution(items)
    pv = panel_verdict_distribution(items)
    cov = coverage_by_side(items, taxonomy["themes"])

    lines: list[str] = []
    lines.append(f"# Corpus audit — {today}")
    lines.append("")
    lines.append(f"Total sidecars: **{len(items)}** (images: {len(images)}, texts: {len(texts)})")
    lines.append("")

    # Folder / tier breakdown
    by_folder: Counter = Counter()
    by_tier_folder: dict[str, Counter] = defaultdict(Counter)
    for it in items:
        by_folder[it.folder] += 1
        by_tier_folder[it.folder][it.tier] += 1
    lines.append("## Folder × tier")
    lines.append("")
    lines.append("| folder | total | public_domain | cc0 | personal_library | other |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for folder in ("images", "texts", "nocturne", "personal_library", "personal_library/nocturne"):
        if folder not in by_folder:
            continue
        c = by_tier_folder[folder]
        other = sum(v for k, v in c.items() if k not in ("public_domain", "cc0", "personal_library"))
        lines.append(
            f"| `{folder}` | {by_folder[folder]} "
            f"| {c.get('public_domain', 0)} | {c.get('cc0', 0)} "
            f"| {c.get('personal_library', 0)} | {other} |"
        )
    lines.append("")

    # Gate tracking
    lines.append("## Gate tracking")
    lines.append("")
    lines.append("| Gate | State | Status |")
    lines.append("|---|---|---|")
    image_total = len(images)
    text_total = len(texts)
    lines.append(f"| Item pool ≥ {SEED_TARGET_PER_SIDE} + {SEED_TARGET_PER_SIDE} (image + text) | {image_total} + {text_total} | "
                 f"{'✅' if image_total >= SEED_TARGET_PER_SIDE and text_total >= SEED_TARGET_PER_SIDE else '❌'} |")
    lines.append(f"| Romanian text share ≥ {ROMANIAN_SHARE_FLOOR:.0%} | "
                 f"{ro}/{texts_total} = {ro_pct:.1f}% | "
                 f"{'✅' if ro_pct >= ROMANIAN_SHARE_FLOOR * 100 else '❌'} |")
    lines.append(f"| Nocturne pool ≥ {NOCTURNE_FLOOR} | {len(nocturne)} | "
                 f"{'✅' if len(nocturne) >= NOCTURNE_FLOOR else '❌'} |")
    pv_reject = pv.get("reject", 0)
    lines.append(f"| Zero panel_verdict=reject | {pv_reject} | "
                 f"{'✅' if pv_reject == 0 else '❌'} |")
    lines.append(f"| Zero images below resolution floor | {len(res['below_floor'])} | "
                 f"{'✅' if not res['below_floor'] else '❌'} |")
    lines.append("")

    # Theme coverage
    lines.append("## Theme coverage by side")
    lines.append("")
    lines.append(f"Floor per side per theme: **{THEME_FLOOR_PER_SIDE}**. Themes listed in order of total presence.")
    lines.append("")
    lines.append("| theme | image | text | total | status |")
    lines.append("|---|---:|---:|---:|---|")
    sorted_themes = sorted(cov.items(), key=lambda kv: -(kv[1]["image"] + kv[1]["text"]))
    for theme, counts in sorted_themes:
        total = counts["image"] + counts["text"]
        img_ok = counts["image"] >= THEME_FLOOR_PER_SIDE
        txt_ok = counts["text"] >= THEME_FLOOR_PER_SIDE
        status = "✅" if (img_ok and txt_ok) else "⚠️" if total > 0 else "∅"
        lines.append(f"| `{theme}` | {counts['image']} | {counts['text']} | {total} | {status} |")
    lines.append("")

    # Language distribution
    lines.append("## Language distribution (text items)")
    lines.append("")
    lang_counter: Counter = Counter()
    for it in texts:
        langs = it.doc.get("language") or []
        if isinstance(langs, list):
            for l in langs:
                lang_counter[str(l)] += 1
    lines.append("| code | count |")
    lines.append("|---|---:|")
    for code, n in lang_counter.most_common():
        lines.append(f"| `{code}` | {n} |")
    lines.append("")

    # Panel fidelity / verdict
    lines.append("## Image quality distribution")
    lines.append("")
    lines.append("**panel_fidelity** (image items only)")
    lines.append("")
    lines.append("| value | count |")
    lines.append("|---|---:|")
    for k, n in pf.most_common():
        lines.append(f"| `{k}` | {n} |")
    lines.append("")
    lines.append("**panel_verdict** (image items only)")
    lines.append("")
    lines.append("| value | count |")
    lines.append("|---|---:|")
    for k, n in pv.most_common():
        lines.append(f"| `{k}` | {n} |")
    lines.append("")

    # Resolution
    lines.append("## Resolution")
    lines.append("")
    lines.append(f"Below orientation-aware floor (landscape < {FILL_AXIS_LANDSCAPE} width, portrait < {FILL_AXIS_PORTRAIT} height): **{len(res['below_floor'])}**")
    for line in res["below_floor"]:
        lines.append(f"- {line}")
    if res["below_long_edge"]:
        lines.append("")
        lines.append(f"Long edge < {LONG_EDGE_PREFERRED} preferred: **{len(res['below_long_edge'])}**")
        for line in res["below_long_edge"][:30]:
            lines.append(f"- {line}")
        if len(res["below_long_edge"]) > 30:
            lines.append(f"- ...and {len(res['below_long_edge']) - 30} more")
    if res["missing_dims"]:
        lines.append("")
        lines.append(f"Missing pixel_width/pixel_height: **{len(res['missing_dims'])}**")
        for i in res["missing_dims"]:
            lines.append(f"- {i}")
    lines.append("")

    # Outstanding rejects + flags
    rejects = [i for i in images if i.doc.get("panel_verdict") == "reject"]
    flags = [i for i in images if i.doc.get("panel_verdict") == "flag"]
    if rejects:
        lines.append("## Outstanding panel_verdict: reject")
        lines.append("")
        for it in rejects:
            reason = it.doc.get("verdict_reason", "")
            lines.append(f"- `{it.doc.get('id')}` ({it.folder}) — {reason}")
        lines.append("")
    if flags:
        lines.append("## Outstanding panel_verdict: flag")
        lines.append("")
        for it in flags:
            reason = it.doc.get("verdict_reason", "")
            lines.append(f"- `{it.doc.get('id')}` ({it.folder}) — {reason}")
        lines.append("")

    # Tag histograms (mood, register, form)
    for field_name in ("mood", "register", "form"):
        h = histogram(items, field_name)
        lines.append(f"## {field_name.capitalize()} histogram")
        lines.append("")
        lines.append(f"| {field_name} | count |")
        lines.append("|---|---:|")
        for k, n in h.most_common():
            known = k in set(taxonomy.get(field_name, []))
            marker = "" if known else " ⚠️ not in taxonomy"
            lines.append(f"| `{k}`{marker} | {n} |")
        lines.append("")

    return "\n".join(lines) + "\n"


def format_json(items: list[Item], taxonomy: dict[str, list[str]]) -> str:
    images = [i for i in items if i.kind == "image"]
    texts = [i for i in items if i.kind == "text"]
    nocturne = [i for i in items if i.is_nocturne and i.kind == "image"]
    ro, texts_total = romanian_share(items)
    res = resolution_status(items)
    pf = panel_fidelity_distribution(items)
    pv = panel_verdict_distribution(items)
    cov = coverage_by_side(items, taxonomy["themes"])
    out = {
        "generated": dt.date.today().isoformat(),
        "totals": {
            "all": len(items),
            "images": len(images),
            "texts": len(texts),
            "nocturne": len(nocturne),
        },
        "by_folder_tier": {},
        "romanian_share": {"ro_count": ro, "text_total": texts_total},
        "resolution": res,
        "panel_fidelity": dict(pf),
        "panel_verdict": dict(pv),
        "theme_coverage": cov,
    }
    by_folder_tier: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for it in items:
        by_folder_tier[it.folder][it.tier] += 1
    out["by_folder_tier"] = {k: dict(v) for k, v in by_folder_tier.items()}
    return json.dumps(out, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Corpus audit / coverage report")
    ap.add_argument("--out", type=Path, help="Write report to this file instead of stdout")
    ap.add_argument("--format", choices=("md", "json"), default="md")
    args = ap.parse_args()

    items = iter_sidecars()
    taxonomy = load_taxonomy()
    text = format_md(items, taxonomy) if args.format == "md" else format_json(items, taxonomy)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text)
        print(f"Wrote {args.out} ({len(items)} sidecars audited)")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())

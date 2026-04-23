"""corpus harvest <creator> — primary photographer-level ingestion flow.

Phase 1 (this module, no API calls, no corpus writes):
  - Resolve creator from Stage-1 shortlist YAML
  - DDG query "<Creator> best photos" with size:Large,type:photo,color:Monochrome
  - Apply candidate gate (surname, resolution MUST floor, reject-list)
  - pHash dedup on top candidates
  - Write contact sheet (HTML + MD) + decisions.yaml + report.md to
    corpus/_staging/harvest-<creator-id>/

Phase 2 (future: `corpus harvest --commit <creator>`):
  - Read decisions.yaml, for accepted items do Claude-vision tag + sidecar
    write + binary download + manifest update

See openspec/changes/add-ingestion-automation/design.md for the full design
and openspec/changes/add-ingestion-automation/specs/corpus-ingestion/spec.md
"Photographer harvest" requirement.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
from dataclasses import asdict
from pathlib import Path

try:
    import yaml  # type: ignore
except ImportError:
    sys.stderr.write("corpus harvest: PyYAML is required. `pip install -e pairing`\n")
    sys.exit(2)

from corpus_web_search import (
    Candidate,
    apply_gate,
    candidates_to_json,
    cluster_dedup,
    ddg_search,
    dhash,
    fetch_thumbnail,
    http_get,
    to_candidate,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CORPUS = REPO_ROOT / "corpus"
STAGING = CORPUS / "_staging"
MANIFEST = CORPUS / "_manifest.json"
TAXONOMY_DIR = CORPUS / "_taxonomy"
DEFAULT_SHORTLIST = STAGING / "top-50-bw-photographers.yaml"

IMG_EXTS = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp")
MIME_BY_EXT = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".tif": "image/tiff", ".tiff": "image/tiff", ".webp": "image/webp",
}
# Per-request cost estimate for Haiku 4.5 vision calls: ~$0.002 per image.
VISION_COST_USD = 0.002
VISION_MODEL = "claude-haiku-4-5"


# -- Shortlist resolution ----------------------------------------------------

def load_shortlist(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"shortlist not found: {path}")
    doc = yaml.safe_load(path.read_text()) or {}
    items = doc.get("items") or []
    if not isinstance(items, list):
        raise ValueError(f"shortlist {path} has no 'items' array")
    return items


def find_creator(items: list[dict], key: str) -> dict:
    """Match by id first, then case-insensitive name substring."""
    k = key.lower()
    # id exact
    for it in items:
        if str(it.get("id", "")).lower() == k:
            return it
    # name substring
    for it in items:
        if k in str(it.get("name", "")).lower():
            return it
    raise KeyError(f"creator '{key}' not in shortlist (try one of: "
                   + ", ".join(str(i.get('id', '?')) for i in items[:5]) + " …)")


def creator_surname(creator: dict) -> str:
    """Derive a usable surname for candidate-gate matching.

    Prefers explicit `surname` field if the shortlist provides one, falls
    back to the last whitespace-separated token of `name` (handles
    "Henri Cartier-Bresson" → "Cartier-Bresson",
    "Fan Ho" → "Ho", "Manuel Álvarez Bravo" → "Bravo").
    For two-part surnames like "Álvarez Bravo" or "Cartier-Bresson" we
    keep the hyphen/accent intact so word-boundary regex still matches.
    """
    s = creator.get("surname")
    if s:
        return str(s)
    name = str(creator.get("name") or "").strip()
    if not name:
        return ""
    parts = name.split()
    return parts[-1] if parts else name


# -- Batch dir ---------------------------------------------------------------

def batch_dir(creator_id: str) -> Path:
    d = STAGING / f"harvest-{creator_id}"
    d.mkdir(parents=True, exist_ok=True)
    return d


# -- Contact sheet rendering -------------------------------------------------

HTML_HEAD = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Harvest — {title}</title>
<style>
  body {{ font: 14px/1.4 -apple-system, system-ui, sans-serif; max-width: 1200px;
         margin: 1em auto; padding: 0 1em; color: #222; }}
  h1 {{ font-size: 1.4em; margin-bottom: .3em; }}
  .meta {{ color: #666; margin-bottom: 1em; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
           gap: 1em; }}
  figure {{ margin: 0; padding: .6em; background: #fafafa; border: 1px solid #e0e0e0;
           border-radius: 4px; }}
  figure.rej {{ background: #fff5f5; border-color: #e8b0b0; }}
  figure img {{ display: block; max-width: 100%; max-height: 280px;
                margin: 0 auto; background: #eaeaea; }}
  figcaption {{ font-size: 12px; margin-top: .4em; }}
  .id {{ font-family: ui-monospace, monospace; color: #0a5; font-weight: 600; }}
  .size {{ color: #666; }}
  .size.hr {{ color: #080; font-weight: 600; }}
  .dom {{ color: #334; }}
  .reason {{ color: #b00; font-weight: 600; }}
  .title {{ color: #222; }}
  a {{ color: inherit; }}
  details {{ margin-top: 1em; }}
  h2 {{ font-size: 1.1em; color: #333; margin-top: 2em; }}
</style>
</head><body>
<h1>Harvest — {title}</h1>
<div class="meta">
  Creator: <strong>{name}</strong>
  &middot; Query: <code>{query}</code>
  &middot; {total} DDG candidates &middot; {kept} pass gate &middot; {unique} unique (pHash)
</div>
<p>Edit <code>decisions.yaml</code> in this folder to mark items <code>accept: true</code>. Then run <code>corpus harvest --commit {cid}</code> (Phase 2, not yet implemented).</p>
<h2>Accepted pool ({kept_label})</h2>
<div class="grid">
{kept_cards}
</div>
<details><summary><h2 style="display:inline">Rejected by gate ({rej_count})</h2></summary>
<div class="grid">
{rej_cards}
</div>
</details>
</body></html>
"""


def _card_html(c: Candidate, local_id: str, is_rejected: bool = False) -> str:
    size_class = "size hr" if c.high_res else "size"
    reason_html = (f'<div class="reason">{c.reject_reason}</div>'
                   if is_rejected and c.reject_reason else "")
    title = (c.title or "").replace("<", "&lt;").replace(">", "&gt;")[:160]
    host = c.host or "—"
    return (
        f'<figure{" class=rej" if is_rejected else ""}>'
        f'<a href="{c.image_url}" target="_blank"><img src="{c.thumb_url}" loading="lazy" alt=""></a>'
        f'<figcaption>'
        f'<div class="id">{local_id}</div>'
        f'<div class="{size_class}">{c.width}×{c.height}{" · HIGH-RES" if c.high_res else ""}</div>'
        f'<div class="dom">rank #{c.ddg_rank} · <a href="{c.source_url}" target="_blank">{host}</a>'
        f' · dom {c.domain_weight:.2f}</div>'
        f'{reason_html}'
        f'<div class="title">{title}</div>'
        f'</figcaption></figure>'
    )


def render_contact_sheet(
    creator: dict, query: str, kept: list[Candidate], rejected: list[Candidate],
    decisions_ids: list[str],
) -> tuple[str, str]:
    """Return (html, md)."""
    name = creator.get("name", "?")
    cid = creator.get("id", "?")
    total = len(kept) + len(rejected)
    unique = len({c.cluster_id for c in kept if c.cluster_id is not None})

    kept_cards = "\n".join(_card_html(c, decisions_ids[i]) for i, c in enumerate(kept))
    rej_cards = "\n".join(_card_html(c, f"rej-{i+1}", is_rejected=True)
                          for i, c in enumerate(rejected))

    html = HTML_HEAD.format(
        title=name, name=name, query=query, cid=cid,
        total=total, kept=len(kept), unique=unique,
        kept_cards=kept_cards,
        kept_label=f"{len(kept)} kept, {unique} unique images",
        rej_count=len(rejected), rej_cards=rej_cards,
    )

    md_lines = [
        f"# Harvest — {name}",
        "",
        f"- Creator id: `{cid}`",
        f"- Query: `{query}`",
        f"- DDG candidates: {total}",
        f"- Passed gate: {len(kept)}",
        f"- Unique images (pHash-deduped): {unique}",
        "",
        "## Kept candidates",
        "",
    ]
    for i, c in enumerate(kept):
        md_lines.append(
            f"- **{decisions_ids[i]}** · {c.width}×{c.height}"
            f"{' **HIGH-RES**' if c.high_res else ''}"
            f" · rank #{c.ddg_rank} · {c.host}"
            f" · [{(c.title or '')[:80]}]({c.source_url})"
        )
    md_lines += ["", "## Rejected", ""]
    for c in rejected:
        md_lines.append(
            f"- *{c.reject_reason}* · {c.width}×{c.height} · {c.host}"
            f" · {(c.title or '')[:80]}"
        )
    return html, "\n".join(md_lines) + "\n"


# -- Decisions YAML ----------------------------------------------------------

def render_decisions_yaml(creator: dict, kept: list[Candidate],
                          decisions_ids: list[str]) -> str:
    """Operator-editable YAML. Every entry starts with accept: false."""
    name = creator.get("name", "?")
    cid = creator.get("id", "?")
    lines = [
        f"# Harvest decisions for: {name} ({cid})",
        f"# Edit each entry's `accept:` to true for items you want to commit.",
        f"# After editing, run:  corpus harvest --commit {cid}",
        f"",
        f"creator: {cid}",
        f"decisions:",
    ]
    for i, c in enumerate(kept):
        lid = decisions_ids[i]
        # YAML-safe title (quote aggressively)
        safe_title = str(c.title or "").replace('"', "'").replace("\n", " ").strip()[:180]
        lines += [
            f"  - local_id: {lid}",
            f"    accept: false",
            f"    width: {c.width}",
            f"    height: {c.height}",
            f"    host: {c.host}",
            f"    ddg_rank: {c.ddg_rank}",
            f"    cluster: {c.cluster_id}",
            f"    domain_weight: {c.domain_weight:.2f}",
            f"    high_res: {str(c.high_res).lower()}",
            f'    title: "{safe_title}"',
            f"    image_url: {c.image_url}",
            f"    source_url: {c.source_url}",
            "",
        ]
    return "\n".join(lines)


# -- Report ------------------------------------------------------------------

def render_report(
    creator: dict, query: str, total: int, kept: list[Candidate],
    rejected_by_reason: dict[str, int],
) -> str:
    n_high = sum(1 for c in kept if c.high_res)
    n_kept = len(kept)
    unique = len({c.cluster_id for c in kept if c.cluster_id is not None})
    orient_counts: dict[str, int] = {"wide": 0, "tall": 0, "square": 0}
    for c in kept:
        orient_counts[c.orientation()] += 1
    lines = [
        f"# Harvest report — {creator.get('name')}",
        "",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        f"- Creator id: `{creator.get('id')}`",
        f"- Query: `{query}`",
        f"- DDG candidates total: {total}",
        f"- Passed gate: {n_kept}",
        f"- HIGH-RES (≥ 1800 long-edge): {n_high}",
        f"- Unique images (pHash-deduped): {unique}",
        f"- Orientation distribution (tall/wide/square): "
        f"{orient_counts['tall']}/{orient_counts['wide']}/{orient_counts['square']}",
        "",
        "## Rejection reasons",
        "",
    ]
    for reason, count in sorted(rejected_by_reason.items()):
        lines.append(f"- `{reason}`: {count}")
    return "\n".join(lines) + "\n"


# -- Main flow ---------------------------------------------------------------

def _harvest_pipeline(creator: dict, *, max_results: int, phash_limit: int,
                       query_override: str | None) -> tuple[dict, list[Candidate], list[Candidate], str, int]:
    """DDG → gate → pHash dedup. Returns (creator_meta, representatives, rejected, query, total).

    Shared by run_harvest (contact-sheet mode) and run_auto_commit.
    """
    cid = str(creator.get("id") or "")
    name = str(creator.get("name") or "")
    surname = creator_surname(creator)
    if not cid or not name or not surname:
        raise ValueError(f"creator entry missing id/name/surname: {creator}")

    query = query_override or f"{name} best photos"
    print(f"→ harvest: {cid} ({name}) | surname='{surname}'")
    print(f"  query: {query!r}")

    rows = ddg_search(query, orientation=None, max_results=max_results)
    total = len(rows)
    print(f"  DDG returned {total} candidates")

    gated: list[Candidate] = []
    for i, row in enumerate(rows, start=1):
        c = to_candidate(i, row, surname)
        apply_gate(c)
        gated.append(c)

    kept = [c for c in gated if c.reject_reason is None]
    rejected = [c for c in gated if c.reject_reason is not None]

    to_phash = kept[:phash_limit]
    print(f"  pHash-ing top {len(to_phash)} kept candidates …")
    for c in to_phash:
        tb = fetch_thumbnail(c)
        if tb:
            c.phash = dhash(tb)
        time.sleep(0.05)

    clusters = cluster_dedup(to_phash, threshold=8)
    representatives = [cl[0] for cl in clusters]
    representatives.sort(key=lambda c: c.ddg_rank)
    return creator, representatives, rejected, query, total


def _write_harvest_artifacts(creator: dict, query: str, total: int,
                              representatives: list[Candidate], rejected: list[Candidate],
                              decisions_ids: list[str], kept_all: list[Candidate]) -> Path:
    cid = str(creator.get("id") or "")
    d = batch_dir(cid)
    (d / "candidates.json").write_text(json.dumps({
        "creator": {k: creator.get(k) for k in ("id", "name", "surname", "years", "lineage", "canon_weight")},
        "query": query,
        "total_ddg_results": total,
        "kept": candidates_to_json(kept_all),
        "rejected": candidates_to_json(rejected),
    }, ensure_ascii=False, indent=2) + "\n")
    html, md = render_contact_sheet(creator, query, representatives, rejected, decisions_ids)
    (d / "contact-sheet.html").write_text(html)
    (d / "contact-sheet.md").write_text(md)
    rejected_by_reason: dict[str, int] = {}
    for c in rejected:
        rejected_by_reason[c.reject_reason or "unknown"] = rejected_by_reason.get(c.reject_reason or "unknown", 0) + 1
    (d / "report.md").write_text(render_report(creator, query, total, representatives, rejected_by_reason))
    return d


def run_harvest(creator: dict, *, max_results: int = 40, phash_limit: int = 30,
                query_override: str | None = None) -> int:
    try:
        creator, representatives, rejected, query, total = _harvest_pipeline(
            creator, max_results=max_results, phash_limit=phash_limit,
            query_override=query_override)
    except Exception as e:
        sys.stderr.write(f"harvest: {e}\n")
        return 1

    kept_all = [c for c in rejected + representatives if c.reject_reason is None]
    # Ensure kept_all is the gate-passing superset (cluster heads + their members);
    # the earlier separation already guarantees representatives all have no reject_reason.
    kept_all = [c for c in representatives]

    decisions_ids = [f"c{i+1:02d}" for i in range(len(representatives))]
    d = _write_harvest_artifacts(creator, query, total, representatives, rejected,
                                  decisions_ids, kept_all)
    (d / "decisions.yaml").write_text(render_decisions_yaml(creator, representatives, decisions_ids))

    print(f"  kept {len(representatives)} unique (of {total})")
    print(f"  wrote → {d.relative_to(REPO_ROOT)}/")
    print(f"    - contact-sheet.html   (open in a browser)")
    print(f"    - decisions.yaml       (edit accept:true for items to commit)")
    print(f"    - candidates.json / report.md / contact-sheet.md")
    return 0


# =========================================================================
# PHASE 2 — commit accepted items via Claude-vision tagging
# =========================================================================

KEBAB_RE = re.compile(r"[^a-z0-9-]+")


def kebab(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"[_\s]+", "-", s)
    s = KEBAB_RE.sub("", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "item"


def load_taxonomy_keys() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for name in ("themes", "mood", "register", "form"):
        p = TAXONOMY_DIR / f"{name}.yaml"
        if not p.exists():
            out[name] = set()
            continue
        data = yaml.safe_load(p.read_text()) or {}
        out[name] = set(data.keys()) if isinstance(data, dict) else set()
    return out


def load_taxonomy_for_prompt() -> str:
    """Human-readable summary of the taxonomy for the Claude system prompt.

    We pass keys only (not labels/descriptions) to keep the prompt tight;
    the caller cares about validation, not education.
    """
    parts = []
    for name in ("themes", "mood", "register"):
        p = TAXONOMY_DIR / f"{name}.yaml"
        data = yaml.safe_load(p.read_text()) if p.exists() else {}
        keys = sorted((data or {}).keys()) if isinstance(data, dict) else []
        parts.append(f"{name.upper()} (keys only, pick from this set):\n  " + ", ".join(keys))
    # Form is split into text vs image groups; we only emit the image group.
    form_p = TAXONOMY_DIR / "form.yaml"
    form_data = yaml.safe_load(form_p.read_text()) if form_p.exists() else {}
    img_forms = sorted(k for k in (form_data or {}).keys()
                       if k in {"etching","engraving","woodblock","wood-engraving",
                                "lithograph","drawing","photograph","painting",
                                "ink-wash","silverpoint","poster"})
    parts.append("FORM (image, single value): " + ", ".join(img_forms))
    return "\n\n".join(parts)


VISION_SYSTEM_PROMPT_TEMPLATE = """You are a visual archivist curating a personal-library photography collection for a 3-bit greyscale e-ink display (Inkplate 10, 1200×825). Only monochrome-surviving work is admitted.

For each image you will be shown, given the creator's name, identify the specific work if you can (title, year), and propose taxonomy-compliant tags.

{taxonomy}

PANEL_FIDELITY:
- native: work conceived under pure-value constraint; full fidelity on 3-bit panel (B&W photograph, etching, pen/ink drawing, silver-gelatin, sumi-e, monochrome lithograph).
- robust: color-origin but tonal structure carries composition without hue (Hiroshige snow, Vermeer interior).
- color-dependent: NOT ADMITTED; figure/ground or register carried by hue. Reject with reason "color_dependent".

OUTPUT: strict JSON, no prose, no code fence.

Schema:
{{
  "status": "accept" | "reject",
  "reject_reason": null | "portrait_of_creator" | "book_cover" | "exhibition_poster" | "wrong_creator" | "color_dependent" | "not_a_work" | "unreadable",
  "title": string,                 // specific work title if identifiable, else a descriptive title
  "year": integer | null,
  "themes": [string, ...],         // 3-5 keys from THEMES
  "mood": [string, ...],           // 1-3 keys from MOOD
  "register": [string, ...],       // 1-3 keys from REGISTER
  "form": string,                  // single key from FORM
  "panel_fidelity": "native" | "robust",
  "confidence": "high" | "medium" | "low",   // how confident in the title identification
  "notes": string                  // one-line curatorial note, <= 120 chars
}}

Reject when image is:
- a portrait / self-portrait of the creator (not their work)
- a book cover, magazine cover, gallery-exhibition poster, event flyer
- clearly not a work by the named creator
- a color-dependent composition where hue drives figure/ground
"""


def _anthropic_client():
    try:
        import anthropic  # type: ignore
    except ImportError:
        raise RuntimeError(
            "The Anthropic SDK is required for `corpus harvest --commit`.\n"
            "Install it with:  pip install anthropic\n"
            "Then set ANTHROPIC_API_KEY in your environment."
        )
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Export it before running `corpus harvest --commit`."
        )
    return anthropic.Anthropic()


def _media_type_from_bytes(image_bytes: bytes) -> str:
    if image_bytes[:8].startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def _parse_vision_json(text: str) -> dict:
    """Parse a JSON object out of a Claude text response.

    Handles: plain JSON; ```json\\n{...}\\n``` fences; leading prose before
    {...}; trailing prose after {...}; multiple JSON objects (returns first).

    Uses json.JSONDecoder().raw_decode() so any content after the first valid
    object is ignored, rather than tripping "Extra data" parse errors.
    """
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text).strip()
    i = text.find("{")
    if i < 0:
        raise RuntimeError(f"no JSON object found: {text[:300]}")
    try:
        obj, _end = json.JSONDecoder().raw_decode(text[i:])
        return obj
    except json.JSONDecodeError as e:
        raise RuntimeError(f"vision response was not valid JSON: {e}\nraw: {text[i:i+400]}")


def vision_tag(image_bytes: bytes, *, creator_name: str, title_hint: str,
               source_url: str, system_prompt: str, client) -> dict:
    """Call Claude vision and return parsed JSON response. Raises on error."""
    image_bytes = make_vision_thumbnail(image_bytes)
    b64 = base64.standard_b64encode(image_bytes).decode("ascii")
    media_type = _media_type_from_bytes(image_bytes)
    user_text = (
        f"Creator: {creator_name}\n"
        f"DDG title hint: {title_hint or '(none)'}\n"
        f"Source page: {source_url or '(none)'}\n\n"
        f"Identify the work and propose tags per schema. Output JSON only."
    )
    resp = client.messages.create(
        model=VISION_MODEL,
        max_tokens=1500,
        system=[{
            "type": "text", "text": system_prompt,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {
                    "type": "base64", "media_type": media_type, "data": b64}},
                {"type": "text", "text": user_text},
            ],
        }],
    )
    return _parse_vision_json(resp.content[0].text)


def vision_tag_retry(image_bytes: bytes, *, creator_name: str, title_hint: str,
                      source_url: str, system_prompt: str, client,
                      prior_response: dict, errors: list[str]) -> dict:
    """Second-chance call: send the original response + validation errors back
    to Claude and ask for a corrected JSON.

    Cost: one additional API call. Typically recovers category-confusion
    (e.g. 'documentary' placed in themes when it belongs to register) without
    giving Claude a chance to hallucinate a different title.
    """
    image_bytes = make_vision_thumbnail(image_bytes)
    b64 = base64.standard_b64encode(image_bytes).decode("ascii")
    media_type = _media_type_from_bytes(image_bytes)
    user_text_initial = (
        f"Creator: {creator_name}\n"
        f"DDG title hint: {title_hint or '(none)'}\n"
        f"Source page: {source_url or '(none)'}\n\n"
        f"Identify the work and propose tags per schema. Output JSON only."
    )
    correction = (
        "Your prior response failed taxonomy validation with these errors:\n"
        + "\n".join(f"  - {e}" for e in errors) + "\n\n"
        "Reply with a CORRECTED JSON object using the SAME title / year / "
        "panel_fidelity / form / confidence / notes you chose above, but with "
        "tag values adjusted so every item in themes/mood/register is a valid "
        "key from the taxonomy listed in the system prompt. If a concept you "
        "proposed has no matching key in the correct dimension, drop it "
        "rather than swap it for a loose synonym. Output JSON only."
    )
    resp = client.messages.create(
        model=VISION_MODEL,
        max_tokens=1500,
        system=[{
            "type": "text", "text": system_prompt,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[
            {"role": "user", "content": [
                {"type": "image", "source": {
                    "type": "base64", "media_type": media_type, "data": b64}},
                {"type": "text", "text": user_text_initial},
            ]},
            {"role": "assistant", "content": json.dumps(prior_response)},
            {"role": "user", "content": correction},
        ],
    )
    return _parse_vision_json(resp.content[0].text)


def validate_vision_response(vr: dict, tax: dict[str, set[str]]) -> list[str]:
    """Return list of validation errors; empty means OK."""
    errs: list[str] = []
    if vr.get("status") not in ("accept", "reject"):
        errs.append("status must be 'accept' or 'reject'")
    if vr.get("status") == "reject":
        if not vr.get("reject_reason"):
            errs.append("rejected response missing reject_reason")
        return errs  # no tag validation on rejects
    for fld, tax_key in (("themes", "themes"), ("mood", "mood"), ("register", "register")):
        val = vr.get(fld)
        if not isinstance(val, list) or not val:
            errs.append(f"{fld} must be a non-empty list")
            continue
        unknown = [v for v in val if v not in tax[tax_key]]
        if unknown:
            errs.append(f"{fld} has unknown taxonomy keys: {unknown}")
    form = vr.get("form")
    if form not in tax["form"]:
        errs.append(f"form '{form}' is not in form.yaml keys")
    pf = vr.get("panel_fidelity")
    if pf not in ("native", "robust"):
        errs.append(f"panel_fidelity must be 'native' or 'robust' (got: {pf})")
    title = vr.get("title")
    if not title or not isinstance(title, str):
        errs.append("title must be a non-empty string")
    return errs


# -- Binary fetch + resize --------------------------------------------------

def guess_ext_from_url_or_bytes(url: str, content: bytes) -> str:
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return ".webp"
    if content[:2] == b"\xff\xd8":
        return ".jpg"
    if content[:4] in (b"II*\x00", b"MM\x00*"):
        return ".tif"
    # Fall back to URL path.
    path = urllib.parse.urlparse(url).path.lower()
    for ext in IMG_EXTS:
        if path.endswith(ext):
            return ext
    return ".jpg"


_BROWSER_UAS = [
    # Safari desktop (default; polite)
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    # Firefox desktop (retry-1 — some CDNs that 403 Safari allow Firefox)
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.0; rv:119.0) Gecko/20100101 Firefox/119.0",
    # Chrome desktop (retry-2)
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


def _fetch_with_retry(url: str, timeout: int = 30) -> bytes:
    """Download with fallback UAs. Helps through CDNs that 403 Safari but
    accept Firefox/Chrome (observed on cloudfront, some gallery hosts)."""
    last_err = None
    for ua in _BROWSER_UAS:
        try:
            return http_get(url, binary=True, timeout=timeout,
                             headers={"User-Agent": ua,
                                       "Accept": "image/*,*/*;q=0.8"})
        except Exception as e:
            last_err = e
            continue
    raise last_err if last_err else RuntimeError(f"fetch failed: {url}")


def download_image(url: str, max_long_edge: int = 4096) -> tuple[bytes, str, int, int]:
    """Fetch image; optionally downscale. Return (bytes, ext, w, h).

    If the post-resize bytes are still likely to trip Claude's 5 MB base64
    cap (~3.75 MB raw → ~5 MB base64), the returned bytes are re-encoded at
    a lower JPEG quality. Separate vision-thumbnail helper below handles the
    "need a small version for the API call" case distinctly.
    """
    raw = _fetch_with_retry(url, timeout=30)
    ext = guess_ext_from_url_or_bytes(url, raw)
    from PIL import Image
    import io as _io
    img = Image.open(_io.BytesIO(raw))
    w, h = img.size
    if max(w, h) > max_long_edge:
        scale = max_long_edge / max(w, h)
        new_w, new_h = int(w * scale), int(h * scale)
        img = img.convert("L") if img.mode not in ("RGB", "L", "RGBA") else img
        img = img.resize((new_w, new_h), Image.LANCZOS)
        buf = _io.BytesIO()
        if img.mode == "RGBA":
            img = img.convert("RGB")
        img.save(buf, format="JPEG", quality=92, optimize=True)
        raw = buf.getvalue()
        ext = ".jpg"
        w, h = new_w, new_h
    return raw, ext, w, h


def make_vision_thumbnail(image_bytes: bytes, max_edge: int = 1600,
                            target_kb: int = 3500) -> bytes:
    """Produce a JPEG safely under Claude's 5 MB base64 cap for a vision call.

    The stored binary stays full-res (per download_image); this is a separate
    smaller buffer fed only to the vision API. Claude is scale-invariant for
    work identification — 1600 long-edge is plenty.
    """
    # Short-circuit when the input is already comfortably under the cap.
    # Claude's base64 payload is ~4/3 the raw size, so 3.5 MB raw → ~4.67 MB b64.
    if len(image_bytes) <= target_kb * 1024:
        return image_bytes
    from PIL import Image
    import io as _io
    img = Image.open(_io.BytesIO(image_bytes))
    if img.mode == "RGBA":
        img = img.convert("RGB")
    elif img.mode not in ("RGB", "L"):
        img = img.convert("L")
    w, h = img.size
    if max(w, h) > max_edge:
        scale = max_edge / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    # Shrink quality until under target; rarely goes below 70.
    for q in (85, 80, 75, 70):
        buf = _io.BytesIO()
        img.save(buf, format="JPEG", quality=q, optimize=True)
        out = buf.getvalue()
        if len(out) <= target_kb * 1024:
            return out
    return out


# -- Sidecar id + YAML ------------------------------------------------------

def generate_sidecar_id(surname: str, title: str, existing: set[str],
                         creator_id: str, local_id: str) -> str:
    title_slug = kebab(title)
    surname_slug = kebab(surname)
    # Drop any surname tokens already present at the start of the title slug.
    if title_slug.startswith(surname_slug):
        base = title_slug
    elif surname_slug:
        base = f"{surname_slug}-{title_slug}"
    else:
        base = title_slug or f"{creator_id}-harvest-{local_id}"
    # Trim absurdly long ids.
    base = base[:80].rstrip("-")
    cand = base
    suffix = 2
    while cand in existing:
        cand = f"{base}-v{suffix}"
        suffix += 1
    return cand


def build_harvest_sidecar(
    *, item_id: str, creator_name: str, title: str, year,
    source_url: str, citation: str, width: int, height: int,
    form: str, panel_fidelity: str, themes: list[str],
    mood: list[str], register: list[str], notes: str,
    claude_confidence: str | None = None,
) -> dict:
    """Construct a corpus/personal_library/ sidecar dict matching corpus-schema."""
    doc: dict = {
        "id": item_id,
        "title": title,
        "artist": creator_name,
        "year": year if isinstance(year, int) else None,
        "rights_tier": "personal_library",
        "source": "web",
        "source_url": source_url,
        "citation": citation,
        "medium": _medium_from_form(form),
        "pixel_width": int(width),
        "pixel_height": int(height),
        "form": form,
        "themes": list(themes),
        "mood": list(mood),
        "register": list(register),
        "panel_fidelity": panel_fidelity,
        "added": time.strftime("%Y-%m-%d"),
    }
    if notes:
        doc["notes"] = str(notes)[:180]
    if claude_confidence:
        # Stored so that post-hoc cleanups ("keep only high-confidence") can
        # filter without re-running vision. Never consumed by the corpus
        # pipeline — purely audit metadata.
        doc["claude_confidence"] = str(claude_confidence)
    return doc


def _medium_from_form(form: str) -> str:
    return {
        "photograph": "silver gelatin photograph",
        "etching": "etching",
        "engraving": "engraving",
        "woodblock": "woodblock print",
        "wood-engraving": "wood engraving",
        "lithograph": "lithograph",
        "drawing": "drawing",
        "painting": "painting",
        "ink-wash": "ink wash",
        "silverpoint": "silverpoint",
        "poster": "lithographic poster",
    }.get(form, form)


# -- Decisions + existing ids ------------------------------------------------

def load_decisions(batch_dir: Path) -> tuple[str, list[dict]]:
    dec_path = batch_dir / "decisions.yaml"
    if not dec_path.exists():
        raise FileNotFoundError(f"decisions.yaml not found at {dec_path}")
    doc = yaml.safe_load(dec_path.read_text()) or {}
    return doc.get("creator", ""), doc.get("decisions", []) or []


def existing_sidecar_ids() -> set[str]:
    ids: set[str] = set()
    for folder in ("images", "texts", "nocturne", "personal_library",
                   "personal_library/nocturne"):
        for p in (CORPUS / folder).glob("*.yaml"):
            if p.name.startswith("EXAMPLE"):
                continue
            try:
                d = yaml.safe_load(p.read_text()) or {}
            except Exception:
                continue
            iid = d.get("id")
            if iid:
                ids.add(str(iid))
    return ids


def append_manifest_entry(path: Path, mime: str, sha256: str, size: int) -> None:
    if MANIFEST.exists():
        doc = json.loads(MANIFEST.read_text())
    else:
        doc = {"schema_version": 1, "created": time.strftime("%Y-%m-%d"), "entries": []}
    rel = path.relative_to(REPO_ROOT).as_posix()
    if any(e.get("path") == rel for e in doc.get("entries", [])):
        return
    doc.setdefault("entries", []).append({
        "path": rel,
        "sha256": sha256,
        "bytes": size,
        "mime": mime,
        "backup_uri": f"file://{path.resolve()}",
    })
    MANIFEST.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")


# -- Commit orchestrator ----------------------------------------------------

def run_commit(creator_id: str, *, max_budget_usd: float | None = None,
               max_long_edge: int = 4096, default_citation: str | None = None,
               dry_run: bool = False) -> int:
    batch_dir = STAGING / f"harvest-{creator_id}"
    if not batch_dir.is_dir():
        sys.stderr.write(f"harvest --commit: no batch at {batch_dir}\n")
        return 2
    try:
        dec_creator, decisions = load_decisions(batch_dir)
    except FileNotFoundError as e:
        sys.stderr.write(f"harvest --commit: {e}\n")
        return 2
    if dec_creator != creator_id:
        sys.stderr.write(f"harvest --commit: decisions.yaml creator '{dec_creator}' != '{creator_id}'\n")
        return 2
    accepted = [d for d in decisions if d.get("accept") is True]
    if not accepted:
        sys.stderr.write(
            f"harvest --commit: no entries have `accept: true` in decisions.yaml "
            f"({batch_dir.relative_to(REPO_ROOT)}/decisions.yaml).\n"
            f"Edit the file to mark items for commit.\n")
        return 2

    # Read candidate details
    cand_path = batch_dir / "candidates.json"
    candidates_doc = json.loads(cand_path.read_text()) if cand_path.exists() else {}
    creator_info = candidates_doc.get("creator") or {}
    creator_name = creator_info.get("name") or creator_id.replace("-", " ").title()
    surname = creator_info.get("surname") or creator_name.split()[-1]
    citation = default_citation or (
        f"{creator_name}, personal-library reproduction, web-sourced; archival record held by operator"
    )

    print(f"→ harvest --commit: {creator_id} ({creator_name})")
    print(f"  accepted entries: {len(accepted)}")
    print(f"  budget: ${max_budget_usd if max_budget_usd is not None else 'unlimited'}")
    if dry_run:
        print(f"  (dry-run — no API calls, no writes)")

    # Pre-flight: taxonomy + existing ids + Anthropic client
    tax = load_taxonomy_keys()
    used_ids = existing_sidecar_ids()
    client = None
    if not dry_run:
        try:
            client = _anthropic_client()
        except RuntimeError as e:
            sys.stderr.write(f"harvest --commit: {e}\n")
            return 2
    system_prompt = VISION_SYSTEM_PROMPT_TEMPLATE.format(taxonomy=load_taxonomy_for_prompt())

    report_lines = [
        f"# Harvest commit report — {creator_name}",
        "",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Accepted entries: {len(accepted)}",
        "",
    ]
    committed: list[dict] = []
    rejected_by_vision: list[dict] = []
    errors: list[dict] = []
    total_cost = 0.0
    dest_parent = CORPUS / "personal_library"
    dest_parent.mkdir(parents=True, exist_ok=True)

    for idx, entry in enumerate(accepted, 1):
        local_id = entry.get("local_id", f"item-{idx}")
        image_url = entry.get("image_url")
        source_url = entry.get("source_url")
        title_hint = entry.get("title") or ""
        w_hint = int(entry.get("width", 0) or 0)
        h_hint = int(entry.get("height", 0) or 0)
        prefix = f"  [{idx}/{len(accepted)}] {local_id}"

        if max_budget_usd is not None and total_cost + VISION_COST_USD > max_budget_usd:
            print(f"{prefix}: budget exceeded (${total_cost:.4f} + {VISION_COST_USD} > ${max_budget_usd})")
            errors.append({"local_id": local_id, "reason": "budget_exhausted"})
            break

        if dry_run:
            print(f"{prefix}: DRY-RUN — would vision-tag and commit {image_url}")
            continue

        # 1. Download full image (also use for vision call).
        try:
            raw, ext, full_w, full_h = download_image(image_url, max_long_edge=max_long_edge)
        except Exception as e:
            print(f"{prefix}: DOWNLOAD-FAILED ({e})")
            errors.append({"local_id": local_id, "reason": f"download_failed: {e}"})
            continue

        # 2. Vision call.
        try:
            vr = vision_tag(
                raw,
                creator_name=creator_name,
                title_hint=title_hint,
                source_url=source_url or "",
                system_prompt=system_prompt,
                client=client,
            )
        except Exception as e:
            print(f"{prefix}: VISION-ERROR ({e})")
            errors.append({"local_id": local_id, "reason": f"vision_error: {e}"})
            continue
        total_cost += VISION_COST_USD

        if vr.get("status") == "reject":
            reason = vr.get("reject_reason") or "unknown"
            print(f"{prefix}: VISION-REJECTED ({reason})")
            rejected_by_vision.append({"local_id": local_id, "reason": reason,
                                        "notes": vr.get("notes", "")})
            continue

        # 3. Validate tags against taxonomy.
        errs = validate_vision_response(vr, tax)
        if errs:
            print(f"{prefix}: TAX-VALIDATION-FAILED: {errs}")
            errors.append({"local_id": local_id, "reason": f"taxonomy_errors: {errs}"})
            continue

        # 4. Generate stable sidecar id.
        item_id = generate_sidecar_id(
            surname=surname, title=vr["title"], existing=used_ids,
            creator_id=creator_id, local_id=local_id,
        )
        used_ids.add(item_id)

        # 5. Write binary.
        bin_path = dest_parent / f"{item_id}{ext}"
        if bin_path.exists():
            print(f"{prefix}: SKIP (binary already exists at {bin_path.name})")
            errors.append({"local_id": local_id, "reason": "collision_binary"})
            continue
        bin_path.write_bytes(raw)
        sha = hashlib.sha256(raw).hexdigest()
        mime = MIME_BY_EXT.get(ext, "application/octet-stream")

        # 6. Build + write sidecar.
        sidecar = build_harvest_sidecar(
            item_id=item_id, creator_name=creator_name,
            title=vr["title"], year=vr.get("year"),
            source_url=source_url or image_url or "",
            citation=citation,
            width=full_w, height=full_h,
            form=vr["form"], panel_fidelity=vr["panel_fidelity"],
            themes=vr["themes"], mood=vr["mood"], register=vr["register"],
            notes=vr.get("notes", ""),
            claude_confidence=vr.get("confidence"),
        )
        sidecar_path = dest_parent / f"{item_id}.yaml"
        if sidecar_path.exists():
            # Unlikely — id-generation deduped — but defensive.
            bin_path.unlink(missing_ok=True)
            print(f"{prefix}: SKIP (sidecar already exists at {sidecar_path.name})")
            errors.append({"local_id": local_id, "reason": "collision_sidecar"})
            continue
        sidecar_path.write_text(
            yaml.safe_dump(sidecar, sort_keys=False, allow_unicode=True,
                           default_flow_style=False)
        )

        # 7. Append manifest.
        append_manifest_entry(bin_path, mime=mime, sha256=sha, size=len(raw))

        committed.append({
            "local_id": local_id, "id": item_id, "title": vr["title"],
            "year": vr.get("year"), "size": f"{full_w}×{full_h}",
            "confidence": vr.get("confidence", "?"),
        })
        print(f"{prefix}: ✓ committed as '{item_id}' — {vr['title']} ({vr.get('year', '?')}, conf={vr.get('confidence','?')})")

    # Commit report
    report_lines += [
        f"## Committed ({len(committed)})",
        "",
    ]
    for c in committed:
        report_lines.append(f"- `{c['id']}` — {c['title']} ({c.get('year') or '?'}) · {c['size']} · conf={c['confidence']}")
    report_lines += ["", f"## Rejected by Claude-vision ({len(rejected_by_vision)})", ""]
    for r in rejected_by_vision:
        report_lines.append(f"- {r['local_id']}: `{r['reason']}` — {r.get('notes','')}")
    report_lines += ["", f"## Errors ({len(errors)})", ""]
    for e in errors:
        report_lines.append(f"- {e['local_id']}: {e['reason']}")
    report_lines += ["", f"## Cost", "",
                     f"- Vision calls: {len(committed) + len(rejected_by_vision)}",
                     f"- Approximate cost: ${total_cost:.4f}"]
    (batch_dir / "commit-report.md").write_text("\n".join(report_lines) + "\n")

    print()
    print(f"summary: committed {len(committed)}, vision-rejected {len(rejected_by_vision)}, errors {len(errors)}")
    print(f"cost: ~${total_cost:.4f}")
    print(f"report: {batch_dir.relative_to(REPO_ROOT)}/commit-report.md")
    if committed:
        print("run `corpus validate` to confirm the corpus is still clean.")
    return 0 if not errors else 1


# -- Auto-commit: harvest + vision + commit in one shot -------------------

CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}


def _load_secret_fallback_key() -> str | None:
    """Optional convenience: read ANTHROPIC_API_KEY from ha/secrets.yaml if
    present, so the operator doesn't have to re-export before each run.

    Never logs the key. Only consulted if env var is missing.
    """
    path = REPO_ROOT / "ha" / "secrets.yaml"
    if not path.exists():
        return None
    try:
        doc = yaml.safe_load(path.read_text()) or {}
    except Exception:
        return None
    for k in ("anthropic_api_key", "ANTHROPIC_API_KEY", "anthropic_key"):
        v = doc.get(k)
        if v:
            return str(v).strip()
    return None


def _ensure_anthropic_key() -> None:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return
    v = _load_secret_fallback_key()
    if v:
        os.environ["ANTHROPIC_API_KEY"] = v


def _existing_source_urls() -> set[str]:
    """Scan personal_library/*.yaml for source_url values (to skip already-ingested items)."""
    urls: set[str] = set()
    for p in (CORPUS / "personal_library").glob("*.yaml"):
        if p.name.startswith("EXAMPLE"):
            continue
        try:
            d = yaml.safe_load(p.read_text()) or {}
        except Exception:
            continue
        u = d.get("source_url")
        if u:
            urls.add(str(u))
    return urls


def build_existing_phash_index(scope: str = "personal_library") -> list[tuple[str, int]]:
    """Compute dHash for every image already on disk in the given scope, for
    semantic-duplicate detection against new candidates.

    Returns [(sidecar_id, phash), ...]. Missing PIL reads are silently skipped
    (already validated by corpus validate; we are just deduping).
    """
    roots = []
    if scope in ("personal_library", "all"):
        roots.append(CORPUS / "personal_library")
        roots.append(CORPUS / "personal_library" / "nocturne")
    if scope == "all":
        roots.append(CORPUS / "images")
        roots.append(CORPUS / "nocturne")
    index: list[tuple[str, int]] = []
    for root in roots:
        if not root.is_dir():
            continue
        for p in sorted(root.iterdir()):
            if p.is_dir(): continue
            if p.suffix.lower() not in IMG_EXTS: continue
            try:
                raw = p.read_bytes()
                h = dhash(raw)
            except Exception:
                h = None
            if h is not None:
                index.append((p.stem, h))
    return index


def find_corpus_duplicate(phash: int | None,
                           index: list[tuple[str, int]],
                           threshold: int = 8) -> str | None:
    """Return the id of an existing item whose pHash is within Hamming
    threshold of the given phash, else None."""
    if phash is None:
        return None
    from corpus_web_search import hamming
    for existing_id, existing_h in index:
        if hamming(existing_h, phash) <= threshold:
            return existing_id
    return None


def run_auto_commit(creator: dict, *, max_results: int = 40, phash_limit: int = 30,
                     query_override: str | None = None,
                     confidence_min: str = "medium",
                     require_cluster: bool = False,
                     max_budget_usd: float | None = None,
                     budget_tracker: dict | None = None,
                     max_long_edge: int = 4096,
                     default_citation: str | None = None,
                     dry_run: bool = False) -> tuple[int, dict]:
    """Harvest + vision + commit in one shot. No operator gating.

    Returns (exit_code, stats_dict). When called from run_auto_commit_all a
    shared budget_tracker dict keeps the running cost across creators.
    """
    # 1. Run the harvest pipeline
    try:
        creator, representatives, rejected, query, total = _harvest_pipeline(
            creator, max_results=max_results, phash_limit=phash_limit,
            query_override=query_override)
    except Exception as e:
        sys.stderr.write(f"auto-commit: harvest failed: {e}\n")
        return 1, {"error": str(e)}

    cid = str(creator.get("id") or "")
    name = str(creator.get("name") or "")
    surname = creator_surname(creator)

    min_rank = CONFIDENCE_RANK.get(confidence_min, 1)
    citation = default_citation or (
        f"{name}, personal-library reproduction, web-sourced; archival record held by operator"
    )
    dest_parent = CORPUS / "personal_library"
    dest_parent.mkdir(parents=True, exist_ok=True)
    seen_urls = _existing_source_urls()

    tax = load_taxonomy_keys()
    used_ids = existing_sidecar_ids()

    # Cross-corpus semantic-duplicate index (dHash of every personal_library image).
    # Built once per auto-commit invocation; O(N) in existing images.
    phash_index = build_existing_phash_index(scope="personal_library")
    print(f"  existing-phash index: {len(phash_index)} entries (personal_library)")

    client = None
    if not dry_run:
        try:
            client = _anthropic_client()
        except RuntimeError as e:
            sys.stderr.write(f"auto-commit: {e}\n")
            return 2, {"error": str(e)}
    system_prompt = VISION_SYSTEM_PROMPT_TEMPLATE.format(taxonomy=load_taxonomy_for_prompt())

    budget_tracker = budget_tracker if budget_tracker is not None else {"total_cost": 0.0}

    committed: list[dict] = []
    rejected_by_vision: list[dict] = []
    errors: list[dict] = []
    skipped_low_conf: list[dict] = []
    skipped_no_cluster: list[dict] = []
    skipped_already: list[dict] = []
    skipped_duplicate: list[dict] = []
    retries_used = 0
    decisions_ids: list[str] = []

    print(f"  auto-commit: {len(representatives)} gate-passing candidates; "
          f"min confidence='{confidence_min}'; require_cluster={require_cluster}")

    for idx, cand in enumerate(representatives, 1):
        local_id = f"c{idx:02d}"
        decisions_ids.append(local_id)
        prefix = f"  [{idx}/{len(representatives)}] {local_id}"

        # Cluster-corroboration gate (if required, pre-vision to save cost)
        if require_cluster and (cand.cluster_size or 1) < 2:
            print(f"{prefix}: SKIP (cluster_size={cand.cluster_size or 1}; --require-cluster)")
            skipped_no_cluster.append({"local_id": local_id, "image_url": cand.image_url,
                                         "cluster_size": cand.cluster_size})
            continue

        # Dedup against what's already in the corpus — URL match first (cheap)
        if cand.image_url in seen_urls or cand.source_url in seen_urls:
            print(f"{prefix}: SKIP (source_url already in corpus)")
            skipped_already.append({"local_id": local_id, "image_url": cand.image_url})
            continue

        # Dedup by pHash against the existing corpus (catches same-image-different-URL)
        dup = find_corpus_duplicate(cand.phash, phash_index, threshold=8)
        if dup:
            print(f"{prefix}: SKIP (semantic duplicate of existing '{dup}')")
            skipped_duplicate.append({"local_id": local_id, "duplicate_of": dup,
                                       "image_url": cand.image_url})
            continue

        if max_budget_usd is not None and budget_tracker["total_cost"] + VISION_COST_USD > max_budget_usd:
            print(f"{prefix}: BUDGET EXHAUSTED (${budget_tracker['total_cost']:.4f} + "
                  f"{VISION_COST_USD} > ${max_budget_usd})")
            errors.append({"local_id": local_id, "reason": "budget_exhausted"})
            break

        if dry_run:
            print(f"{prefix}: DRY-RUN — would vision-tag and commit {cand.image_url}")
            continue

        # Download (full-res, may resize if > max_long_edge)
        try:
            raw, ext, full_w, full_h = download_image(cand.image_url, max_long_edge=max_long_edge)
        except Exception as e:
            print(f"{prefix}: DOWNLOAD-FAILED ({e})")
            errors.append({"local_id": local_id, "image_url": cand.image_url,
                            "reason": f"download_failed: {e}"})
            continue

        # Vision
        try:
            vr = vision_tag(raw, creator_name=name, title_hint=cand.title or "",
                            source_url=cand.source_url or "",
                            system_prompt=system_prompt, client=client)
        except Exception as e:
            print(f"{prefix}: VISION-ERROR ({e})")
            errors.append({"local_id": local_id, "image_url": cand.image_url,
                            "reason": f"vision_error: {e}"})
            continue
        budget_tracker["total_cost"] += VISION_COST_USD

        if vr.get("status") == "reject":
            reason = vr.get("reject_reason") or "unknown"
            print(f"{prefix}: VISION-REJECTED ({reason})")
            rejected_by_vision.append({"local_id": local_id, "image_url": cand.image_url,
                                        "reason": reason, "notes": vr.get("notes", "")})
            continue

        conf = vr.get("confidence", "low")
        if CONFIDENCE_RANK.get(conf, -1) < min_rank:
            print(f"{prefix}: SKIP (confidence={conf} < {confidence_min})")
            skipped_low_conf.append({"local_id": local_id, "image_url": cand.image_url,
                                      "confidence": conf, "title_proposal": vr.get("title"),
                                      "notes": vr.get("notes", "")})
            continue

        errs = validate_vision_response(vr, tax)
        if errs:
            # Retry once with the validation errors fed back to Claude.
            if max_budget_usd is not None and budget_tracker["total_cost"] + VISION_COST_USD > max_budget_usd:
                print(f"{prefix}: TAX-VALIDATION-FAILED + BUDGET (no retry): {errs}")
                errors.append({"local_id": local_id, "image_url": cand.image_url,
                                "reason": f"taxonomy_errors: {errs}"})
                continue
            print(f"{prefix}: taxonomy-validation failed on first pass ({errs}); retrying with correction prompt …")
            try:
                vr_retry = vision_tag_retry(
                    raw, creator_name=name, title_hint=cand.title or "",
                    source_url=cand.source_url or "",
                    system_prompt=system_prompt, client=client,
                    prior_response=vr, errors=errs,
                )
                retries_used += 1
                budget_tracker["total_cost"] += VISION_COST_USD
            except Exception as e:
                print(f"{prefix}: VISION-RETRY-ERROR ({e})")
                errors.append({"local_id": local_id, "image_url": cand.image_url,
                                "reason": f"retry_vision_error: {e}; first-pass errors: {errs}"})
                continue
            # Retry may still reject or still fail validation; handle both.
            if vr_retry.get("status") == "reject":
                reason = vr_retry.get("reject_reason") or "unknown"
                print(f"{prefix}: VISION-REJECTED on retry ({reason})")
                rejected_by_vision.append({"local_id": local_id, "image_url": cand.image_url,
                                            "reason": reason, "notes": vr_retry.get("notes", "")})
                continue
            errs2 = validate_vision_response(vr_retry, tax)
            if errs2:
                print(f"{prefix}: TAX-VALIDATION-FAILED after retry: {errs2}")
                errors.append({"local_id": local_id, "image_url": cand.image_url,
                                "reason": f"taxonomy_errors_after_retry: {errs2}; first-pass: {errs}"})
                continue
            vr = vr_retry  # retry salvaged; proceed to commit with corrected tags
            print(f"{prefix}: retry succeeded; committing")

        item_id = generate_sidecar_id(
            surname=surname, title=vr["title"], existing=used_ids,
            creator_id=cid, local_id=local_id)
        used_ids.add(item_id)

        bin_path = dest_parent / f"{item_id}{ext}"
        if bin_path.exists():
            errors.append({"local_id": local_id, "reason": "collision_binary"})
            continue
        bin_path.write_bytes(raw)
        sha = hashlib.sha256(raw).hexdigest()
        mime = MIME_BY_EXT.get(ext, "application/octet-stream")

        sidecar = build_harvest_sidecar(
            item_id=item_id, creator_name=name,
            title=vr["title"], year=vr.get("year"),
            source_url=cand.source_url or cand.image_url or "",
            citation=citation,
            width=full_w, height=full_h,
            form=vr["form"], panel_fidelity=vr["panel_fidelity"],
            themes=vr["themes"], mood=vr["mood"], register=vr["register"],
            notes=vr.get("notes", ""),
            claude_confidence=vr.get("confidence"))
        sidecar_path = dest_parent / f"{item_id}.yaml"
        if sidecar_path.exists():
            bin_path.unlink(missing_ok=True)
            errors.append({"local_id": local_id, "reason": "collision_sidecar"})
            continue
        sidecar_path.write_text(yaml.safe_dump(sidecar, sort_keys=False,
                                                 allow_unicode=True, default_flow_style=False))
        append_manifest_entry(bin_path, mime=mime, sha256=sha, size=len(raw))
        seen_urls.add(cand.source_url or cand.image_url)
        # Update in-memory index so later items in this run also dedup against just-committed items.
        new_phash = dhash(raw)
        if new_phash is not None:
            phash_index.append((item_id, new_phash))

        committed.append({"local_id": local_id, "id": item_id,
                          "title": vr["title"], "year": vr.get("year"),
                          "confidence": conf, "size": f"{full_w}×{full_h}",
                          "cluster_size": cand.cluster_size or 1})
        print(f"{prefix}: ✓ committed as '{item_id}' — {vr['title']} "
              f"({vr.get('year', '?')}, conf={conf})")

    # Write artifacts (post-hoc audit trail)
    d = _write_harvest_artifacts(creator, query, total, representatives, rejected,
                                  decisions_ids, representatives)
    # Mirror the commit outcomes into decisions.yaml with accept flags set true/false
    # so the batch dir is a complete audit record.
    dec_lines = [
        f"# Auto-commit decisions for: {name} ({cid})",
        f"# Generated by `corpus harvest --auto-commit`.",
        f"",
        f"creator: {cid}",
        f"mode: auto-commit",
        f"confidence_min: {confidence_min}",
        f"require_cluster: {str(require_cluster).lower()}",
        f"decisions:",
    ]
    committed_local_ids = {c["local_id"] for c in committed}
    for i, cand in enumerate(representatives):
        lid = decisions_ids[i]
        accepted = lid in committed_local_ids
        safe_title = str(cand.title or "").replace('"', "'").replace("\n", " ").strip()[:180]
        dec_lines += [
            f"  - local_id: {lid}",
            f"    accept: {str(accepted).lower()}",
            f"    width: {cand.width}",
            f"    height: {cand.height}",
            f"    host: {cand.host}",
            f"    ddg_rank: {cand.ddg_rank}",
            f"    cluster: {cand.cluster_id}",
            f"    cluster_size: {cand.cluster_size}",
            f'    title: "{safe_title}"',
            f"    image_url: {cand.image_url}",
            f"    source_url: {cand.source_url}",
            "",
        ]
    (d / "decisions.yaml").write_text("\n".join(dec_lines))

    # Commit report
    report_lines = [
        f"# Auto-commit report — {name}",
        "",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Mode: auto-commit (confidence_min={confidence_min}, require_cluster={require_cluster})",
        f"Representatives: {len(representatives)}",
        f"Committed: {len(committed)}",
        f"Rejected by vision: {len(rejected_by_vision)}",
        f"Skipped (low confidence): {len(skipped_low_conf)}",
        f"Skipped (no cluster): {len(skipped_no_cluster)}",
        f"Skipped (URL already ingested): {len(skipped_already)}",
        f"Skipped (pHash duplicate of existing item): {len(skipped_duplicate)}",
        f"Taxonomy-retry calls: {retries_used}",
        f"Errors: {len(errors)}",
        f"",
        f"## Committed ({len(committed)})",
        f"",
    ]
    for c in committed:
        report_lines.append(
            f"- `{c['id']}` — {c['title']} ({c.get('year') or '?'}) · "
            f"{c['size']} · conf={c['confidence']} · cluster={c['cluster_size']}"
        )
    report_lines += ["", f"## Rejected by Claude-vision ({len(rejected_by_vision)})", ""]
    for r in rejected_by_vision:
        report_lines.append(f"- {r['local_id']}: `{r['reason']}` — {r.get('notes','')}")
    report_lines += ["", f"## Skipped — low confidence ({len(skipped_low_conf)})", ""]
    for s in skipped_low_conf:
        report_lines.append(
            f"- {s['local_id']}: conf={s.get('confidence','?')} · "
            f"proposed title={s.get('title_proposal','?')} · {s.get('notes','')}"
        )
    if skipped_no_cluster:
        report_lines += ["", f"## Skipped — no cluster ({len(skipped_no_cluster)})", ""]
        for s in skipped_no_cluster:
            report_lines.append(f"- {s['local_id']}: cluster_size={s.get('cluster_size')}")
    if skipped_already:
        report_lines += ["", f"## Skipped — URL already ingested ({len(skipped_already)})", ""]
        for s in skipped_already:
            report_lines.append(f"- {s['local_id']}: {s.get('image_url')}")
    if skipped_duplicate:
        report_lines += ["", f"## Skipped — pHash duplicate of existing item ({len(skipped_duplicate)})", ""]
        for s in skipped_duplicate:
            report_lines.append(f"- {s['local_id']}: duplicate of `{s['duplicate_of']}` · {s.get('image_url')}")
    report_lines += ["", f"## Errors ({len(errors)})", ""]
    for e in errors:
        report_lines.append(f"- {e['local_id']}: {e['reason']}")
    report_lines += ["", f"## Cost (this creator)", "",
                     f"- Vision calls: {len(committed) + len(rejected_by_vision) + len(skipped_low_conf)}",
                     f"- Approximate cost (cumulative run): ${budget_tracker['total_cost']:.4f}"]
    (d / "commit-report.md").write_text("\n".join(report_lines) + "\n")

    stats = {
        "creator_id": cid, "creator_name": name,
        "candidates": len(representatives),
        "committed": len(committed),
        "vision_rejected": len(rejected_by_vision),
        "skipped_low_conf": len(skipped_low_conf),
        "skipped_no_cluster": len(skipped_no_cluster),
        "skipped_already": len(skipped_already),
        "skipped_duplicate": len(skipped_duplicate),
        "retries_used": retries_used,
        "errors": len(errors),
    }
    print(f"  creator summary: {stats['committed']} committed, "
          f"{stats['vision_rejected']} vision-rejected, "
          f"{stats['skipped_low_conf']} low-conf, {stats['errors']} errors")
    return (0 if not errors else 1), stats


def run_auto_commit_all(*, shortlist_path: Path,
                         confidence_min: str = "medium",
                         require_cluster: bool = False,
                         max_budget_usd: float | None = None,
                         max_long_edge: int = 4096,
                         skip_pioneers: bool = False,
                         only_missing: bool = False,
                         dry_run: bool = False) -> int:
    """Iterate every creator in the shortlist."""
    items = load_shortlist(shortlist_path)
    budget_tracker = {"total_cost": 0.0}
    per_creator: list[dict] = []
    print(f"→ auto-commit --all: {len(items)} creators in shortlist "
          f"({shortlist_path.relative_to(REPO_ROOT)})")
    if max_budget_usd is not None:
        print(f"  global budget: ${max_budget_usd}")
    for i, creator in enumerate(items, 1):
        lineage = str(creator.get("lineage") or "")
        if skip_pioneers and lineage == "pioneers":
            print(f"\n[{i}/{len(items)}] SKIP pioneer: {creator.get('id')} "
                  f"(lineage={lineage}; may need PD-connector routing)")
            continue
        if only_missing and creator.get("in_corpus", 0) > 0:
            print(f"\n[{i}/{len(items)}] SKIP already-in-corpus: {creator.get('id')} "
                  f"({creator.get('in_corpus')} items)")
            continue
        print(f"\n[{i}/{len(items)}] {creator.get('id')}")
        if max_budget_usd is not None and budget_tracker["total_cost"] >= max_budget_usd:
            print(f"  GLOBAL BUDGET EXHAUSTED (${budget_tracker['total_cost']:.4f}); stopping.")
            break
        try:
            _, stats = run_auto_commit(
                creator,
                confidence_min=confidence_min,
                require_cluster=require_cluster,
                max_budget_usd=max_budget_usd,
                budget_tracker=budget_tracker,
                max_long_edge=max_long_edge,
                dry_run=dry_run,
            )
            per_creator.append(stats)
        except Exception as e:
            sys.stderr.write(f"  creator {creator.get('id')} failed: {e}\n")
            per_creator.append({"creator_id": creator.get("id"), "error": str(e)})
        time.sleep(0.6)  # polite pacing between creators

    # Aggregate summary
    print("\n" + "=" * 72)
    print("AUTO-COMMIT AGGREGATE SUMMARY")
    print("=" * 72)
    total_committed = sum(s.get("committed", 0) for s in per_creator)
    total_rej = sum(s.get("vision_rejected", 0) for s in per_creator)
    total_lowconf = sum(s.get("skipped_low_conf", 0) for s in per_creator)
    total_errors = sum(s.get("errors", 0) for s in per_creator)
    print(f"Creators processed: {len(per_creator)}")
    print(f"Total committed:    {total_committed}")
    print(f"Vision-rejected:    {total_rej}")
    print(f"Low-confidence:     {total_lowconf}")
    print(f"Errors:             {total_errors}")
    print(f"Approximate cost:   ${budget_tracker['total_cost']:.4f}")
    # Write an aggregate report too
    agg = STAGING / f"harvest-all-{time.strftime('%Y%m%d-%H%M%S')}.md"
    lines = [
        "# Auto-commit aggregate report",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Shortlist: {shortlist_path.relative_to(REPO_ROOT)}",
        f"Confidence min: {confidence_min} · require_cluster: {require_cluster}",
        "",
        f"- Creators processed: {len(per_creator)}",
        f"- Total committed: {total_committed}",
        f"- Vision-rejected: {total_rej}",
        f"- Low-confidence skips: {total_lowconf}",
        f"- Errors: {total_errors}",
        f"- Approximate cost: ${budget_tracker['total_cost']:.4f}",
        "",
        "## Per-creator",
        "",
    ]
    for s in per_creator:
        if "error" in s:
            lines.append(f"- `{s['creator_id']}` — ERROR: {s['error']}")
        else:
            lines.append(
                f"- `{s['creator_id']}` ({s.get('creator_name','?')}): "
                f"{s.get('committed',0)} committed, "
                f"{s.get('vision_rejected',0)} vision-rejected, "
                f"{s.get('skipped_low_conf',0)} low-conf, "
                f"{s.get('errors',0)} errors")
    agg.write_text("\n".join(lines) + "\n")
    print(f"aggregate report: {agg.relative_to(REPO_ROOT)}")
    return 0 if total_errors == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(prog="corpus harvest",
                                  description="Photographer-level harvest-and-prune. Three modes: "
                                              "(1) default — produce contact sheet + decisions.yaml; "
                                              "(2) --commit — commit operator-accepted entries; "
                                              "(3) --auto-commit [--all] — skip operator review, "
                                              "commit everything that passes vision + confidence gate.")
    ap.add_argument("creator", nargs="?", default=None,
                    help="Creator id or name substring (omit with --auto-commit --all).")
    ap.add_argument("--shortlist", default=str(DEFAULT_SHORTLIST),
                    help=f"Path to Stage-1 shortlist YAML. Default: {DEFAULT_SHORTLIST.relative_to(REPO_ROOT)}")
    ap.add_argument("--query", default=None,
                    help='Override the DDG query (default: "<Creator> best photos").')
    ap.add_argument("--max-results", type=int, default=40,
                    help="Max DDG candidates to fetch (default 40).")
    ap.add_argument("--phash-limit", type=int, default=30,
                    help="Cap how many kept candidates get pHash-dedup'd (default 30).")
    ap.add_argument("--commit", action="store_true",
                    help="Read decisions.yaml from the creator's harvest batch and commit accepted items via Claude-vision tagging. Requires ANTHROPIC_API_KEY.")
    ap.add_argument("--auto-commit", action="store_true",
                    help="Skip operator review. Harvest, run Claude-vision on every gate-passing candidate, and commit those that pass the confidence + cluster gates. Requires ANTHROPIC_API_KEY.")
    ap.add_argument("--all", action="store_true",
                    help="With --auto-commit: iterate every creator in the shortlist. No `creator` positional argument needed.")
    ap.add_argument("--confidence-min", choices=["low", "medium", "high"], default="medium",
                    help="With --auto-commit: commit only items whose Claude-vision identification confidence is at least this level (default 'medium').")
    ap.add_argument("--require-cluster", action="store_true",
                    help="With --auto-commit: only commit items whose pHash cluster has ≥ 2 members (independent reputable domains corroborate the image).")
    ap.add_argument("--skip-pioneers", action="store_true",
                    help="With --auto-commit --all: skip creators born before 1900 (pioneers may need PD-connector routing, not web-fetch).")
    ap.add_argument("--only-missing", action="store_true",
                    help="With --auto-commit --all: skip creators that already have entries in the corpus (in_corpus > 0 in the shortlist).")
    ap.add_argument("--dry-run", action="store_true",
                    help="With --commit or --auto-commit: print the plan (no API calls, no writes).")
    ap.add_argument("--max-budget-usd", type=float, default=None,
                    help="Abort before exceeding this USD ceiling in Claude spend. With --all, the budget is global across all creators.")
    ap.add_argument("--max-long-edge", type=int, default=4096,
                    help="Resize images whose long edge exceeds this (default 4096).")
    ap.add_argument("--citation", type=str, default=None,
                    help="Override the default personal_library citation string.")
    args = ap.parse_args()

    # Populate ANTHROPIC_API_KEY from ha/secrets.yaml if env is empty.
    # Both --commit and --auto-commit need it; harmless for the read-side.
    _ensure_anthropic_key()

    if args.auto_commit and args.all:
        return run_auto_commit_all(
            shortlist_path=Path(args.shortlist),
            confidence_min=args.confidence_min,
            require_cluster=args.require_cluster,
            max_budget_usd=args.max_budget_usd,
            max_long_edge=args.max_long_edge,
            skip_pioneers=args.skip_pioneers,
            only_missing=args.only_missing,
            dry_run=args.dry_run,
        )

    if args.auto_commit:
        if not args.creator:
            sys.stderr.write("auto-commit: provide a creator id or use --all.\n")
            return 2
        try:
            items = load_shortlist(Path(args.shortlist))
            creator = find_creator(items, args.creator)
        except Exception as e:
            sys.stderr.write(f"auto-commit: {e}\n")
            return 2
        rc, _ = run_auto_commit(
            creator,
            max_results=args.max_results,
            phash_limit=args.phash_limit,
            query_override=args.query,
            confidence_min=args.confidence_min,
            require_cluster=args.require_cluster,
            max_budget_usd=args.max_budget_usd,
            max_long_edge=args.max_long_edge,
            default_citation=args.citation,
            dry_run=args.dry_run,
        )
        return rc

    if args.commit:
        try:
            items = load_shortlist(Path(args.shortlist))
            creator = find_creator(items, args.creator)
            cid = str(creator.get("id"))
        except Exception:
            cid = args.creator
        return run_commit(cid,
                          max_budget_usd=args.max_budget_usd,
                          max_long_edge=args.max_long_edge,
                          default_citation=args.citation,
                          dry_run=args.dry_run)

    if not args.creator:
        sys.stderr.write("harvest: missing creator argument.\n")
        return 2
    try:
        items = load_shortlist(Path(args.shortlist))
    except Exception as e:
        sys.stderr.write(f"harvest: {e}\n")
        return 2
    try:
        creator = find_creator(items, args.creator)
    except KeyError as e:
        sys.stderr.write(f"harvest: {e}\n")
        return 2

    return run_harvest(creator,
                       max_results=args.max_results,
                       phash_limit=args.phash_limit,
                       query_override=args.query)


if __name__ == "__main__":
    sys.exit(main())

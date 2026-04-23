"""corpus fetch-work — targeted per-work DDG fetch with query-expansion ladder.

For each Stage-2 checklist entry whose status is `pending`, try up to N
query variants in order, commit the first gate+vision-passing result.
Mark entries `checked` or `targeted-fetch-failed` after the ladder.

See openspec/changes/add-ingestion-automation/design.md §"Query-expansion
strategies" and tasks.md §15.

This module composes primitives from corpus_web_search and corpus_harvest —
it does not reimplement them.
"""
from __future__ import annotations
import argparse
import hashlib
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except ImportError:
    sys.stderr.write("corpus fetch-work: PyYAML is required.\n")
    sys.exit(2)

from corpus_web_search import (
    apply_gate, ddg_search, dhash, fetch_thumbnail, to_candidate,
)
# Reuse commit primitives from corpus_harvest so we don't drift.
from corpus_harvest import (
    MIME_BY_EXT, VISION_COST_USD, VISION_MODEL, VISION_SYSTEM_PROMPT_TEMPLATE,
    _anthropic_client, _ensure_anthropic_key, _media_type_from_bytes,
    _parse_vision_json,
    append_manifest_entry, build_existing_phash_index,
    build_harvest_sidecar, download_image,
    existing_sidecar_ids, find_corpus_duplicate,
    generate_sidecar_id, load_taxonomy_for_prompt, load_taxonomy_keys,
    make_vision_thumbnail,
    validate_vision_response, vision_tag, vision_tag_retry,
)
import base64
import json

REPO_ROOT = Path(__file__).resolve().parents[1]
CORPUS = REPO_ROOT / "corpus"
STAGING = CORPUS / "_staging"
EM_DASH = "\u2014"


# -- Query-expansion ladder -------------------------------------------------

def build_query_variants(entry: dict, creator_name: str) -> list[tuple[str, str, str | None]]:
    """Return [(label, query, orientation_override_or_None), ...].

    Variants in order per design.md:
      1. baseline            creator + em-dash + title
      2. with-year           adds year if present
      3. with-note           adds first 5 note words for disambiguation
      4. with-orient         uses the entry's orientation filter
      5. flipped-orient      tries the opposite orientation (reproduction
                             containers often flip the image's native aspect)
      6. site-magnum         site-restricted to magnumphotos.com
      7. site-moma           site-restricted to moma.org
      8. site-artblart       site-restricted to artblart.com
      9. listicle-iconic     "<creator> iconic photographs <distinctive-terms>"
     10. subject-only        distinctive-terms only (last resort)
    """
    title = (entry.get("title") or "").strip()
    year = entry.get("year")
    note = (entry.get("note") or "").strip()
    orient = entry.get("orientation")
    q_base = f"{creator_name} {EM_DASH} {title}"

    variants: list[tuple[str, str, str | None]] = []
    variants.append(("baseline", q_base, orient))

    if year:
        variants.append(("with-year", f"{q_base} {year}", orient))

    if note:
        note_terms = " ".join(note.split()[:5]).rstrip(".,;")
        variants.append(("with-note", f"{q_base} {note_terms}", orient))

    if orient:
        # Try the opposite orientation too; reproductions often flip
        flipped = {"tall": "wide", "wide": "tall", "square": None}.get(orient)
        if flipped:
            variants.append(("flipped-orient", q_base, flipped))
    else:
        # No orientation hint — try both
        variants.append(("try-tall", q_base, "tall"))
        variants.append(("try-wide", q_base, "wide"))

    # Site-restricted to high-trust archives
    for site in ("magnumphotos.com", "moma.org", "artblart.com"):
        variants.append((f"site-{site}", f"site:{site} {creator_name} {title}", None))

    # Listicle-phrase alternate
    variants.append(("listicle-iconic",
                      f"{creator_name} iconic photographs {title}", orient))

    # Subject-keyword-only last resort (risky; no surname)
    if len(title.split()) >= 2:
        variants.append(("subject-only", f"{title} {year or ''}".strip(), orient))

    return variants


# -- Targeted vision call with subject cross-check -------------------------

def vision_tag_for_targeted(image_bytes: bytes, *, creator_name: str,
                              expected_title: str, expected_note: str,
                              expected_year: Any, source_url: str,
                              system_prompt: str, client) -> dict:
    """Vision call for targeted fetch, with author + subject cross-checks.

    Decisioning is split across two fields in the response:

      status              "accept" iff the image is plausibly BY <creator_name>.
                          "reject" only when the author is wrong (or the image
                          is a portrait, book cover, exhibition poster, color-
                          dependent, not-a-work, unreadable).
      matches_expected    "yes" iff the image plausibly depicts the EXPECTED
                          WORK (same frame / series / project). "no" if it's
                          by the right author but a different work.

    Callers commit every `status: accept` result (the author is right; it's
    still a legit item by this creator). Stage-2 checklist entries are only
    ticked when matches_expected == "yes" — otherwise the entry stays pending
    and the commit is a "bonus" (a different legit work by the same creator).

    This matches the operator's stance: a right-author wrong-subject item is
    not a failure, it's serendipity. Subject misidentification only means we
    didn't fulfill *this specific* stage-2 entry; the item itself is kept.
    """
    image_bytes = make_vision_thumbnail(image_bytes)
    b64 = base64.standard_b64encode(image_bytes).decode("ascii")
    media_type = _media_type_from_bytes(image_bytes)
    user_text = (
        f"Expected creator: {creator_name}\n"
        f"Expected work title: {expected_title}\n"
        f"Expected year: {expected_year if expected_year is not None else '(unspecified)'}\n"
        f"Expected note: {expected_note or '(none)'}\n"
        f"Source page: {source_url or '(none)'}\n\n"
        f"Answer two questions:\n"
        f"  1. Is this image plausibly BY {creator_name}? (Reject only if it is "
        f"NOT by this creator, or is a portrait of the creator, a book cover, "
        f"an exhibition poster, a color-dependent composition, unreadable, or "
        f"not a work.)\n"
        f"  2. Regardless of #1, does the image depict the EXPECTED WORK above "
        f"(same subject / series / frame, not just the same creator)?\n\n"
        f"Output JSON only, per this schema:\n"
        f"{{\n"
        f'  "status": "accept" | "reject",\n'
        f'  "reject_reason": null | "wrong_creator" | "portrait_of_creator" | '
        f'"book_cover" | "exhibition_poster" | "color_dependent" | '
        f'"not_a_work" | "unreadable",\n'
        f'  "matches_expected": "yes" | "no",\n'
        f'  "title": <Claude-identified title — may differ from expected>,\n'
        f'  "year": <integer or null>,\n'
        f'  "themes": [<taxonomy keys>],\n'
        f'  "mood": [<taxonomy keys>],\n'
        f'  "register": [<taxonomy keys>],\n'
        f'  "form": <image-form key>,\n'
        f'  "panel_fidelity": "native" | "robust",\n'
        f'  "confidence": "high" | "medium" | "low",   // confidence in CREATOR attribution (not subject)\n'
        f'  "notes": <one-line curatorial note or reason for matches_expected=no>\n'
        f"}}\n"
    )
    resp = client.messages.create(
        model=VISION_MODEL,
        max_tokens=1500,
        system=[{"type": "text", "text": system_prompt,
                  "cache_control": {"type": "ephemeral"}}],
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


# -- Entry resolution -------------------------------------------------------

def load_stage2_file(path: Path) -> dict:
    try:
        return yaml.safe_load(path.read_text()) or {}
    except Exception as e:
        raise RuntimeError(f"stage-2 parse error: {path}: {e}")


def find_stage2_file_for_creator(creator_id: str) -> tuple[Path, dict]:
    """Return (path, loaded_doc) of the stage-2 file containing creator_id."""
    for p in sorted(STAGING.glob("works-*.yaml")):
        doc = load_stage2_file(p)
        if creator_id in (doc.get("creators") or {}):
            return p, doc
    raise KeyError(f"creator '{creator_id}' not in any corpus/_staging/works-*.yaml")


def pending_entries(creator_block: dict) -> list[dict]:
    return [e for e in (creator_block.get("works") or [])
            if e.get("status") not in ("checked", "targeted-fetch-failed", "dropped")
            and not e.get("in_corpus")]


# -- Core: try variants for one entry, commit on first success -------------

def attempt_entry(entry: dict, *, creator_meta: dict,
                   client, system_prompt: str, tax: dict[str, set[str]],
                   used_ids: set[str], phash_index: list[tuple[str, int]],
                   budget_tracker: dict, max_budget_usd: float | None,
                   max_long_edge: int, citation: str,
                   dest_parent: Path, dry_run: bool) -> dict:
    """Try each query variant. On first success, commit and return result.

    Returns {"outcome": "committed"|"failed"|"skipped"|"budget_exhausted",
              ... outcome-specific fields}.
    """
    creator_name = creator_meta["name"]
    surname = creator_meta["surname"]
    # lineage-specific DDG media-type filter: photo for photographers,
    # line for drawn art (manga, comic-strip, caricature, pen-and-ink)
    media_type = creator_meta.get("ddg_media_type", "photo")
    variants = build_query_variants(entry, creator_name)
    attempts_log: list[dict] = []

    for label, query, orientation in variants:
        if max_budget_usd is not None and budget_tracker["total_cost"] + VISION_COST_USD > max_budget_usd:
            return {"outcome": "budget_exhausted",
                     "entry_id": entry.get("id"),
                     "attempts": attempts_log}

        print(f"      variant '{label}' → {query!r} orient={orientation}")
        # DDG
        try:
            rows = ddg_search(query, orientation=orientation, max_results=20,
                              media_type=media_type)
        except Exception as e:
            attempts_log.append({"label": label, "query": query,
                                  "orientation": orientation,
                                  "result": f"ddg_error: {e}"})
            continue

        # Build + gate candidates
        cands = []
        for i, row in enumerate(rows, 1):
            c = to_candidate(i, row, surname)
            apply_gate(c)
            if c.reject_reason is None:
                cands.append(c)
        if not cands:
            attempts_log.append({"label": label, "query": query,
                                  "orientation": orientation,
                                  "result": "no_gate_passing_candidate"})
            continue

        # pHash the top 3; dedup against existing corpus
        top_to_hash = cands[:3]
        for c in top_to_hash:
            tb = fetch_thumbnail(c)
            if tb:
                c.phash = dhash(tb)
            time.sleep(0.05)

        # Filter out semantic duplicates of existing items
        def not_duplicate(c):
            return find_corpus_duplicate(c.phash, phash_index, threshold=8) is None
        filtered = [c for c in top_to_hash if not_duplicate(c)]
        if not filtered:
            dup = find_corpus_duplicate(top_to_hash[0].phash, phash_index, threshold=8)
            attempts_log.append({"label": label, "query": query,
                                  "orientation": orientation,
                                  "result": f"all_candidates_are_duplicates (top→ {dup})"})
            continue
        top = filtered[0]

        if dry_run:
            print(f"        DRY-RUN — would commit: {top.image_url} "
                  f"({top.width}x{top.height}, {top.host})")
            attempts_log.append({"label": label, "query": query,
                                  "orientation": orientation,
                                  "result": "dry_run_would_commit",
                                  "image_url": top.image_url})
            return {"outcome": "committed", "entry_id": entry.get("id"),
                    "via_variant": label, "dry_run": True,
                    "image_url": top.image_url, "attempts": attempts_log}

        # Download full image
        try:
            raw, ext, full_w, full_h = download_image(top.image_url,
                                                       max_long_edge=max_long_edge)
        except Exception as e:
            attempts_log.append({"label": label, "query": query,
                                  "orientation": orientation,
                                  "result": f"download_failed: {e}"})
            continue

        # Targeted vision call with subject cross-check
        try:
            vr = vision_tag_for_targeted(
                raw, creator_name=creator_name,
                expected_title=entry.get("title", ""),
                expected_note=entry.get("note", ""),
                expected_year=entry.get("year"),
                source_url=top.source_url or "",
                system_prompt=system_prompt, client=client,
            )
        except Exception as e:
            attempts_log.append({"label": label, "query": query,
                                  "orientation": orientation,
                                  "result": f"vision_error: {e}"})
            continue
        budget_tracker["total_cost"] += VISION_COST_USD

        if vr.get("status") == "reject":
            reason = vr.get("reject_reason") or "unknown"
            attempts_log.append({"label": label, "query": query,
                                  "orientation": orientation,
                                  "result": f"vision_rejected: {reason}",
                                  "notes": vr.get("notes", "")})
            continue

        # Author is accepted. The image is BY this creator. We'll commit it
        # regardless of whether the subject matches the expected work.
        matches_expected = vr.get("matches_expected") == "yes"

        # Taxonomy validation + retry
        errs = validate_vision_response(vr, tax)
        if errs:
            if max_budget_usd is not None and budget_tracker["total_cost"] + VISION_COST_USD > max_budget_usd:
                attempts_log.append({"label": label, "query": query,
                                      "result": f"tax_errors_and_budget: {errs}"})
                continue
            try:
                vr = vision_tag_retry(raw, creator_name=creator_name,
                                       title_hint=top.title or "",
                                       source_url=top.source_url or "",
                                       system_prompt=system_prompt, client=client,
                                       prior_response=vr, errors=errs)
                budget_tracker["total_cost"] += VISION_COST_USD
            except Exception as e:
                attempts_log.append({"label": label, "query": query,
                                      "result": f"retry_error: {e}"})
                continue
            if vr.get("status") == "reject":
                attempts_log.append({"label": label, "query": query,
                                      "result": f"vision_rejected_on_retry: {vr.get('reject_reason')}"})
                continue
            errs2 = validate_vision_response(vr, tax)
            if errs2:
                attempts_log.append({"label": label, "query": query,
                                      "result": f"tax_errors_after_retry: {errs2}"})
                continue

        # Confidence now refers to CREATOR attribution, not subject. Gate only
        # on low-confidence author attribution; subject mismatch is fine.
        conf = vr.get("confidence", "low")
        if conf == "low":
            attempts_log.append({"label": label, "query": query,
                                  "result": f"low_author_confidence: {vr.get('title','?')}"})
            continue

        # Commit
        item_id = generate_sidecar_id(surname=surname, title=vr["title"],
                                         existing=used_ids,
                                         creator_id=creator_meta["id"],
                                         local_id=label)
        used_ids.add(item_id)
        bin_path = dest_parent / f"{item_id}{ext}"
        if bin_path.exists():
            attempts_log.append({"label": label, "result": f"collision_binary: {bin_path.name}"})
            continue
        bin_path.write_bytes(raw)
        sha = hashlib.sha256(raw).hexdigest()
        mime = MIME_BY_EXT.get(ext, "application/octet-stream")

        sidecar = build_harvest_sidecar(
            item_id=item_id, creator_name=creator_name,
            title=vr["title"], year=vr.get("year"),
            source_url=top.source_url or top.image_url,
            citation=citation,
            width=full_w, height=full_h,
            form=vr["form"], panel_fidelity=vr["panel_fidelity"],
            themes=vr["themes"], mood=vr["mood"], register=vr["register"],
            notes=vr.get("notes", ""),
            claude_confidence=vr.get("confidence"),
        )
        sidecar_path = dest_parent / f"{item_id}.yaml"
        if sidecar_path.exists():
            bin_path.unlink(missing_ok=True)
            attempts_log.append({"label": label, "result": "collision_sidecar"})
            continue
        sidecar_path.write_text(yaml.safe_dump(sidecar, sort_keys=False,
                                                 allow_unicode=True, default_flow_style=False))
        append_manifest_entry(bin_path, mime=mime, sha256=sha, size=len(raw))
        # Update phash index so subsequent entries dedup against this one
        new_h = dhash(raw)
        if new_h is not None:
            phash_index.append((item_id, new_h))

        match_tag = "subject-match" if matches_expected else "bonus (wrong subject; right author)"
        print(f"        ✓ committed as '{item_id}' — {vr['title']} "
              f"({vr.get('year','?')}, conf={conf}, via variant '{label}') — {match_tag}")
        attempts_log.append({"label": label, "query": query,
                              "result": "committed",
                              "committed_id": item_id,
                              "matches_expected": matches_expected})
        outcome = "committed" if matches_expected else "committed_bonus"
        return {"outcome": outcome, "entry_id": entry.get("id"),
                 "committed_id": item_id, "via_variant": label,
                 "title": vr["title"], "year": vr.get("year"),
                 "confidence": conf, "matches_expected": matches_expected,
                 "attempts": attempts_log}

    return {"outcome": "failed", "entry_id": entry.get("id"),
             "variants_tried": [a["label"] for a in attempts_log],
             "attempts": attempts_log}


# -- Escalate over all pending entries for a creator ------------------------

def run_escalate(creator_id: str, *, entry_filter: str | None,
                  max_budget_usd: float | None,
                  max_long_edge: int,
                  citation_override: str | None,
                  dry_run: bool) -> int:
    try:
        stage2_path, stage2_doc = find_stage2_file_for_creator(creator_id)
    except KeyError as e:
        sys.stderr.write(f"fetch-work: {e}\n")
        return 2
    creator_block = (stage2_doc.get("creators") or {}).get(creator_id) or {}

    # Search all top-*.yaml shortlists for this creator (photographers,
    # contemporary-pen, and any future canons).
    creator_shortlist = None
    for shortlist_path in sorted(STAGING.glob("top-*.yaml")):
        shortlist = (yaml.safe_load(shortlist_path.read_text()) or {}).get("items", [])
        creator_shortlist = next((s for s in shortlist if s.get("id") == creator_id), None)
        if creator_shortlist:
            break
    if not creator_shortlist:
        sys.stderr.write(f"fetch-work: creator '{creator_id}' not in any corpus/_staging/top-*.yaml shortlist; can't resolve name/surname.\n")
        return 2
    # Decide DDG media-type from the creator's lineage in Stage-1 shortlist.
    lineage = creator_shortlist.get("lineage", "")
    drawn_lineages = {"manga", "comic-strip", "caricature", "xkcd",
                      "pen-and-ink", "contemporary", "fin-de-siecle",
                      "modernist-drawing", "japanese-ink", "old-master-print",
                      "19c-print", "german-expressionist", "american-20c-graphic"}
    ddg_media_type = "line" if lineage in drawn_lineages else "photo"

    creator_meta = {
        "id": creator_id,
        "name": creator_shortlist.get("name", creator_id),
        "surname": creator_shortlist.get("name", creator_id).split()[-1],
        "ddg_media_type": ddg_media_type,
    }

    entries = pending_entries(creator_block)
    if entry_filter:
        entries = [e for e in entries if e.get("id") == entry_filter]
        if not entries:
            sys.stderr.write(f"fetch-work: no pending entry with id='{entry_filter}' under creator '{creator_id}'\n")
            return 2

    if not entries:
        print(f"fetch-work: no pending entries for {creator_id}; nothing to do.")
        return 0

    print(f"→ fetch-work --escalate: {creator_meta['name']} ({creator_id})")
    print(f"  pending entries: {len(entries)}")
    if max_budget_usd is not None:
        print(f"  budget: ${max_budget_usd}")
    if dry_run:
        print(f"  (dry-run)")

    _ensure_anthropic_key()
    client = None
    if not dry_run:
        try:
            client = _anthropic_client()
        except RuntimeError as e:
            sys.stderr.write(f"fetch-work: {e}\n")
            return 2
    system_prompt = VISION_SYSTEM_PROMPT_TEMPLATE.format(taxonomy=load_taxonomy_for_prompt())
    tax = load_taxonomy_keys()
    used_ids = existing_sidecar_ids()
    phash_index = build_existing_phash_index(scope="personal_library")
    budget_tracker = {"total_cost": 0.0}
    citation = citation_override or (
        f"{creator_meta['name']}, personal-library reproduction, "
        f"web-sourced; archival record held by operator"
    )
    dest_parent = CORPUS / "personal_library"
    dest_parent.mkdir(parents=True, exist_ok=True)

    committed: list[dict] = []
    failed: list[dict] = []
    outcomes: list[dict] = []

    for i, entry in enumerate(entries, 1):
        eid = entry.get("id")
        print(f"\n  [{i}/{len(entries)}] {eid}  (title: {entry.get('title')})")
        outcome = attempt_entry(
            entry, creator_meta=creator_meta,
            client=client, system_prompt=system_prompt, tax=tax,
            used_ids=used_ids, phash_index=phash_index,
            budget_tracker=budget_tracker,
            max_budget_usd=max_budget_usd,
            max_long_edge=max_long_edge, citation=citation,
            dest_parent=dest_parent, dry_run=dry_run,
        )
        outcomes.append(outcome)

        if outcome["outcome"] == "committed":
            committed.append(outcome)
            if not dry_run:
                entry["status"] = "checked"
                entry["committed_id"] = outcome["committed_id"]
                entry["checked_by"] = f"targeted-fetch:{outcome.get('via_variant','?')}"
        elif outcome["outcome"] == "committed_bonus":
            # Right author, wrong subject. Keep the item (it's legit by this
            # creator) but leave stage-2 entry pending — the specific work
            # we searched for is still not in the corpus.
            committed.append(outcome)
            if not dry_run:
                entry["status"] = "targeted-fetch-wrong-subject"
                entry["bonus_committed_id"] = outcome["committed_id"]
                entry["bonus_committed_title"] = outcome.get("title")
        elif outcome["outcome"] == "budget_exhausted":
            print(f"      BUDGET EXHAUSTED; stopping.")
            failed.append(outcome)
            break
        else:
            failed.append(outcome)
            if not dry_run:
                entry["status"] = "targeted-fetch-failed"
                entry["targeted_fetch_variants_tried"] = outcome.get("variants_tried", [])

    # Write back the stage-2 YAML with updated statuses (block style, see reconcile note)
    if not dry_run and (committed or failed):
        stage2_path.write_text(yaml.safe_dump(stage2_doc, sort_keys=False,
                                                allow_unicode=True, default_flow_style=None))

    # Stats
    n_subject_match = sum(1 for c in committed if c.get("outcome") == "committed")
    n_bonus = sum(1 for c in committed if c.get("outcome") == "committed_bonus")
    report_path = STAGING / f"fetch-work-{creator_id}-{time.strftime('%Y%m%d-%H%M%S')}.md"
    report_lines = [
        f"# fetch-work --escalate report — {creator_meta['name']}",
        f"",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Pending entries attempted: {len(entries)}",
        f"Committed (subject match, stage-2 ticked): {n_subject_match}",
        f"Committed (bonus — right author, wrong subject, stage-2 left pending): {n_bonus}",
        f"Failed: {len(failed)}",
        f"Approximate cost: ${budget_tracker['total_cost']:.4f}",
        f"",
        f"## Committed — subject match (stage-2 entries ticked)",
        f"",
    ]
    for c in committed:
        if c.get("outcome") != "committed":
            continue
        report_lines.append(
            f"- `{c.get('entry_id')}` → `{c.get('committed_id')}` "
            f"(via `{c.get('via_variant')}`, conf={c.get('confidence','?')}): "
            f"{c.get('title','?')} ({c.get('year','?')})"
        )
    if n_bonus:
        report_lines += ["", "## Committed — bonus items (right author, different work)",
                          "Stage-2 entries for these remain `pending` (the specific work was not retrieved).", ""]
        for c in committed:
            if c.get("outcome") != "committed_bonus":
                continue
            report_lines.append(
                f"- searched for `{c.get('entry_id')}` → committed instead as "
                f"`{c.get('committed_id')}` "
                f"(via `{c.get('via_variant')}`, conf={c.get('confidence','?')}): "
                f"{c.get('title','?')} ({c.get('year','?')})"
            )
    report_lines += ["", "## Failed", ""]
    for f in failed:
        report_lines.append(f"- `{f.get('entry_id')}` — variants tried: "
                             f"{', '.join(f.get('variants_tried', []))}")
        for a in (f.get("attempts") or []):
            report_lines.append(f"    - `{a.get('label')}`: {a.get('result')}")
    report_path.write_text("\n".join(report_lines) + "\n")

    print()
    print(f"summary: {n_subject_match} subject-match committed (stage-2 ticked), "
          f"{n_bonus} bonus committed (right author, wrong subject — stage-2 pending), "
          f"{len(failed)} failed; cost ~${budget_tracker['total_cost']:.4f}")
    print(f"report: {report_path.relative_to(REPO_ROOT)}")
    if committed:
        print("run `corpus validate` to confirm the corpus is still clean.")
    return 0 if not failed else 1


def _creators_in_stage2() -> list[str]:
    """Collect every creator_id appearing in any stage-2 YAML."""
    ids: list[str] = []
    for p in sorted(STAGING.glob("works-*.yaml")):
        doc = load_stage2_file(p)
        for cid in (doc.get("creators") or {}).keys():
            if cid not in ids:
                ids.append(cid)
    return ids


def main() -> int:
    ap = argparse.ArgumentParser(prog="corpus fetch-work",
                                  description="Targeted per-work fetch via query-expansion ladder for Stage-2 entries.")
    ap.add_argument("--creator", default=None,
                    help="Creator id (e.g., 'sebastiao-salgado'). Omit with --all.")
    ap.add_argument("--all", action="store_true",
                    help="Iterate every creator that has pending stage-2 entries. Budget is global across creators.")
    ap.add_argument("--escalate", action="store_true",
                    help="Escalate over all pending entries for the creator.")
    ap.add_argument("--id", default=None,
                    help="Target a single entry-id. Single-creator only.")
    ap.add_argument("--max-budget-usd", type=float, default=None,
                    help="Abort before the next vision call that would exceed this cap.")
    ap.add_argument("--max-long-edge", type=int, default=4096,
                    help="Resize images whose long edge exceeds this.")
    ap.add_argument("--citation", type=str, default=None,
                    help="Override the default personal_library citation.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print the plan; no API calls, no writes.")
    args = ap.parse_args()

    if args.all:
        if args.id:
            sys.stderr.write("fetch-work: --all is incompatible with --id.\n")
            return 2
        creators = _creators_in_stage2()
        print(f"→ fetch-work --all: {len(creators)} creators in stage-2 files")
        if args.max_budget_usd is not None:
            print(f"  global budget: ${args.max_budget_usd}")
        rc_any = 0
        # Use a shared budget tracker via monkey-patching budget_tracker per call.
        # Simpler: we re-use run_escalate and pass the budget cap; run_escalate
        # creates its own tracker. To enforce a *global* budget across creators
        # we'd want a shared tracker — for this first rev we split the budget
        # evenly per creator as a rough cap.
        per_creator_budget = None
        if args.max_budget_usd is not None and creators:
            per_creator_budget = args.max_budget_usd / len(creators)
            print(f"  per-creator budget: ${per_creator_budget:.3f}")
        for i, cid in enumerate(creators, 1):
            print(f"\n[{i}/{len(creators)}] creator={cid}")
            try:
                rc = run_escalate(
                    creator_id=cid, entry_filter=None,
                    max_budget_usd=per_creator_budget,
                    max_long_edge=args.max_long_edge,
                    citation_override=args.citation,
                    dry_run=args.dry_run,
                )
            except Exception as e:
                sys.stderr.write(f"  creator {cid} failed: {e}\n")
                rc = 1
            if rc:
                rc_any = rc
            time.sleep(0.4)
        return rc_any

    if not args.creator:
        sys.stderr.write("fetch-work: supply --creator <id> or --all.\n")
        return 2
    if not args.escalate and not args.id:
        sys.stderr.write("fetch-work: supply --escalate (all pending) or --id <entry-id>.\n")
        return 2

    return run_escalate(
        creator_id=args.creator,
        entry_filter=args.id,
        max_budget_usd=args.max_budget_usd,
        max_long_edge=args.max_long_edge,
        citation_override=args.citation,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    sys.exit(main())

"""corpus reconcile-checklist — match committed sidecars against Stage-2 checklists.

Tiered matching per entry:
  1. Exact id match — committed sidecar id equals stage-2 entry id.
  2. Token-boundary match — distinctive title/note terms coincide between
     stage-2 entry and committed sidecar. Far more conservative than
     character-level fuzzy match.
  3. (optional, --vision) Claude-vision cross-check on uncertain matches.

Updates stage-2 YAML in place with `status`, `committed_id`, and `checked_by`
fields. Writes a reconciliation report to corpus/_staging/reconcile-<date>.md.

See openspec/changes/add-ingestion-automation/design.md §"Stage-2 as checklist"
and tasks.md §14.
"""
from __future__ import annotations
import argparse
import re
import sys
import time
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except ImportError:
    sys.stderr.write("corpus reconcile: PyYAML is required.\n")
    sys.exit(2)

REPO_ROOT = Path(__file__).resolve().parents[1]
CORPUS = REPO_ROOT / "corpus"
STAGING = CORPUS / "_staging"

# Distinctive-token matcher: strip stopwords, require length >= SHORT_MIN.
STOPWORDS = {
    "the", "a", "an", "of", "and", "or", "at", "in", "on", "for", "to", "with",
    "by", "from", "de", "la", "le", "les", "des", "du", "and", "et", "en", "di",
    "il", "das", "der", "die", "ein", "eine", "photographs", "photograph",
    "photo", "photos", "image", "images", "best",
}
SHORT_MIN = 4


def title_tokens(s: str) -> set[str]:
    """Distinctive tokens from a title/id (length >= 4, non-stopword, lowercased)."""
    return {t for t in re.findall(r"[\w']+", (s or "").lower())
            if len(t) >= SHORT_MIN and t not in STOPWORDS}


def load_yaml_safe(path: Path) -> dict:
    try:
        return yaml.safe_load(path.read_text()) or {}
    except Exception:
        return {}


def committed_for_creator(creator_name: str) -> list[dict]:
    """All sidecars whose `artist` field matches creator_name (case-insensitive)."""
    items: list[dict] = []
    for folder in ("personal_library", "personal_library/nocturne",
                    "images", "nocturne"):
        d = CORPUS / folder
        if not d.is_dir():
            continue
        for p in sorted(d.glob("*.yaml")):
            if p.name.startswith("EXAMPLE"):
                continue
            doc = load_yaml_safe(p)
            artist = (doc.get("artist") or "").lower().strip()
            if artist and artist == creator_name.lower().strip():
                items.append({
                    "id": doc["id"],
                    "title": doc.get("title") or "",
                    "year": doc.get("year"),
                    "path": p,
                    "folder": folder,
                })
    return items


def match_entry(entry: dict, committed: list[dict],
                 already_matched: set[str],
                 creator_tokens: set[str] | None = None) -> dict | None:
    """Tiered match for one stage-2 entry. Returns {sidecar, confidence, shared_tokens?}.

    creator_tokens: tokens from the creator's name/surname that are guaranteed
    to appear in every committed sidecar's id (because ids are surname-prefixed).
    They add no disambiguation signal and are excluded from the shared-token
    count to avoid false positives where every item "shares" the surname.
    """
    creator_tokens = creator_tokens or set()
    eid = str(entry.get("id", ""))
    etitle = str(entry.get("title", ""))
    enote = str(entry.get("note", ""))

    # Tier 1: exact id match
    for c in committed:
        if c["id"] in already_matched:
            continue
        if c["id"] == eid:
            return {"sidecar": c, "confidence": "exact"}

    # Tier 2: token-boundary match
    entry_tokens = title_tokens(f"{eid} {etitle} {enote}") - creator_tokens
    if len(entry_tokens) < 2:
        return None
    best = None
    best_count = 0
    best_shared = set()
    for c in committed:
        if c["id"] in already_matched:
            continue
        committed_tokens = title_tokens(f"{c['id']} {c['title']}") - creator_tokens
        shared = entry_tokens & committed_tokens
        # Require:
        #   - >= 2 shared distinctive tokens (neither of which is the creator name), AND
        #   - at least one shared token of length >= 6 (to avoid short-word coincidences
        #     like "camp" or "series" dominating the match).
        if len(shared) < 2:
            continue
        if not any(len(t) >= 6 for t in shared):
            continue
        if len(shared) > best_count:
            best = c
            best_count = len(shared)
            best_shared = shared
    if best:
        return {"sidecar": best, "confidence": "token",
                "shared_tokens": sorted(best_shared)}
    return None


def reconcile_creators_in_file(path: Path, *, creator_filter: str | None = None,
                                 shortlist_index: dict[str, str],
                                 dry_run: bool) -> list[dict]:
    """Reconcile every creator in a stage-2 file (or just creator_filter if set).

    shortlist_index maps creator_id -> creator_name (used to find committed
    sidecars). Returns a list of per-creator stats.
    """
    doc = load_yaml_safe(path)
    creators_map = doc.get("creators") or {}
    stats: list[dict] = []
    file_modified = False

    for creator_id, creator_entry in creators_map.items():
        if creator_filter and creator_id != creator_filter:
            continue
        creator_name = shortlist_index.get(creator_id) or creator_id.replace("-", " ").title()
        committed = committed_for_creator(creator_name)
        # Tokens guaranteed to appear in every committed sidecar id for this
        # creator (surname-prefixed). Exclude from shared-token scoring.
        creator_tokens = title_tokens(f"{creator_id} {creator_name}")
        works = creator_entry.get("works") or []
        matched_ids: set[str] = set()
        per_creator = {
            "creator_id": creator_id,
            "creator_name": creator_name,
            "committed_count": len(committed),
            "total_entries": len(works),
            "exact": 0,
            "token": 0,
            "pending": 0,
            "carried_forward": 0,   # already-checked in prior run
            "unmatched": [],
            "checked": [],
            "extras": [],           # committed items not mapped to any stage-2 entry
        }

        for entry in works:
            # Skip entries already checked in a previous run; preserve them.
            if entry.get("status") == "checked" and entry.get("committed_id"):
                matched_ids.add(entry["committed_id"])
                per_creator["carried_forward"] += 1
                continue

            # Stage-2 entries that claim `in_corpus: true` should be id-exact-matched.
            # If that fails, fall through to token match.
            match = match_entry(entry, committed, matched_ids, creator_tokens)
            if match:
                sidecar = match["sidecar"]
                entry["status"] = "checked"
                entry["committed_id"] = sidecar["id"]
                entry["checked_by"] = f"reconcile-{match['confidence']}"
                matched_ids.add(sidecar["id"])
                if match["confidence"] == "exact":
                    per_creator["exact"] += 1
                else:
                    per_creator["token"] += 1
                per_creator["checked"].append({
                    "stage2_id": entry.get("id"),
                    "committed_id": sidecar["id"],
                    "confidence": match["confidence"],
                    "shared_tokens": match.get("shared_tokens", []),
                })
                file_modified = True
            else:
                if "status" not in entry:
                    entry["status"] = "pending"
                    file_modified = True
                per_creator["pending"] += 1
                per_creator["unmatched"].append({
                    "stage2_id": entry.get("id"),
                    "title": entry.get("title", ""),
                    "note": entry.get("note", ""),
                })

        # Extras: committed sidecars for this creator that didn't map anywhere
        for c in committed:
            if c["id"] not in matched_ids:
                per_creator["extras"].append({
                    "id": c["id"], "title": c["title"], "year": c["year"],
                })

        stats.append(per_creator)

    if file_modified and not dry_run:
        # PyYAML's default_flow_style=None auto-picks per-node. The existing
        # stage-2 files used flow-style inline dicts; they will come out in
        # block style after the dump. Operators: this is a status-fields
        # addition, not a semantic change.
        path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True,
                                         default_flow_style=None))
    return stats


def load_shortlist_index() -> dict[str, str]:
    """id -> name from corpus/_staging/top-50-bw-photographers.yaml (if present)."""
    p = STAGING / "top-50-bw-photographers.yaml"
    if not p.exists():
        return {}
    doc = load_yaml_safe(p)
    return {str(i.get("id")): str(i.get("name", ""))
            for i in (doc.get("items") or []) if i.get("id")}


def write_report(all_stats: list[dict], out_path: Path) -> None:
    total_entries = sum(s["total_entries"] for s in all_stats)
    total_checked = sum(s["exact"] + s["token"] + s["carried_forward"] for s in all_stats)
    total_pending = sum(s["pending"] for s in all_stats)
    pct = (100 * total_checked / total_entries) if total_entries else 0

    lines = [
        f"# Reconcile-checklist report",
        "",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        f"- Creators processed: {len(all_stats)}",
        f"- Total stage-2 entries: {total_entries}",
        f"- Checked: **{total_checked}** ({pct:.0f}%)",
        f"- Pending (no match): **{total_pending}**",
        "",
        "## Per creator",
        "",
    ]
    for s in sorted(all_stats, key=lambda x: x["creator_id"]):
        n_checked = s["exact"] + s["token"] + s["carried_forward"]
        n_total = s["total_entries"]
        pct_c = (100 * n_checked / n_total) if n_total else 0
        lines.append(
            f"### {s['creator_name']} (`{s['creator_id']}`)"
        )
        lines.append("")
        lines.append(
            f"- checked: **{n_checked}/{n_total}** ({pct_c:.0f}%)  "
            f"[exact={s['exact']}, token={s['token']}, carried_forward={s['carried_forward']}]"
        )
        lines.append(f"- pending: {s['pending']}")
        lines.append(f"- committed sidecars for this creator: {s['committed_count']}")
        lines.append(f"- extras (committed but not in stage-2 checklist): {len(s['extras'])}")
        if s["checked"]:
            lines.append("")
            lines.append("**Matches** (how each stage-2 entry got ticked):")
            lines.append("")
            for c in s["checked"]:
                tok = f" ({', '.join(c['shared_tokens'])})" if c.get("shared_tokens") else ""
                lines.append(f"- `{c['stage2_id']}` → `{c['committed_id']}` · {c['confidence']}{tok}")
        if s["unmatched"]:
            lines.append("")
            lines.append("**Unmatched stage-2 entries** (candidates for `fetch-work --escalate`):")
            lines.append("")
            for u in s["unmatched"]:
                lines.append(f"- `{u['stage2_id']}` — {u['title']}")
                if u["note"]:
                    lines.append(f"    note: {u['note']}")
        if s["extras"]:
            lines.append("")
            lines.append("**Extras** (committed but not matched to any stage-2 entry):")
            lines.append("")
            for e in s["extras"]:
                lines.append(f"- `{e['id']}` — [{e.get('year') or '?'}] {e['title']}")
        lines.append("")

    out_path.write_text("\n".join(lines) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(prog="corpus reconcile-checklist",
                                  description="Match committed sidecars against Stage-2 checklists.")
    ap.add_argument("--creator", default=None,
                    help="Reconcile only one creator (by id). Default: all creators in all stage-2 files.")
    ap.add_argument("--file", default=None,
                    help="Reconcile only the given stage-2 file (path). Default: every corpus/_staging/works-*.yaml.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print matches; do not modify stage-2 YAML files.")
    ap.add_argument("--out", default=None,
                    help="Report output path (default: corpus/_staging/reconcile-<date>.md).")
    args = ap.parse_args()

    shortlist_index = load_shortlist_index()

    if args.file:
        stage2_files = [Path(args.file)]
    else:
        stage2_files = sorted(STAGING.glob("works-*.yaml"))

    if not stage2_files:
        sys.stderr.write("reconcile: no stage-2 files found under corpus/_staging/works-*.yaml\n")
        return 2

    print(f"→ reconcile: {len(stage2_files)} stage-2 file(s)"
          f"{', filtering to creator=' + args.creator if args.creator else ''}"
          f"{' (dry-run)' if args.dry_run else ''}")

    all_stats: list[dict] = []
    for path in stage2_files:
        print(f"\n  {path.relative_to(REPO_ROOT)}")
        stats = reconcile_creators_in_file(
            path, creator_filter=args.creator,
            shortlist_index=shortlist_index, dry_run=args.dry_run,
        )
        for s in stats:
            n_checked = s["exact"] + s["token"] + s["carried_forward"]
            print(f"    {s['creator_name']:<30} "
                  f"checked={n_checked}/{s['total_entries']} "
                  f"(exact={s['exact']} token={s['token']} carry={s['carried_forward']}) "
                  f"pending={s['pending']} extras={len(s['extras'])}")
        all_stats.extend(stats)

    # Summary
    total_entries = sum(s["total_entries"] for s in all_stats)
    total_checked = sum(s["exact"] + s["token"] + s["carried_forward"] for s in all_stats)
    total_pending = sum(s["pending"] for s in all_stats)
    print()
    print(f"aggregate: {total_checked}/{total_entries} checked "
          f"({100*total_checked/total_entries if total_entries else 0:.0f}%), "
          f"{total_pending} pending")

    out = Path(args.out) if args.out else STAGING / f"reconcile-{time.strftime('%Y-%m-%d-%H%M%S')}.md"
    write_report(all_stats, out)
    print(f"report: {out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

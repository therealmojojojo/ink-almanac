"""corpus dedup — pairwise pHash scan to surface duplicates and near-duplicates.

Computes dHash-8 for every image binary in the given scope and reports
pairs within configurable Hamming thresholds.

  - Hamming 0–8   → probable same image (compression / small crop variation).
                    Auto-delete candidate: keep higher-resolution member.
  - Hamming 9–15  → near-duplicate (plausibly same frame; worth operator eye).
                    Flagged, never auto-deleted.
  - Hamming > 15  → not considered.

Ops:

  corpus dedup                       # report across all personal_library
  corpus dedup --creator <surname>   # filter to one creator
  corpus dedup --scope all           # include corpus/images + nocturne
  corpus dedup --delete-exact-dups   # DESTRUCTIVE: auto-drop the smaller of
                                      # each Hamming≤8 pair (and manifest entry)
  corpus dedup --near-threshold 12   # tune the near-dup upper bound

Does NOT touch:
  - corpus/texts/ (no binaries)
  - sidecars without a matching binary on disk
  - items in corpus/_staging/
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

try:
    import yaml  # type: ignore
except ImportError:
    sys.stderr.write("corpus dedup: PyYAML is required.\n")
    sys.exit(2)

from corpus_web_search import dhash, hamming

REPO_ROOT = Path(__file__).resolve().parents[1]
CORPUS = REPO_ROOT / "corpus"
MANIFEST = CORPUS / "_manifest.json"
IMG_EXTS = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp")


def scope_roots(scope: str) -> list[Path]:
    if scope == "personal_library":
        return [CORPUS / "personal_library",
                CORPUS / "personal_library" / "nocturne"]
    if scope == "all":
        return [CORPUS / "personal_library",
                CORPUS / "personal_library" / "nocturne",
                CORPUS / "images",
                CORPUS / "nocturne"]
    raise ValueError(f"unknown scope: {scope!r}")


def index_images(scope: str, creator_filter: str | None = None) -> list[dict]:
    """Build an index of every image binary in scope, with dhash + dims + artist."""
    entries: list[dict] = []
    for root in scope_roots(scope):
        if not root.is_dir():
            continue
        for p in sorted(root.iterdir()):
            if not p.is_file() or p.suffix.lower() not in IMG_EXTS:
                continue
            sidecar = p.with_suffix(".yaml")
            if not sidecar.exists():
                continue
            try:
                d = yaml.safe_load(sidecar.read_text()) or {}
            except Exception:
                continue
            artist = (d.get("artist") or "").strip()
            if creator_filter and creator_filter.lower() not in artist.lower() and creator_filter.lower() not in p.stem.lower():
                continue
            try:
                h = dhash(p.read_bytes())
            except Exception:
                h = None
            if h is None:
                continue
            entries.append({
                "id": p.stem,
                "path": p,
                "sidecar": sidecar,
                "artist": artist,
                "dhash": h,
                "w": d.get("pixel_width") or 0,
                "h": d.get("pixel_height") or 0,
                "title": d.get("title") or "",
            })
    return entries


def scan_pairs(entries: list[dict], near_threshold: int) -> tuple[list[tuple], list[tuple]]:
    exact: list[tuple] = []   # (a, b, hamming)  Hamming ≤ 8
    near: list[tuple] = []    # 9 ≤ Hamming ≤ near_threshold
    n = len(entries)
    for i in range(n):
        for j in range(i + 1, n):
            a, b = entries[i], entries[j]
            # Only compare within-creator — across-creator pHash matches are
            # almost always incidental composition similarity, not duplicates.
            if a["artist"] and b["artist"] and a["artist"].lower() != b["artist"].lower():
                continue
            h = hamming(a["dhash"], b["dhash"])
            if h <= 8:
                exact.append((a, b, h))
            elif h <= near_threshold:
                near.append((a, b, h))
    return exact, near


def decide_drop(a: dict, b: dict) -> tuple[dict, dict]:
    """Given a confirmed duplicate pair, return (keeper, dropper) by resolution."""
    area_a = a["w"] * a["h"]
    area_b = b["w"] * b["h"]
    if area_a >= area_b:
        return a, b
    return b, a


def manifest_strip(paths_to_strip: set[str]) -> int:
    if not paths_to_strip or not MANIFEST.exists():
        return 0
    doc = json.loads(MANIFEST.read_text())
    before = len(doc.get("entries", []))
    doc["entries"] = [e for e in doc.get("entries", [])
                       if e.get("path") not in paths_to_strip]
    MANIFEST.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    return before - len(doc["entries"])


def format_pair(a: dict, b: dict, ham: int) -> str:
    return (f"  [ham={ham}]  {a['id']:<55} ({a['w']}x{a['h']})\n"
            f"              {b['id']:<55} ({b['w']}x{b['h']})")


def main() -> int:
    ap = argparse.ArgumentParser(prog="corpus dedup",
                                  description="Pairwise pHash scan to surface duplicates and near-duplicates.")
    ap.add_argument("--scope", choices=["personal_library", "all"],
                    default="personal_library",
                    help="Folders to scan (default: personal_library).")
    ap.add_argument("--creator", default=None,
                    help="Filter to one creator (matched against artist field + id prefix).")
    ap.add_argument("--near-threshold", type=int, default=15,
                    help="Upper Hamming bound for near-duplicate reporting (default 15).")
    ap.add_argument("--delete-exact-dups", action="store_true",
                    help="DESTRUCTIVE: auto-delete the smaller member of each Hamming≤8 pair (sidecar + binary + manifest entry).")
    ap.add_argument("--dry-run", action="store_true",
                    help="With --delete-exact-dups: print the plan without deleting.")
    args = ap.parse_args()

    print(f"→ corpus dedup: scope={args.scope}"
          f"{', creator=' + args.creator if args.creator else ''}")
    entries = index_images(args.scope, args.creator)
    print(f"  indexed {len(entries)} image binaries")
    if not entries:
        return 0

    exact, near = scan_pairs(entries, args.near_threshold)
    print(f"  probable duplicates (Hamming ≤ 8):   {len(exact)}")
    print(f"  near-duplicates   (Hamming 9–{args.near_threshold}): {len(near)}")

    if exact:
        print()
        print("== PROBABLE DUPLICATES ==")
        for a, b, h in exact:
            keeper, dropper = decide_drop(a, b)
            print(format_pair(a, b, h))
            print(f"              → keep {keeper['id']}, drop {dropper['id']}")
    if near:
        print()
        print(f"== NEAR-DUPLICATES (operator review; none auto-dropped) ==")
        for a, b, h in near:
            print(format_pair(a, b, h))

    # Destructive path
    if args.delete_exact_dups and exact:
        print()
        print(f"== DELETING {len(exact)} EXACT DUPLICATES ==" +
              ("  (dry-run)" if args.dry_run else ""))
        droppers = []
        strip_paths: set[str] = set()
        for a, b, _ in exact:
            _, dropper = decide_drop(a, b)
            # Skip if already queued (chains of duplicates)
            if dropper["id"] in {d["id"] for d in droppers}:
                continue
            droppers.append(dropper)
            rel = dropper["path"].relative_to(REPO_ROOT).as_posix()
            strip_paths.add(rel)
        for d in droppers:
            msg = f"  drop {d['id']} ({d['w']}x{d['h']})  {d['path'].name} + {d['sidecar'].name}"
            print(msg)
            if not args.dry_run:
                d["path"].unlink(missing_ok=True)
                d["sidecar"].unlink(missing_ok=True)
        if not args.dry_run:
            stripped = manifest_strip(strip_paths)
            print(f"  manifest: stripped {stripped} entr{'y' if stripped==1 else 'ies'}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

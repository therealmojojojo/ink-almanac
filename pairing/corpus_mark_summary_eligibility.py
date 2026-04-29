"""Mark every text sidecar with an explicit `summary_eligible` field.

Walks corpus/texts/ and corpus/personal_library/. For each text sidecar
with a non-empty body, computes the renderer's fit tier (mirror of
`renderer/src/modes/summary.ts:pickFitTier`) and decides what value to
write:

  - tier 1-5 (pill-parity, ≥28u): `summary_eligible: true` if absent;
    existing values (true or false) are preserved — operator intent
    wins for items that already carry the field.
  - tier 6-7 (sub-pill, <28u):  `summary_eligible: false` always —
    the renderer can fit them, but only via the sub-pill escape, so
    they should not compete for the summary delight cell. Existing
    `false` is left as-is; existing `true` is flipped to `false`;
    absent is filled in.

Default invocation is dry-run; pass `--apply` to write changes.
"""
from __future__ import annotations

import argparse
import math
import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
FOLDERS = [REPO / "corpus" / "texts", REPO / "corpus" / "personal_library"]

# Mirror renderer/src/modes/summary.ts:DELIGHT_TIERS verbatim.
# (tier, font_u, line_height_u, soft_cpl, max_visual_lines)
DELIGHT_TIERS: dict[int, tuple[int, int, int, int]] = {
    1: (36, 48, 34,  7),
    2: (32, 44, 38,  8),
    3: (30, 40, 41,  9),
    4: (28, 34, 44, 11),
    5: (28, 30, 44, 12),
    6: (24, 32, 52, 11),
    7: (22, 28, 57, 13),
}
PILL_FLOOR = (1, 2, 3, 4, 5)
WRAP_AT_FLOOR = (4, 5)
SUB_FLOOR = (6, 7)


def visual_lines_at(lines: list[str], cpl: int) -> int:
    return sum(max(1, math.ceil(len(ln) / cpl)) for ln in lines)


def pick_fit_tier(body: str) -> int | None:
    lines = [ln.rstrip() for ln in body.splitlines() if ln.strip()]
    if not lines:
        return None
    longest = max(len(ln) for ln in lines)
    n = len(lines)
    for t in PILL_FLOOR:
        _, _, cpl, mvl = DELIGHT_TIERS[t]
        if longest <= cpl and n <= mvl:
            return t
    for t in WRAP_AT_FLOOR:
        _, _, cpl, mvl = DELIGHT_TIERS[t]
        if visual_lines_at(lines, cpl) <= mvl:
            return t
    for t in SUB_FLOOR:
        _, _, cpl, mvl = DELIGHT_TIERS[t]
        if longest <= cpl and n <= mvl:
            return t
    return 7  # last-resort fallback (matches summary.ts)


def get_body(doc: dict) -> str:
    if doc.get("text"):
        return doc["text"]
    tv = doc.get("text_variants") or {}
    if isinstance(tv, dict) and tv:
        return tv.get("en") or next(iter(tv.values()))
    return ""


_FIELD_RE = re.compile(r"(?m)^summary_eligible:\s*(true|false)\s*$")


def write_field(text: str, value: bool) -> tuple[str, str]:
    """Insert / replace a top-level `summary_eligible:` line. Returns
    (new_text, action). Action is one of: 'set', 'replace', 'noop'."""
    yaml_value = "true" if value else "false"
    m = _FIELD_RE.search(text)
    if m:
        if m.group(1) == yaml_value:
            return text, "noop"
        new = text[: m.start()] + f"summary_eligible: {yaml_value}" + text[m.end() :]
        return new, "replace"
    # Append at end (consistent with how the prior session marked items).
    if not text.endswith("\n"):
        text = text + "\n"
    return text + f"summary_eligible: {yaml_value}\n", "set"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Write changes (default: dry-run)")
    args = ap.parse_args()

    stats = {
        "scanned": 0,
        "no_body": 0,
        "tier_hist": {1:0,2:0,3:0,4:0,5:0,6:0,7:0},
        "set_true_filled": 0,
        "set_false_filled": 0,
        "set_false_replaced_true": 0,
        "preserved_existing_true": 0,
        "preserved_existing_false": 0,
        "noop": 0,
    }
    flips: list[tuple[Path, int, str]] = []

    for folder in FOLDERS:
        for p in sorted(folder.glob("*.yaml")):
            if "EXAMPLE" in p.name:
                continue
            try:
                doc = yaml.safe_load(p.read_text())
            except Exception:
                continue
            if not isinstance(doc, dict):
                continue
            if not (doc.get("text") or doc.get("text_variants")):
                continue
            body = get_body(doc) or ""
            if not body.strip():
                stats["no_body"] += 1
                continue

            stats["scanned"] += 1
            tier = pick_fit_tier(body)
            if tier is None:
                continue
            stats["tier_hist"][tier] += 1

            current = doc.get("summary_eligible", None)  # explicit-only; default not assumed
            text = p.read_text()

            if tier in PILL_FLOOR:
                # tier 1-5: fill if absent; preserve existing values
                if current is None:
                    new_text, _ = write_field(text, True)
                    if new_text != text:
                        stats["set_true_filled"] += 1
                        if args.apply:
                            p.write_text(new_text)
                elif current is True:
                    stats["preserved_existing_true"] += 1
                else:
                    stats["preserved_existing_false"] += 1
            else:
                # tier 6-7: false always; preserve existing false; flip existing true; fill absent
                if current is None:
                    new_text, _ = write_field(text, False)
                    if new_text != text:
                        stats["set_false_filled"] += 1
                        flips.append((p, tier, "absent→false"))
                        if args.apply:
                            p.write_text(new_text)
                elif current is True:
                    new_text, _ = write_field(text, False)
                    stats["set_false_replaced_true"] += 1
                    flips.append((p, tier, "true→false"))
                    if args.apply:
                        p.write_text(new_text)
                else:
                    stats["preserved_existing_false"] += 1

    print(f"Scanned text sidecars (with body): {stats['scanned']}")
    print(f"  empty body / skipped:            {stats['no_body']}")
    print()
    print("Tier histogram:")
    for t in (1, 2, 3, 4, 5, 6, 7):
        font = DELIGHT_TIERS[t][0]
        zone = "pill-parity" if t in PILL_FLOOR else "sub-pill"
        print(f"  tier {t} ({font}u, {zone:<11}): {stats['tier_hist'][t]:>4}")
    print()
    print("Field actions:")
    print(f"  filled-in true  (tier 1-5, was absent):  {stats['set_true_filled']}")
    print(f"  filled-in false (tier 6-7, was absent):  {stats['set_false_filled']}")
    print(f"  flipped true → false (tier 6-7):         {stats['set_false_replaced_true']}")
    print(f"  preserved existing true:                  {stats['preserved_existing_true']}")
    print(f"  preserved existing false:                 {stats['preserved_existing_false']}")
    print()
    print(f"Mode: {'APPLY (changes written)' if args.apply else 'DRY-RUN (no changes)'}")

    if flips:
        print()
        print(f"Items where the field changes (tier 6/7, {len(flips)} total):")
        for p, tier, action in flips:
            print(f"  tier {tier}  {action:<12}  {p.relative_to(REPO)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

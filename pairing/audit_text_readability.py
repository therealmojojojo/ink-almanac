"""
One-shot readability audit across the corpus.

For every text in `corpus/texts/` and `corpus/personal_library/`, predicts the
size it would render at in each of the three text-bearing zones, and classifies
the risk against the operator's readability thresholds:

  - OK     ≥ 30u  (sweet spot is 30-32u)
  - AMBER  25-29u (legible but past the sweet spot)
  - RED    < 25u or visibly overflows at the floor

Zones modelled (all measurements in `u` = 1px):

  1. summary.delight   457 × 408  static per-form size, no auto-fit, soft-wrap.
                       sonnet/free-verse/stanzaic/prose-poem already at 28u.
  2. gallery_text      1056 × ~620 (after title + attrib clearance).
                       Dynamic step-down via the empirical fit table that
                       validate-corpus-fit.ts already uses.
  3. summary.smart_pill 437 × 408  Plex Sans, 9-step ladder by char count.
                       Sourced from each text's `smart_pill.body` (LLM-authored).

The point is to surface where the same text reads comfortably in one zone but
poorly in another — e.g. a sonnet at 28u in summary.delight that would land at
32u in gallery_text. That difference drives steps 1, 2, 4 of the larger plan.
"""

from __future__ import annotations

import math
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable

import yaml

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus"
TEXT_DIRS = ["texts", "personal_library"]
TRIPLETS_DIR = CORPUS / "_triplets"

# --- summary.delight design intent ------------------------------------------
# The cell is sized for short forms: 4-5 lines of quote / aphorism / haiku /
# tanka / single stanza. Anything longer is misrouted regardless of whether
# the renderer can squeeze it in.
DELIGHT_LINE_BUDGET = 5  # operator's stated intent
DELIGHT_SHORT_FORMS = {"haiku", "tanka", "aphorism", "quote", "fragment"}


# --- Gallery-text fit (mirrors renderer/src/tools/validate-corpus-fit.ts) ----

GALLERY_BUDGET_WITH_TITLE = {
    54: {1: (7, 36),  2: (14, 16)},
    52: {1: (7, 37),  2: (14, 17)},
    48: {1: (8, 40),  2: (16, 18)},
    44: {1: (9, 44),  2: (18, 20)},
    42: {1: (9, 45),  2: (16, 21)},
    36: {1: (11, 53), 2: (20, 24)},
    32: {1: (12, 60), 2: (22, 27)},
    28: {1: (14, 68), 2: (24, 31)},
    25: {1: (16, 76), 2: (28, 35)},
}

GALLERY_DEFAULT_SIZE = {
    "haiku": 54, "tanka": 54,
    "aphorism": 52,
    "fragment": 48,
    "quote": 44,
    "sonnet": 42, "free-verse": 42, "stanzaic": 42, "lyric": 42, "song": 42,
    "prose-poem": 36,
}
GALLERY_STEP_DOWN = [42, 36, 32, 28, 25]


def fit_gallery(lines: int, max_chars: int, form: str) -> tuple[int, int] | None:
    base = GALLERY_DEFAULT_SIZE.get(form, 42)
    sizes = [base] + [s for s in GALLERY_STEP_DOWN if s < base]
    for size in sizes:
        for cols in (1, 2):
            max_l, max_c = GALLERY_BUDGET_WITH_TITLE[size][cols]
            if lines <= max_l and max_chars <= max_c:
                return (size, cols)
    return None


# --- Summary-delight fit (mirrors renderer/templates/summary/summary.css) ---

# (size_u, line_height_u) per form. Static; no auto-fit today.
DELIGHT_RULE = {
    "haiku":      (36, 52),
    "tanka":      (36, 52),
    "fragment":   (36, 48),
    "aphorism":   (36, 48),
    "quote":      (34, 46),
    "sonnet":     (28, 40),
    "free-verse": (28, 40),
    "stanzaic":   (28, 40),
    "prose-poem": (28, 40),
}
# Delight cell geometry derived from summary.css:
#   bottom-band content area = 1200 - 2×48 (face pad) = 1104u
#   bottom-band gap = 28u → 1076u splits 1.45 : 1
#     delight cell width  = 1076 × 1.45/2.45 ≈ 637u
#     smart-pill cell     = 1076 × 1.00/2.45 ≈ 439u (source uses 437u)
#   .summary-delight has padding-right: 28u → body inner width ≈ 609u.
DELIGHT_W = 609
DELIGHT_H = 408
FRAUNCES_CHAR_W = 0.50  # AVG_CHAR_WIDTH_FACTOR in typography.ts

# --- bilingual haiku geometry (anthology layout in summary.css) -------------
# .anthology .body uses `grid-template-columns: auto auto`, so each column
# shrink-wraps to its longest line. The constraint is the SUM:
#   JA_max × 40u  +  40u gap  +  EN_max × (32u × 0.5)  ≤  DELIGHT_W
# JA = Noto Serif JP 40u (CJK glyphs ~1em wide), EN = Fraunces 32u, both at
# 56u line-height → 7 rows max in the 408u cell.
ANTH_GAP_U = 40
ANTH_JA_SIZE = 40
ANTH_EN_SIZE = 32
ANTH_LH = 56
ANTH_MAX_ROWS = math.floor(DELIGHT_H / ANTH_LH)               # = 7


def visual_lines(body_lines: list[str], size: int) -> int:
    """Soft-wrap each logical line to the cell width and sum the visual rows."""
    chars_per_line = math.floor(DELIGHT_W / (size * FRAUNCES_CHAR_W))
    if chars_per_line <= 0:
        return 10**6
    total = 0
    any_wrapped = False
    for ln in body_lines:
        n = len(ln)
        if n == 0:
            total += 1  # blank line still consumes a row in pre-line
        else:
            rows = max(1, math.ceil(n / chars_per_line))
            if rows > 1:
                any_wrapped = True
            total += rows
    return total, any_wrapped, chars_per_line


def fit_delight(form: str, body_lines: list[str]) -> dict:
    rule = DELIGHT_RULE.get(form, (28, 40))  # unknown forms get the worst case
    size, lh = rule
    rows, wrapped, cpl = visual_lines(body_lines, size)
    cap_rows = math.floor(DELIGHT_H / lh)
    overflow = rows > cap_rows
    return {
        "size": size,
        "line_height": lh,
        "wrapped": wrapped,         # True if any logical line had to soft-wrap
        "rows": rows,
        "cap_rows": cap_rows,
        "chars_per_line": cpl,
        "overflow": overflow,
    }


# --- Smart-pill fit (mirrors renderer/src/modes/summary.ts) -----------------

PILL_LADDER = [36, 32, 30, 28, 26, 25, 23, 21, 19]
PILL_W = 437
PILL_H = 408
PLEX_CHAR_W = 0.55
PILL_LH_RATIO = 1.35


def fit_pill(char_count: int) -> int:
    for size in PILL_LADDER:
        cpl = math.floor(PILL_W / (size * PLEX_CHAR_W))
        rows = math.floor(PILL_H / (size * PILL_LH_RATIO))
        if char_count <= cpl * rows:
            return size
    return PILL_LADDER[-1]


# --- Risk classification ----------------------------------------------------

def classify(size: int | None, overflow: bool) -> str:
    if size is None or overflow or size < 25:
        return "RED"
    if size < 30:
        return "AMBER"
    return "OK"


# --- Driver -----------------------------------------------------------------

def body_stats(body: str) -> tuple[int, int, list[str]]:
    raw = [l.rstrip() for l in body.replace("\r\n", "\n").split("\n")]
    nonblank = [l for l in raw if l.strip()]
    max_chars = max((len(l) for l in nonblank), default=0)
    return len(nonblank), max_chars, raw


def iter_text_yamls() -> Iterable[Path]:
    for sub in TEXT_DIRS:
        d = CORPUS / sub
        if not d.exists():
            continue
        for p in sorted(d.glob("*.yaml")):
            if p.name.startswith("EXAMPLE"):
                continue
            yield p


def qualifies_for_delight(form: str, lines: int) -> bool:
    """Operator's design intent: short forms only, 4-5 lines max.

    Haiku/tanka qualify by canonical line count.
    Aphorism/quote/fragment qualify if ≤5 lines.
    Sonnet/free-verse/stanzaic/prose-poem qualify only if heavily excerpted
    down to ≤5 lines (a short stanza, not the full poem).
    """
    if form in {"haiku", "tanka"}:
        return True
    return lines <= DELIGHT_LINE_BUDGET


def fits_delight_at_form_size(form: str, body_lines: list[str]) -> bool:
    """At the form's static size, the body fits without soft-wrap and without
    exceeding the row cap. Soft-wrap is treated as a fail because (a) it
    breaks haiku/tanka/sonnet metrical lines and (b) for short forms the
    operator wants the line break to be the intended one, not a width spill."""
    rule = DELIGHT_RULE.get(form, (28, 40))
    size, lh = rule
    rows, wrapped, _ = visual_lines(body_lines, size)
    return (not wrapped) and rows <= math.floor(DELIGHT_H / lh)


def haiku_bilingual_fit(ja: str, en: str) -> dict:
    """Test whether a JA original and EN translation render side-by-side at
    the anthology layout. With `grid-template-columns: auto auto`, columns
    shrink-wrap to their longest line, so the real constraint is the row
    width sum:  JA_max × 40u + 40u gap + EN_max × (32u × 0.5) ≤ DELIGHT_W.

    Per-row baseline alignment also requires the same line count on both
    sides (otherwise auto-auto pairs them by row index but one side runs
    short).
    """
    ja_lines = [l for l in ja.replace("\r\n", "\n").split("\n") if l.strip()]
    en_lines = [l for l in en.replace("\r\n", "\n").split("\n") if l.strip()]
    ja_max = max((len(l) for l in ja_lines), default=0)
    en_max = max((len(l) for l in en_lines), default=0)
    width_used = ja_max * ANTH_JA_SIZE + ANTH_GAP_U + en_max * (ANTH_EN_SIZE * FRAUNCES_CHAR_W)
    width_overflow = width_used > DELIGHT_W
    n_rows = max(len(ja_lines), len(en_lines))
    line_mismatch = len(ja_lines) != len(en_lines)
    fits = (not width_overflow) and (not line_mismatch) and n_rows <= ANTH_MAX_ROWS
    return {
        "ja_lines": len(ja_lines),
        "en_lines": len(en_lines),
        "ja_max": ja_max,
        "en_max": en_max,
        "width_used": int(round(width_used)),
        "width_budget": DELIGHT_W,
        "width_overflow": width_overflow,
        "line_mismatch": line_mismatch,
        "rows_used": n_rows,
        "fits_side_by_side": fits,
    }


def load_used_summary_text_ids() -> set[str]:
    """Text ids that appear as the `summary` slot in a visual-day triplet —
    i.e. texts that have actually been routed into summary.delight."""
    used: set[str] = set()
    if not TRIPLETS_DIR.exists():
        return used
    for p in TRIPLETS_DIR.glob("*.yaml"):
        if p.name.startswith("EXAMPLE"):
            continue
        with p.open() as f:
            try:
                doc = yaml.safe_load(f)
            except yaml.YAMLError:
                continue
        if not isinstance(doc, dict):
            continue
        if doc.get("flavor") != "visual-day":
            continue
        s = doc.get("summary")
        if isinstance(s, str):
            used.add(s)
    return used


def main() -> int:
    rows = []
    pill_rows = []
    seen_smart_pill = 0
    used_in_delight = load_used_summary_text_ids()
    haiku_rows = []

    for path in iter_text_yamls():
        with path.open() as f:
            try:
                doc = yaml.safe_load(f)
            except yaml.YAMLError as e:
                print(f"# parse error: {path.name}: {e}", file=sys.stderr)
                continue
        if not isinstance(doc, dict):
            continue
        form = doc.get("form")
        variants = doc.get("text_variants") or {}
        if not form or not variants:
            continue

        # Pick the variant we'll render. EN preferred for audit clarity.
        lang = "en" if "en" in variants else next(iter(variants))
        body = variants[lang]
        if not isinstance(body, str):
            continue
        lines, max_chars, raw_lines = body_stats(body)

        # Gallery-text
        gfit = fit_gallery(lines, max_chars, form)
        gsize = gfit[0] if gfit else None
        gcols = gfit[1] if gfit else None
        g_class = classify(gsize, overflow=gfit is None)

        # Summary-delight
        d = fit_delight(form, [l for l in raw_lines if l.strip()])
        d_class = classify(d["size"], overflow=d["overflow"])
        # Wrap-without-overflow on a strict-line form (haiku/tanka/sonnet) is
        # itself a content failure even if rows don't exceed the cap.
        if d["wrapped"] and form in {"haiku", "tanka", "sonnet"}:
            d_class = "RED"

        text_id = doc.get("id") or path.stem
        rows.append({
            "id": text_id,
            "form": form,
            "lang": lang,
            "lines": lines,
            "max_chars": max_chars,
            "gallery_size": gsize,
            "gallery_cols": gcols,
            "gallery_class": g_class,
            "delight_size": d["size"],
            "delight_rows": d["rows"],
            "delight_cap": d["cap_rows"],
            "delight_wrapped": d["wrapped"],
            "delight_overflow": d["overflow"],
            "delight_class": d_class,
            "qualifies_delight": qualifies_for_delight(form, lines),
            "fits_delight_static": fits_delight_at_form_size(form, [l for l in raw_lines if l.strip()]),
            "used_in_delight": text_id in used_in_delight,
        })

        # Bilingual haiku side-by-side check (operator design goal)
        if form in {"haiku", "tanka"} and "ja" in variants and "en" in variants:
            ja, en = variants["ja"], variants["en"]
            if isinstance(ja, str) and isinstance(en, str):
                fit = haiku_bilingual_fit(ja, en)
                fit["id"] = text_id
                fit["form"] = form
                fit["used"] = text_id in used_in_delight
                haiku_rows.append(fit)

        # Smart-pill (only if the YAML carries one)
        sp = doc.get("smart_pill") or {}
        sp_body = sp.get("body") if isinstance(sp, dict) else None
        if isinstance(sp_body, str) and sp_body.strip():
            seen_smart_pill += 1
            psize = fit_pill(len(sp_body))
            p_class = classify(psize, overflow=False)
            pill_rows.append({
                "id": doc.get("id") or path.stem,
                "chars": len(sp_body),
                "size": psize,
                "class": p_class,
            })

    # ---- summary.delight focus (operator's design intent) ----
    print(f"\n=== summary.delight focus ===\n")
    n_total = len(rows)
    n_used = sum(1 for r in rows if r["used_in_delight"])
    n_qual = sum(1 for r in rows if r["qualifies_delight"])
    n_qual_and_fits = sum(1 for r in rows if r["qualifies_delight"] and r["fits_delight_static"])
    n_used_and_qual = sum(1 for r in rows if r["used_in_delight"] and r["qualifies_delight"])
    n_used_misrouted = sum(1 for r in rows if r["used_in_delight"] and not r["qualifies_delight"])
    n_used_overflows = sum(1 for r in rows if r["used_in_delight"] and r["delight_class"] == "RED")

    print(f"Corpus has {n_total} texts. {n_used} have actually been routed into summary.delight (= summary slot of a visual-day triplet).\n")
    print(f"  qualifies for delight (short-form OR ≤{DELIGHT_LINE_BUDGET} lines): {n_qual:>4} / {n_total}  ({100*n_qual/n_total:.1f}%)")
    print(f"  qualifies AND fits at form's static size, no soft-wrap:        {n_qual_and_fits:>4} / {n_total}  ({100*n_qual_and_fits/n_total:.1f}%)")
    print(f"  USED in delight:                                                {n_used:>4}")
    print(f"    of which qualify (short-form OR ≤{DELIGHT_LINE_BUDGET} lines):           {n_used_and_qual:>4}  ({100*n_used_and_qual/max(n_used,1):.1f}%)")
    print(f"    of which are MISROUTED (long form forced into the cell):     {n_used_misrouted:>4}  ({100*n_used_misrouted/max(n_used,1):.1f}%)")
    print(f"    of which RENDER as RED (overflow / strict-form wrap):        {n_used_overflows:>4}  ({100*n_used_overflows/max(n_used,1):.1f}%)")

    # Form breakdown of currently-used delight texts
    print(f"\n  Form distribution of currently-used delight texts:")
    used_forms = Counter(r["form"] for r in rows if r["used_in_delight"])
    for form, n in used_forms.most_common():
        ok = sum(1 for r in rows if r["used_in_delight"] and r["form"] == form and r["delight_class"] == "OK")
        red = sum(1 for r in rows if r["used_in_delight"] and r["form"] == form and r["delight_class"] == "RED")
        print(f"    {form:<12} {n:>4}   (OK {ok}, RED {red})")

    print(f"\n  Form distribution of texts that QUALIFY (the eligible pool):")
    qual_forms = Counter(r["form"] for r in rows if r["qualifies_delight"])
    for form, n in qual_forms.most_common():
        print(f"    {form:<12} {n:>4}")

    # Misrouted = used in delight despite not qualifying (long-form bodies).
    misrouted = [r for r in rows if r["used_in_delight"] and not r["qualifies_delight"]]
    misrouted.sort(key=lambda r: -r["lines"])
    if misrouted:
        print(f"\n  --- {len(misrouted)} misrouted: long-form text used as delight companion ---")
        print(f"  {'id':<46} {'form':<11} {'lines':>5} {'maxC':>4}  delight verdict")
        for r in misrouted[:60]:
            d_overflow = " OVF" if r["delight_overflow"] else (" wrap" if r["delight_wrapped"] else "")
            print(f"  {r['id']:<46} {r['form']:<11} {r['lines']:>5} {r['max_chars']:>4}  {r['delight_size']}u{d_overflow} {r['delight_class']}")
        if len(misrouted) > 60:
            print(f"  ... and {len(misrouted)-60} more")

    # ---- bilingual haiku/tanka side-by-side fit ----
    if haiku_rows:
        print(f"\n=== haiku/tanka bilingual side-by-side fit ===\n")
        print(f"Geometry: delight body width {DELIGHT_W}u (auto-auto columns), gap {ANTH_GAP_U}u, "
              f"JA {ANTH_JA_SIZE}u (CJK ≈1em), EN {ANTH_EN_SIZE}u Fraunces (≈{FRAUNCES_CHAR_W}em), "
              f"{ANTH_LH}u line-height → {ANTH_MAX_ROWS} rows max.")
        print(f"Fits side-by-side iff: ja_max × 40 + 40 + en_max × 16 ≤ {DELIGHT_W}.\n")
        n_h = len(haiku_rows)
        n_h_fit = sum(1 for h in haiku_rows if h["fits_side_by_side"])
        n_h_width = sum(1 for h in haiku_rows if h["width_overflow"])
        n_h_mismatch = sum(1 for h in haiku_rows if h["line_mismatch"])
        n_h_used = sum(1 for h in haiku_rows if h["used"])
        n_h_used_fit = sum(1 for h in haiku_rows if h["used"] and h["fits_side_by_side"])
        print(f"  haiku/tanka with both JA + EN:                   {n_h:>4}")
        print(f"  fit side-by-side (sum-width OK, lines match):    {n_h_fit:>4}  ({100*n_h_fit/max(n_h,1):.1f}%)")
        print(f"  exceed width budget (forces EN to wrap):         {n_h_width:>4}")
        print(f"  JA/EN line count mismatch:                       {n_h_mismatch:>4}")
        print(f"  used in delight (visual-day triplets):           {n_h_used:>4}")
        print(f"    of which fit side-by-side:                     {n_h_used_fit:>4}  ({100*n_h_used_fit/max(n_h_used,1):.1f}%)")

        bad = [h for h in haiku_rows if not h["fits_side_by_side"]]
        bad.sort(key=lambda h: (not h["used"], -h["width_used"]))
        if bad:
            print(f"\n  --- bilingual haiku/tanka that won't fit side-by-side ({len(bad)}) ---")
            print(f"  {'id':<46} {'form':<6} ja_max en_max width/budget  reason             used")
            for h in bad:
                reasons = []
                if h["width_overflow"]: reasons.append("width-over")
                if h["line_mismatch"]: reasons.append("line-mismatch")
                if h["rows_used"] > ANTH_MAX_ROWS: reasons.append("too-tall")
                print(f"  {h['id']:<46} {h['form']:<6} {h['ja_max']:>5}  {h['en_max']:>5}   {h['width_used']:>3}/{h['width_budget']:<3}u   {','.join(reasons):<18} {'Y' if h['used'] else '-'}")

    # ---- summary tables ----
    print(f"\n=== Readability audit ({len(rows)} texts; {seen_smart_pill} with smart_pill) ===\n")

    def hist(rows, key):
        c = Counter(r[key] for r in rows)
        total = sum(c.values())
        out = []
        for k in ("OK", "AMBER", "RED"):
            n = c.get(k, 0)
            pct = (100 * n / total) if total else 0
            out.append(f"{k:5} {n:4d} ({pct:5.1f}%)")
        return "  ".join(out)

    print("Per zone, count by readability tier:")
    print(f"  gallery_text   : {hist(rows, 'gallery_class')}")
    print(f"  summary_delight: {hist(rows, 'delight_class')}")
    if pill_rows:
        print(f"  smart_pill     : {hist(pill_rows, 'class')}")

    # ---- divergence: same text, different verdict per zone ----
    print("\n--- Texts that differ by zone (gallery_text vs summary_delight) ---\n")
    rank = {"OK": 0, "AMBER": 1, "RED": 2}
    diverging = [r for r in rows if r["gallery_class"] != r["delight_class"]]
    diverging.sort(key=lambda r: (-(rank[r["delight_class"]] - rank[r["gallery_class"]]), r["form"]))
    print(f"  {'id':<46} {'form':<11} {'lines':>5} {'maxC':>4}   gallery        delight")
    print(f"  {'-'*46} {'-'*11} {'-'*5} {'-'*4}   {'-'*14} {'-'*14}")
    for r in diverging[:60]:
        g = f"{r['gallery_size']}u/{r['gallery_cols']}c {r['gallery_class']}" if r['gallery_size'] else f"OVERFLOW {r['gallery_class']}"
        d_overflow = " OVF" if r["delight_overflow"] else (" wrap" if r["delight_wrapped"] else "")
        d = f"{r['delight_size']}u{d_overflow} {r['delight_class']}"
        print(f"  {r['id']:<46} {r['form']:<11} {r['lines']:>5} {r['max_chars']:>4}   {g:<14} {d:<14}")
    if len(diverging) > 60:
        print(f"  ... and {len(diverging)-60} more")

    # ---- worst delight offenders ----
    print("\n--- summary_delight RED (overflow or strict-form wrap) ---\n")
    bad = [r for r in rows if r["delight_class"] == "RED"]
    bad.sort(key=lambda r: (-r["delight_rows"], -r["max_chars"]))
    print(f"  {'id':<46} {'form':<11} {'lines':>5} {'rows':>4}/{'cap':<3} wrap ovf")
    for r in bad[:80]:
        print(f"  {r['id']:<46} {r['form']:<11} {r['lines']:>5} {r['delight_rows']:>4}/{r['delight_cap']:<3} {str(r['delight_wrapped']):<5} {str(r['delight_overflow'])}")
    if len(bad) > 80:
        print(f"  ... and {len(bad)-80} more")

    # ---- worst gallery offenders ----
    print("\n--- gallery_text AMBER+RED (predicted size <30u or no fit) ---\n")
    gbad = [r for r in rows if r["gallery_class"] in {"AMBER", "RED"}]
    gbad.sort(key=lambda r: (rank[r["gallery_class"]] * -1, r["gallery_size"] or 0))
    for r in gbad[:60]:
        g = f"{r['gallery_size']}u/{r['gallery_cols']}c" if r['gallery_size'] else "OVERFLOW"
        print(f"  {r['gallery_class']:<5} {r['id']:<46} {r['form']:<11} lines={r['lines']:>3} maxC={r['max_chars']:>3}  →  {g}")
    if len(gbad) > 60:
        print(f"  ... and {len(gbad)-60} more")

    # ---- worst smart-pill offenders ----
    if pill_rows:
        print("\n--- smart_pill below sweet spot (<30u) ---\n")
        sbad = [r for r in pill_rows if r["class"] != "OK"]
        sbad.sort(key=lambda r: (r["size"], -r["chars"]))
        for r in sbad[:80]:
            print(f"  {r['class']:<5} {r['id']:<46} chars={r['chars']:>4}  →  {r['size']}u")
        if len(sbad) > 80:
            print(f"  ... and {len(sbad)-80} more")

    return 0


if __name__ == "__main__":
    sys.exit(main())

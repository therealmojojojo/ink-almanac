"""Exhaustive corpus analyzer for text sidecars.

Walks corpus/{texts,personal_library} and produces a markdown report plus a
one-page stdout summary. Built to answer four operator questions:

  1. What is in the text corpus, by form / language / rights / author?
  2. Do the declared `form` labels match the bodies (haiku=3 lines, etc.)?
  3. Will the renderer's metric-driven tier ladder land each body at >=28u
     (pill-parity) or below? Why?
  4. Are smart_pill bodies present, in budget (<=455 chars), and free of the
     formulaic openers the regenerated prompt bans?

Constants mirror the live picker (corpus_build_triplets_v2.py) and renderer
(renderer/src/modes/summary.ts) at the time of writing. If those drift, this
script drifts with them — re-read both before trusting the output.

Usage:
  python pairing/corpus_analyze.py
  python pairing/corpus_analyze.py --out corpus/_audits/corpus-analysis-$(date +%F).md
  python pairing/corpus_analyze.py --json    # also emit a sibling .json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import textwrap
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus"
TEXT_DIRS = ("texts", "personal_library")  # image folder excluded — no bodies

# --- Renderer tier ladder (mirror of renderer/src/modes/summary.ts) ----------
# [tier, font_u, line_height_u, soft_cpl, max_visual_lines]
DELIGHT_TIERS = [
    (1, 36, 48, 34,  7),
    (2, 32, 44, 38,  8),
    (3, 30, 40, 41,  9),
    (4, 28, 34, 44, 11),
    (5, 28, 30, 44, 12),
    (6, 24, 32, 52, 11),
    (7, 22, 28, 57, 13),
]
PILL_FLOOR_TIERS  = [1, 2, 3, 4, 5]
WRAP_TIERS_AT_FLOOR = [4, 5]
SUB_FLOOR_TIERS   = [6, 7]

# --- Picker constants (mirror corpus_build_triplets_v2.py) -------------------
SUMMARY_WRAP_COLS = 24
SUMMARY_MAX_VISUAL_LINES = 4

# --- Smart-pill capacity (renderer summary.ts comment) -----------------------
PILL_MAX_CHARS = 455
PILL_SHORT_SUSPICIOUS = 80   # arbitrary low-water mark; pill is meant deep-dive

# Formulaic-opener patterns the regenerated prompt explicitly bans. Match the
# first ~50 chars case-insensitively, after stripping markdown and whitespace.
FORMULAIC_OPENERS = [
    re.compile(r"^\s*\*?published in \d{3,4}", re.I),
    re.compile(r"^\s*\*?written in \d{3,4}", re.I),
    re.compile(r"^\s*\*?composed in \d{3,4}", re.I),
    re.compile(r"^\s*\*?from [A-Z][^.]{0,60}'s ", re.I),
    re.compile(r"^\s*\*?first published", re.I),
    re.compile(r"^\s*\*?appears? in [A-Z]", re.I),
]

# --- Termination quality (mirror corpus_audit_truncations.py) ----------------
DANGLERS = {
    "of","to","in","on","at","with","by","for","from","into","onto","upon",
    "over","under","through","across","between","among","against","without",
    "the","a","an","this","that","these","those","my","your","his","her","its","our","their",
    "and","but","or","nor","so","yet","as","if","when","while","until","since",
    "before","after","because","though","although","unless","whether",
    "who","whom","whose","which","what","where","why","how",
    "is","are","was","were","be","been","being","am","do","does","did",
    "have","has","had","will","would","shall","should","may","might","can","could","must",
}
TERMINAL_OK = set('.!?…—–-"”\'\')]}')

# --- Form expectations -------------------------------------------------------
# Two severities. STRICT: the form name is definitional and an off-count is
# a real classification bug (haiku must be 3 lines, sonnet 14, etc.). SOFT:
# the form is a category, not a fixed structure — operators legitimately
# break aphorisms across 3-4 visual lines for breath. Soft mismatches are
# reported separately so the operator can scan them without drowning the
# strict bugs.
FORM_EXPECTATIONS_STRICT = {
    "haiku":       {"lines": (3, 3),   "max_body_chars": 200},
    "tanka":       {"lines": (5, 5),   "max_body_chars": 280},
    "sonnet":      {"lines": (14, 14), "max_body_chars": None},
}
FORM_EXPECTATIONS_SOFT = {
    "aphorism":    {"lines": (1, 5),   "max_body_chars": 360, "allow_linebreaks": True},
    "quote":       {"lines": (1, 6),   "max_body_chars": 480, "allow_linebreaks": True},
    "fragment":    {"lines": (1, None),"max_body_chars": None, "allow_linebreaks": True},
    "free-verse":  {"lines": (3, None),"max_body_chars": None, "allow_linebreaks": True},
    "stanzaic":    {"lines": (3, None),"max_body_chars": None, "allow_linebreaks": True},
    "prose-poem":  {"lines": (1, None),"max_body_chars": None, "allow_linebreaks": False},
    "song-chorus": {"lines": (2, None),"max_body_chars": None, "allow_linebreaks": True},
    "lyric":       {"lines": (1, None),"max_body_chars": None, "allow_linebreaks": True},
}

# ----------------------------------------------------------------------------

def body_of(doc: dict) -> str:
    tv = doc.get("text_variants")
    if isinstance(tv, dict) and tv:
        return tv.get("en") or next(iter(tv.values())) or ""
    return doc.get("text") or ""


def author_lines(body: str) -> list[str]:
    """Author lines = non-empty lines as written (collapsing blank separators)."""
    return [ln.rstrip() for ln in body.splitlines() if ln.strip()]


def wrapped_visual_lines(body: str, width: int = SUMMARY_WRAP_COLS) -> int:
    """Match picker's wrapped_visual_lines."""
    n = 0
    for line in body.splitlines():
        s = line.strip()
        if not s:
            continue
        wrapped = textwrap.wrap(s, width=width, break_long_words=False, break_on_hyphens=True) or [s]
        n += len(wrapped)
    return n


def visual_lines_at_cpl(lines: list[str], cpl: int) -> int:
    """Renderer's visualLinesAt — sum of ceil(len/cpl) per author line."""
    total = 0
    for ln in lines:
        total += max(1, (len(ln) + cpl - 1) // cpl)
    return total


def predict_tier(body: str) -> tuple[int, str]:
    """Mirror renderer pickFitTier; return (tier, phase_label)."""
    lines = author_lines(body)
    n = len(lines)
    longest = max((len(ln) for ln in lines), default=0)

    # Phase 1: largest unwrapped at >=28u
    for cfg in DELIGHT_TIERS:
        t, _, _, cpl, mvl = cfg
        if t not in PILL_FLOOR_TIERS:
            continue
        if longest <= cpl and n <= mvl:
            return t, "phase1-unwrapped"
    # Phase 2: 28u with wrap
    for cfg in DELIGHT_TIERS:
        t, _, _, cpl, mvl = cfg
        if t not in WRAP_TIERS_AT_FLOOR:
            continue
        if visual_lines_at_cpl(lines, cpl) <= mvl:
            return t, "phase2-28u-wrap"
    # Phase 3: sub-pill unwrapped
    for cfg in DELIGHT_TIERS:
        t, _, _, cpl, mvl = cfg
        if t not in SUB_FLOOR_TIERS:
            continue
        if longest <= cpl and n <= mvl:
            return t, "phase3-sub-pill-unwrapped"
    return 7, "fallback-tier7-wrap"


def termination_signal(body: str) -> str | None:
    text = body.rstrip()
    if not text:
        return None
    last_char = text[-1]
    m = re.search(r"(\w+)\W*$", text)
    last_word = (m.group(1).lower() if m else "")
    ends_clean = last_char in TERMINAL_OK
    ends_comma = last_char == ","
    if (last_word in DANGLERS and not ends_clean) or ends_comma:
        return "comma" if ends_comma else "dangling-word"
    if not ends_clean and last_char not in ";:":
        return "no-terminal"
    return None


def form_check(form: str, body: str) -> tuple[list[str], list[str]]:
    """Return (strict_issues, soft_issues). Strict are real classification
    bugs (haiku not 3 lines etc.); soft are guideline drifts."""
    strict: list[str] = []
    soft: list[str] = []
    if not form:
        strict.append("missing-form")
        return strict, soft
    if form in FORM_EXPECTATIONS_STRICT:
        spec = FORM_EXPECTATIONS_STRICT[form]
        lines = author_lines(body)
        n = len(lines)
        lo, hi = spec["lines"]
        if lo is not None and n < lo:
            strict.append(f"too-few-lines({n}<{lo})")
        if hi is not None and n > hi:
            strict.append(f"too-many-lines({n}>{hi})")
        if spec["max_body_chars"] is not None and len(body) > spec["max_body_chars"]:
            strict.append(f"body-too-long({len(body)}>{spec['max_body_chars']})")
        return strict, soft
    if form in FORM_EXPECTATIONS_SOFT:
        spec = FORM_EXPECTATIONS_SOFT[form]
        lines = author_lines(body)
        n = len(lines)
        lo, hi = spec["lines"]
        if lo is not None and n < lo:
            soft.append(f"too-few-lines({n}<{lo})")
        if hi is not None and n > hi:
            soft.append(f"too-many-lines({n}>{hi})")
        if spec["max_body_chars"] is not None and len(body) > spec["max_body_chars"]:
            soft.append(f"body-too-long({len(body)}>{spec['max_body_chars']})")
        if not spec["allow_linebreaks"] and n > 1:
            soft.append(f"unexpected-linebreaks({n})")
        return strict, soft
    strict.append(f"unknown-form:{form}")
    return strict, soft


# ----------------------------------------------------------------------------
# Walk

def walk() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for sub in TEXT_DIRS:
        d = CORPUS / sub
        if not d.is_dir():
            continue
        for p in sorted(d.glob("*.yaml")):
            if p.name.startswith("EXAMPLE"):
                continue
            try:
                doc = yaml.safe_load(p.read_text())
            except Exception as e:
                rows.append({"id": p.stem, "folder": sub, "error": f"yaml-parse:{e}"})
                continue
            if not isinstance(doc, dict):
                continue
            body = body_of(doc)
            # personal_library has both texts and image sidecars; skip image-only ones
            if not body and not doc.get("text_variants") and not doc.get("text"):
                # likely an image sidecar in personal_library
                continue
            lines = author_lines(body)
            tier, phase = predict_tier(body) if body else (7, "no-body")
            wvl = wrapped_visual_lines(body) if body else 0
            pill = (doc.get("smart_pill") or {}) if isinstance(doc.get("smart_pill"), dict) else {}
            pill_body = pill.get("body") or ""
            ep = doc.get("excerpt_provenance")
            row: dict[str, Any] = {
                "id": doc.get("id") or p.stem,
                "folder": sub,
                "path": str(p.relative_to(ROOT)),
                "form": doc.get("form") or "",
                "author": doc.get("author") or "",
                "rights_tier": doc.get("rights_tier") or "",
                "languages": list((doc.get("language") or [])) if doc.get("language") else [],
                "summary_eligible_explicit": doc.get("summary_eligible", None),
                "has_excerpt_provenance": bool(ep),
                "extracted_at": (ep or {}).get("extracted_at") if isinstance(ep, dict) else None,
                "n_author_lines": len(lines),
                "longest_line_chars": max((len(ln) for ln in lines), default=0),
                "body_chars": len(body),
                "wrapped_visual_lines_24col": wvl,
                "predicted_tier": tier,
                "predicted_phase": phase,
                "predicted_font_u": next(c[1] for c in DELIGHT_TIERS if c[0] == tier),
                "form_issues_strict": (form_check(doc.get("form") or "", body)[0] if body else ["no-body"]),
                "form_issues_soft":   (form_check(doc.get("form") or "", body)[1] if body else []),
                "termination": termination_signal(body),
                "pill_present": bool(pill_body),
                "pill_chars": len(pill_body),
                "pill_over_budget": len(pill_body) > PILL_MAX_CHARS,
                "pill_short": 0 < len(pill_body) < PILL_SHORT_SUSPICIOUS,
                "pill_formulaic": any(rx.search(pill_body) for rx in FORMULAIC_OPENERS),
                "pill_model": pill.get("model") or "",
                "pill_generated_at": pill.get("generated_at") or "",
                "themes_n": len(doc.get("themes") or []),
                "mood_n": len(doc.get("mood") or []),
                "register_n": len(doc.get("register") or []),
            }
            rows.append(row)
    return rows


# ----------------------------------------------------------------------------
# Reporting

def histogram(values: list[int], bins: list[tuple[int, int, str]]) -> list[tuple[str, int]]:
    out = []
    for lo, hi, label in bins:
        out.append((label, sum(1 for v in values if lo <= v <= hi)))
    return out


def md_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |",
             "|" + "|".join(["---"] * len(headers)) + "|"]
    for r in rows:
        lines.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(lines)


def section(title: str, body: str) -> str:
    return f"\n## {title}\n\n{body}\n"


def render_report(rows: list[dict]) -> str:
    out: list[str] = []
    out.append(f"# Corpus analysis — {date.today().isoformat()}\n")
    out.append(f"_{len(rows)} text sidecars walked across {', '.join(TEXT_DIRS)}_")

    # ---------- 1. Headline counts ----------
    by_folder = Counter(r["folder"] for r in rows)
    by_form = Counter(r["form"] or "(missing)" for r in rows)
    by_rights = Counter(r["rights_tier"] or "(missing)" for r in rows)
    out.append(section("1. Headline counts",
        md_table(["folder", "n"], [[k, v] for k, v in sorted(by_folder.items())]) +
        "\n\n**By form:**\n\n" +
        md_table(["form", "n", "%"], [
            [k, v, f"{100*v/len(rows):.1f}%"]
            for k, v in sorted(by_form.items(), key=lambda x: -x[1])
        ]) +
        "\n\n**By rights tier:**\n\n" +
        md_table(["rights_tier", "n"], [[k, v] for k, v in sorted(by_rights.items(), key=lambda x: -x[1])])
    ))

    # ---------- 2. Form-vs-body mismatches ----------
    def render_mismatch_block(rows_subset: list[dict], issue_attr: str, label: str) -> str:
        flagged = [r for r in rows_subset if r[issue_attr]]
        if not flagged:
            return f"_(none — clean against {label} expectations)_"
        by_issue: dict[str, list[dict]] = defaultdict(list)
        for r in flagged:
            for issue in r[issue_attr]:
                tag = issue.split("(")[0]
                by_issue[tag].append(r)
        summary = md_table(
            ["issue", "n"],
            [[k, len(v)] for k, v in sorted(by_issue.items(), key=lambda x: -len(x[1]))]
        )
        detail = []
        for issue, items in sorted(by_issue.items(), key=lambda x: -len(x[1])):
            detail.append(f"\n**`{issue}` ({len(items)})**\n")
            sample = items[:25]
            detail.append(md_table(
                ["id", "form", "n_lines", "body_chars", "longest"],
                [[r["id"], r["form"], r["n_author_lines"], r["body_chars"], r["longest_line_chars"]]
                 for r in sample]
            ))
            if len(items) > 25:
                detail.append(f"\n_…+{len(items)-25} more_")
        return f"{len(flagged)} sidecars flagged.\n\n{summary}\n" + "\n".join(detail)

    out.append(section("2a. Form-vs-body mismatches — STRICT (definitional forms)",
        "Strict checks apply to fixed-structure forms only: haiku=3 lines, "
        "tanka=5 lines, sonnet=14 lines. Hits here are real classification "
        "bugs the operator should fix.\n\n" +
        render_mismatch_block(rows, "form_issues_strict", "strict")
    ))
    out.append(section("2b. Form-vs-body mismatches — SOFT (guideline drift)",
        "Soft checks apply to category forms (aphorism/quote/fragment/etc.) "
        "with generous bounds. Hits here are guideline drifts — usually "
        "fine, occasionally a sign the form label could be tighter (an "
        "aphorism that grew into a fragment, etc.).\n\n" +
        render_mismatch_block(rows, "form_issues_soft", "soft")
    ))

    # ---------- 3. Body geometry ----------
    line_counts = [r["n_author_lines"] for r in rows]
    longest = [r["longest_line_chars"] for r in rows]
    body_lens = [r["body_chars"] for r in rows]
    line_hist = histogram(line_counts, [
        (1, 1, "1"), (2, 2, "2"), (3, 3, "3"), (4, 4, "4"), (5, 5, "5"),
        (6, 8, "6-8"), (9, 12, "9-12"), (13, 16, "13-16"), (17, 9999, "17+"),
    ])
    longest_hist = histogram(longest, [
        (0, 24, "<=24"), (25, 34, "25-34"), (35, 44, "35-44"),
        (45, 52, "45-52"), (53, 57, "53-57"), (58, 9999, ">57 (no-tier-fits)"),
    ])
    body_hist = histogram(body_lens, [
        (0, 80, "<=80"), (81, 160, "81-160"), (161, 280, "161-280"),
        (281, 440, "281-440"), (441, 700, "441-700"), (701, 9999, "701+"),
    ])
    out.append(section("3. Body geometry",
        "**Author line counts:**\n\n" + md_table(["lines", "n"], line_hist) +
        "\n\n**Longest line (chars) — vs renderer cpl budget:**\n\n" +
        md_table(["chars", "n"], longest_hist) +
        "\n\n_Tier cpls: 1=34, 2=38, 3=41, 4/5=44, 6=52, 7=57. Longer than 57 chars cannot fit any tier unwrapped._" +
        "\n\n**Body length (chars):**\n\n" + md_table(["chars", "n"], body_hist)
    ))

    # ---------- 4. Predicted renderer tier ----------
    by_tier = Counter(r["predicted_tier"] for r in rows)
    by_phase = Counter(r["predicted_phase"] for r in rows)
    tier_rows = []
    for cfg in DELIGHT_TIERS:
        t, font, lh, cpl, mvl = cfg
        n = by_tier.get(t, 0)
        floor = "pill-parity (>=28u)" if t in PILL_FLOOR_TIERS else "SUB-PILL"
        tier_rows.append([t, f"{font}u", f"lh{lh}", cpl, mvl, n, floor])
    sub_pill = sum(by_tier.get(t, 0) for t in SUB_FLOOR_TIERS)
    out.append(section("4. Predicted renderer tier (delight cell)",
        md_table(["tier", "font", "line-height", "soft-cpl", "max-vis-lines", "n", "category"], tier_rows) +
        f"\n\n**{sub_pill} sidecars predicted to land below the 28u pill-parity floor.**" +
        "\n\n**By phase:**\n\n" +
        md_table(["phase", "n"], [[k, v] for k, v in sorted(by_phase.items(), key=lambda x: -x[1])])
    ))

    # ---------- 5. Picker summary-eligibility ----------
    explicit_false = [r for r in rows if r["summary_eligible_explicit"] is False]
    implicit_fail  = [r for r in rows
                      if r["summary_eligible_explicit"] is not False
                      and r["wrapped_visual_lines_24col"] > SUMMARY_MAX_VISUAL_LINES]
    picker_eligible = [r for r in rows
                       if r["summary_eligible_explicit"] is not False
                       and r["wrapped_visual_lines_24col"] <= SUMMARY_MAX_VISUAL_LINES
                       and r["wrapped_visual_lines_24col"] > 0]
    # Items the picker would treat as eligible but the renderer would push sub-pill:
    eligible_but_subpill = [r for r in picker_eligible if r["predicted_tier"] in SUB_FLOOR_TIERS]
    out.append(section("5. Picker summary-eligibility",
        f"- explicit `summary_eligible: false`: **{len(explicit_false)}**\n"
        f"- implicit fail (wrapped_visual_lines > {SUMMARY_MAX_VISUAL_LINES}): **{len(implicit_fail)}**\n"
        f"- picker-eligible (passes both): **{len(picker_eligible)}**\n"
        f"- of those eligible, predicted to render SUB-PILL (<28u): **{len(eligible_but_subpill)}**\n\n"
        + (("**Eligible-but-sub-pill (operator should re-extract or mark ineligible):**\n\n" +
            md_table(["id", "form", "tier", "n_lines", "longest"],
                     [[r["id"], r["form"], r["predicted_tier"], r["n_author_lines"], r["longest_line_chars"]]
                      for r in eligible_but_subpill[:50]])
            + (f"\n\n_…+{len(eligible_but_subpill)-50} more_" if len(eligible_but_subpill) > 50 else ""))
           if eligible_but_subpill else "_(no items in this conflict bucket — clean)_")
    ))

    # ---------- 6. Smart-pill audit ----------
    with_pill = [r for r in rows if r["pill_present"]]
    over = [r for r in with_pill if r["pill_over_budget"]]
    short = [r for r in with_pill if r["pill_short"]]
    formulaic = [r for r in with_pill if r["pill_formulaic"]]
    no_meta = [r for r in with_pill if not r["pill_model"] or not r["pill_generated_at"]]
    pill_hist = histogram([r["pill_chars"] for r in with_pill], [
        (1, 200, "1-200"), (201, 320, "201-320"), (321, 400, "321-400"),
        (401, 455, "401-455 (target)"), (456, 500, "456-500 (over)"), (501, 99999, "501+ (way over)"),
    ])
    out.append(section("6. Smart-pill audit",
        f"- present: **{len(with_pill)} / {len(rows)}** ({100*len(with_pill)/max(1,len(rows)):.1f}%)\n"
        f"- missing: **{len(rows) - len(with_pill)}**\n"
        f"- over 455-char budget: **{len(over)}**\n"
        f"- suspiciously short (<{PILL_SHORT_SUSPICIOUS} chars): **{len(short)}**\n"
        f"- formulaic openers ('Published in YYYY', etc.): **{len(formulaic)}**\n"
        f"- missing model/generated_at metadata: **{len(no_meta)}**\n\n"
        "**Pill length distribution:**\n\n" + md_table(["chars", "n"], pill_hist) +
        (("\n\n**Over budget:**\n\n" + md_table(["id", "chars"],
                                                [[r["id"], r["pill_chars"]] for r in over[:50]])
          + (f"\n\n_…+{len(over)-50} more_" if len(over) > 50 else "")) if over else "") +
        (("\n\n**Formulaic openers (sample):**\n\n" + md_table(["id"],
                                                                [[r["id"]] for r in formulaic[:30]])
          + (f"\n\n_…+{len(formulaic)-30} more_" if len(formulaic) > 30 else "")) if formulaic else "")
    ))

    # ---------- 7. Body termination quality ----------
    term_flags = [r for r in rows if r["termination"]]
    by_term = Counter(r["termination"] for r in term_flags)
    out.append(section("7. Body termination quality",
        f"- flagged: **{len(term_flags)}** of {len(rows)} ({100*len(term_flags)/max(1,len(rows)):.1f}%)\n\n" +
        md_table(["signal", "n"], [[k, v] for k, v in sorted(by_term.items(), key=lambda x: -x[1])]) +
        "\n\n_See `corpus audit-truncations` for full per-id tail rendering._"
    ))

    # ---------- 8. Excerpt-provenance coverage by form ----------
    form_x_prov: dict[str, dict[str, int]] = defaultdict(lambda: {"yes": 0, "no": 0})
    for r in rows:
        bucket = "yes" if r["has_excerpt_provenance"] else "no"
        form_x_prov[r["form"] or "(missing)"][bucket] += 1
    prov_rows = []
    for form, d in sorted(form_x_prov.items(), key=lambda x: -(x[1]["yes"] + x[1]["no"])):
        total = d["yes"] + d["no"]
        prov_rows.append([form, d["yes"], d["no"], f"{100*d['yes']/max(1,total):.0f}%"])
    out.append(section("8. Stage-1 excerpt-provenance coverage",
        md_table(["form", "with_provenance", "without", "% covered"], prov_rows)
    ))

    # ---------- 9. Languages, authors, missing metadata ----------
    lang_set = Counter()
    for r in rows:
        for lang in r["languages"]:
            lang_set[lang] += 1
    bilingual = sum(1 for r in rows if len(r["languages"]) > 1)
    top_authors = Counter(r["author"] for r in rows if r["author"]).most_common(20)
    missing_meta_rows = [r for r in rows
                        if r["themes_n"] == 0 or r["mood_n"] == 0 or r["register_n"] == 0]
    out.append(section("9. Language / author / metadata",
        f"- bilingual sidecars: **{bilingual}**\n\n"
        "**By language (item count, multi-counted):**\n\n" +
        md_table(["lang", "n"], [[k, v] for k, v in lang_set.most_common()]) +
        "\n\n**Top 20 authors:**\n\n" +
        md_table(["author", "n"], top_authors) +
        f"\n\n**Missing themes/mood/register: {len(missing_meta_rows)}**" +
        (("\n\n" + md_table(["id", "themes_n", "mood_n", "register_n"],
                            [[r["id"], r["themes_n"], r["mood_n"], r["register_n"]]
                             for r in missing_meta_rows[:30]])
          + (f"\n\n_…+{len(missing_meta_rows)-30} more_" if len(missing_meta_rows) > 30 else ""))
         if missing_meta_rows else "")
    ))

    return "\n".join(out) + "\n"


def stdout_summary(rows: list[dict]) -> str:
    by_form = Counter(r["form"] or "(missing)" for r in rows)
    by_tier = Counter(r["predicted_tier"] for r in rows)
    sub_pill = sum(by_tier.get(t, 0) for t in SUB_FLOOR_TIERS)
    strict_mm = sum(1 for r in rows if r["form_issues_strict"])
    soft_mm   = sum(1 for r in rows if r["form_issues_soft"])
    with_pill = sum(1 for r in rows if r["pill_present"])
    over = sum(1 for r in rows if r["pill_present"] and r["pill_over_budget"])
    formulaic = sum(1 for r in rows if r["pill_present"] and r["pill_formulaic"])
    term = sum(1 for r in rows if r["termination"])
    explicit_false = sum(1 for r in rows if r["summary_eligible_explicit"] is False)
    out = []
    out.append(f"corpus_analyze — {len(rows)} text sidecars")
    out.append(f"  forms : {dict(by_form.most_common())}")
    out.append(f"  form/body strict bugs    : {strict_mm}")
    out.append(f"  form/body soft drifts    : {soft_mm}")
    out.append(f"  predicted sub-pill (<28u): {sub_pill}")
    out.append(f"  summary_eligible:false   : {explicit_false}")
    out.append(f"  smart_pill present       : {with_pill}/{len(rows)}")
    out.append(f"  pills over 455 chars     : {over}")
    out.append(f"  pills with formulaic opener: {formulaic}")
    out.append(f"  body termination flagged : {term}")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path,
                    default=CORPUS / "_audits" / f"corpus-analysis-{date.today().isoformat()}.md")
    ap.add_argument("--json", action="store_true",
                    help="also write a sibling .json with the per-row data")
    args = ap.parse_args()

    rows = walk()
    report = render_report(rows)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report, encoding="utf-8")
    if args.json:
        json_path = args.out.with_suffix(".json")
        json_path.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")

    print(stdout_summary(rows))
    print(f"\nwrote {args.out.relative_to(ROOT)} ({len(report):,} chars)")
    if args.json:
        print(f"wrote {json_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

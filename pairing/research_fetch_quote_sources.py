"""One-off research helper: for each entry in famous-quotes-filtered.json,
fetch the source_text_url, locate the popular_quote inside the source, and
rebuild the snippet with the source's actual line breaks. Then store the
geometry of the rebuilt snippet (n_lines, longest_line_chars, total_chars).

This is research-tier — it is NOT wired into the corpus CLI. It exists to
turn the agent's flat-prose `popular_quote` strings into stanza-shaped
snippets so the operator can decide which entries are picker-eligible
without ingesting first.

Reuses the HTML→text extractor pattern from `corpus_fetch_web_via_urls.py`.

Usage:
  python pairing/research_fetch_quote_sources.py
  python pairing/research_fetch_quote_sources.py --limit 10 --dry-run
"""
from __future__ import annotations

import argparse, html as ihtml, json, re, sys, time, unicodedata, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "openspec/changes/expand-summary-pool/lists/famous-quotes-filtered.json"
OUT = ROOT / "openspec/changes/expand-summary-pool/lists/famous-quotes-resolved.json"

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
XHTML_TAG = re.compile(r"<[^>]+>")
WS = re.compile(r"[ \t]+")
BLANK = re.compile(r"\n{3,}")


def http_get(url: str, timeout: int = 25) -> str:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,*/*",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        # Try utf-8 first; fall back to latin-1
        for enc in ("utf-8", "latin-1"):
            try:
                return raw.decode(enc)
            except Exception:
                continue
        return raw.decode("utf-8", errors="replace")


def html_to_text(html: str) -> str:
    h = re.sub(r"<(script|style|nav|header|footer|aside|form|noscript)[\s\S]*?</\1>", "", html, flags=re.I)
    h = re.sub(r"<br\s*/?>", "\n", h, flags=re.I)
    h = re.sub(r"</(p|div|h[1-6]|li|tr|td|article|section|blockquote|pre)>", "\n", h, flags=re.I)
    h = XHTML_TAG.sub("", h)
    h = ihtml.unescape(h)
    h = WS.sub(" ", h)
    h = re.sub(r" *\n", "\n", h)
    h = BLANK.sub("\n\n", h)
    return h.strip()


def extract_poetryfoundation(html: str) -> str:
    m = re.search(r'<div[^>]*class="[^"]*\bpoem\b[^"]*"[^>]*>([\s\S]*?)</div>\s*</div>', html)
    if m: return html_to_text(m.group(1))
    m = re.search(r"<article[\s\S]*?</article>", html)
    return html_to_text(m.group(0)) if m else html_to_text(html)


def extract_wikisource(html: str) -> str:
    m = re.search(r'<div[^>]*class="[^"]*\bpoem\b[^"]*"[^>]*>([\s\S]*?)</div>', html)
    if m: return html_to_text(m.group(1))
    # Wikipedia and Wikisource often use <pre> blocks for poems too
    m = re.search(r"<pre[^>]*>([\s\S]*?)</pre>", html)
    if m: return html_to_text(m.group(1))
    return html_to_text(html)


EXTRACTORS = [
    ("poetryfoundation.org", extract_poetryfoundation),
    ("poets.org",            extract_poetryfoundation),
    ("wikisource.org",       extract_wikisource),
    ("wikipedia.org",        extract_wikisource),
]


def fetch_and_extract(url: str) -> tuple[str, str]:
    html = http_get(url)
    for needle, fn in EXTRACTORS:
        if needle in url.lower():
            return fn(html), needle
    return html_to_text(html), "generic"


# ---------- Snippet localization -------------------------------------------

def normalize(s: str) -> str:
    """For matching: lowercase, ASCII-fold, collapse whitespace, drop punctuation."""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = s.lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def find_snippet_window(source_text: str, popular_quote: str, window_lines: int = 8) -> tuple[str | None, int]:
    """Locate popular_quote inside source_text, return (window_with_line_breaks, n_lines_in_window).

    Strategy: take the first ~6 distinctive words of the normalized popular_quote
    and substring-match the normalized source. Find ALL matches across the
    document and score them — prefer matches in poem-layout context (short
    lines, adjacent blank lines) over matches inside dense prose paragraphs
    (editorial blurbs, footnotes). Use the best-scoring match's line index
    +/- window to extract a real-line window from the (un-normalized) source."""
    src_lines = [ln.rstrip() for ln in source_text.split("\n")]
    norm_lines = [normalize(ln) for ln in src_lines]
    norm_quote = normalize(popular_quote)
    if not norm_quote:
        return None, 0

    quote_words = norm_quote.split()
    matches: list[int] = []
    for prefix_len in (8, 6, 5, 4, 3):
        if len(quote_words) < prefix_len:
            continue
        needle = " ".join(quote_words[:prefix_len])
        matches = [i for i, nl in enumerate(norm_lines) if needle in nl]
        if matches:
            break
    if not matches:
        return None, 0

    def score(i: int) -> tuple[int, int]:
        # Higher is better. (poem_layout, -line_length).
        line_len = len(src_lines[i])
        # Count blank lines within 3 lines before/after
        blanks = 0
        for j in range(max(0, i - 3), min(len(src_lines), i + 4)):
            if not src_lines[j].strip():
                blanks += 1
        # Penalize very long lines (prose paragraphs); reward short lines (poetry)
        short_bonus = 1 if line_len <= 80 else 0
        return (blanks + short_bonus, -line_len)

    i = max(matches, key=score)

    start = i
    while start > 0 and src_lines[start - 1].strip():
        start -= 1
        if i - start >= window_lines:
            break
    end = i
    while end < len(src_lines) - 1 and src_lines[end + 1].strip():
        end += 1
        if end - i >= window_lines:
            break
    window = [ln for ln in src_lines[start:end + 1] if ln.strip()]
    return "\n".join(window), len(window)


# ---------- Main -----------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="cap entries fetched (0 = all)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sleep", type=float, default=0.6, help="delay between fetches (sec)")
    args = ap.parse_args()

    entries = json.loads(SRC.read_text())
    if args.limit:
        entries = entries[:args.limit]

    out: list[dict] = []
    ok = err = no_match = 0
    for i, e in enumerate(entries, 1):
        url = e.get("source_text_url") or ""
        rec = dict(e)
        rec["fetched_ok"] = False
        rec["snippet_in_source"] = None
        rec["snippet_geometry"] = None
        rec["fetch_error"] = None
        rec["extractor_used"] = None
        rec["snippet_match"] = False
        if not url:
            rec["fetch_error"] = "no source_text_url"
            out.append(rec); err += 1
            continue
        if args.dry_run:
            print(f"[{i}/{len(entries)}] DRY  {url}")
            out.append(rec); continue
        try:
            text, extractor = fetch_and_extract(url)
            rec["fetched_ok"] = True
            rec["extractor_used"] = extractor
            window, n_lines = find_snippet_window(text, e["popular_quote"])
            if window:
                rec["snippet_match"] = True
                rec["snippet_in_source"] = window
                lines = [ln for ln in window.split("\n") if ln.strip()]
                rec["snippet_geometry"] = {
                    "n_lines": len(lines),
                    "longest_line_chars": max((len(ln) for ln in lines), default=0),
                    "total_chars": len(window),
                }
                ok += 1
                marker = "OK"
            else:
                no_match += 1
                marker = "NO-MATCH"
        except Exception as ex:
            rec["fetch_error"] = f"{type(ex).__name__}: {ex}"
            err += 1
            marker = "ERR"
        print(f"[{i}/{len(entries)}] {marker:8s} {e['author'][:25]:25s} {e['poem_title'][:35]:35s} {url[:60]}")
        out.append(rec)
        time.sleep(args.sleep)

    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n=== Summary ===")
    print(f"  total       : {len(entries)}")
    print(f"  fetched OK  : {ok + no_match}")
    print(f"  snippet OK  : {ok}")
    print(f"  no match    : {no_match}")
    print(f"  fetch error : {err}")
    print(f"  wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

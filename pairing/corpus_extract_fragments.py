"""Stage 1 of the two-stage rework.

Given a full source poem at corpus/_sources/<author>/<id>.txt and the current
sidecar body, ask Opus to either:
  (a) return the FULL poem if it fits the delight-cell cap (≤4 visual lines
      after 24-col wrap), OR
  (b) pick a single significant 1-4 line fragment ending at a clean
      syntactic unit, holding load on its own (closing punchline, iconic
      line, volta, refrain, complete thought).

Writes back to text_variants.en, adds an excerpt_provenance block:
  excerpt_provenance:
    is_full_poem: bool
    rationale: str
    source_path: corpus/_sources/<author>/<id>.txt
    model: claude-opus-4-7
    extracted_at: 2026-04-28

Dry-run by default. Use --apply to write changes.
"""
from __future__ import annotations
import argparse, datetime, json, os, re, sys, textwrap, time
from pathlib import Path

import yaml
import anthropic

ROOT   = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus"
SOURCES = CORPUS / "_sources"
SECRETS = ROOT / "ha" / "secrets.yaml"
TEXT_DIRS = ("texts", "personal_library")

MODELS = ["claude-opus-4-7", "claude-opus-4-5", "claude-opus-4-1-20250805"]

# Mirror the picker's wrap parameters (corpus_build_triplets_v2.py).
WRAP_COLS = 24
MAX_VISUAL_LINES = 4

PROMPT = """\
You are curating a small anthology display. Each entry shows ONE short
text in a delight cell.

LENGTH BUDGET — the renderer wraps text at ~24 characters per line. After
that wrap, the body must be:
  - IDEAL  : ≤ 4 visual lines (qualifies for the small "summary" cell)
  - OK     : 5–14 visual lines (will be shown in the larger "gallery" cell)
  - REJECT : > 14 visual lines (won't fit anywhere in the layout)

A 4-author-line quatrain often wraps to 6–10 visual lines; that's fine as
the gallery option, but if you can find a 1–2 line couplet that holds the
poem's weight, that's better (qualifies for summary).

CHOICE A — RETURN THE FULL POEM. If the entire poem fits within the OK
budget (≤ 8 visual lines after wrap), return the whole thing. This is
preferred for short complete poems (Frost "Fire and Ice", "Dust of Snow";
Blake quatrains; many Dickinson 4-line poems; Williams "This is just to
say"). Don't over-trim a piece that already fits whole.

CHOICE B — RETURN A SIGNIFICANT 1–4 LINE FRAGMENT. If the poem is too
long to show whole, pick a fragment that:
  - ends at a clean syntactic unit (period, exclamation, question, em-dash,
    end-of-sentence quotation)
  - holds load on its own: a closing punchline, a refrain, the volta, an
    iconic line, OR a complete thought that invites the whole
  - is NOT a mid-clause break, NOT comma-ending, NOT ending on an article
    / preposition / auxiliary verb
  - is NOT "just the opening" unless that opening is itself iconic AND
    complete on its own (Blake's "To see a World in a grain of sand…"
    quatrain qualifies; the first stanza of Dickinson's "Because I could
    not stop for Death" does NOT — the punchline lies in stanza 6)

You will be given:
  - the full source text of the poem (your authoritative reference, but
    note: source extraction is imperfect — sometimes the wrong poem ends
    up in the source file due to first-line matching collisions in the
    publisher's index. If the source clearly does not contain the poem
    named in the title, fall back to the canonical text from your own
    knowledge and note this in the rationale.)
  - the current excerpt in our corpus (often broken — you're fixing it)

Return ONLY a single JSON object, no markdown, no explanation outside the
JSON:

{
  "is_full_poem": true,           // true if you returned the whole poem
  "body": "...",                  // the actual text, with newlines as \\n
  "form": "stanzaic",             // REQUIRED. The form tag that matches
                                  // the body you're returning. Renderer
                                  // routes font-size by form:
                                  //   - "fragment"/"aphorism" = 36u/48lh
                                  //     (use ONLY for ≤2 lines that read
                                  //     as a self-contained pithy unit)
                                  //   - "quote" = 34u/46lh (single quoted
                                  //     line, attributed)
                                  //   - "haiku"/"tanka" = 36u/52lh
                                  //   - "stanzaic" = 28u/40lh (multi-
                                  //     line poetry — the catch-all)
                                  //   - "sonnet"/"free-verse"/"prose-
                                  //     poem" = 28u/40lh (same as
                                  //     stanzaic)
                                  // Pick by line count of YOUR body:
                                  //   1 line → fragment/aphorism/quote
                                  //   2 lines → fragment if a couplet
                                  //     stands alone, else stanzaic
                                  //   ≥3 lines → stanzaic (or sonnet/
                                  //     free-verse if that matches the
                                  //     work)
  "rationale": "...",             // ≤140 chars: why this is the right
                                  // choice. Reference the structural move
                                  // (closing, volta, refrain, iconic line,
                                  // self-contained quatrain).
  "lines_in_source": "12-15"      // approximate line range in the full
                                  // source, or "all" if is_full_poem
}

Both `body` and `rationale` are required. `body` MUST be a verbatim
substring of the source text (no paraphrase, no modernization). Newlines
in `body` reflect the line breaks of the source.

If the source text is corrupted, fragmentary, or you cannot find a clean
significant fragment, return:
{
  "is_full_poem": false,
  "body": "",
  "rationale": "no clean significant fragment available — needs operator review",
  "lines_in_source": ""
}
"""

USER_TEMPLATE = """\
TEXT ID: {tid}
AUTHOR: {author}
TITLE: {title}

CURRENT EXCERPT (in corpus, may be broken — your job is to verify or fix):
---
{current}
---

FULL SOURCE TEXT (your authoritative reference; may include surrounding
poems or formatting noise from the source EPUB/PDF — focus on the named
poem):
---
{source}
---
"""

# --- Helpers --------------------------------------------------------------

def wrapped_visual_lines(body: str) -> int:
    n = 0
    for line in body.splitlines():
        s = line.strip()
        if not s:
            continue
        wrapped = textwrap.wrap(s, width=WRAP_COLS, break_long_words=False, break_on_hyphens=True) or [s]
        n += len(wrapped)
    return n


def get_api_key() -> str:
    if 'ANTHROPIC_API_KEY' in os.environ:
        return os.environ['ANTHROPIC_API_KEY']
    if SECRETS.exists():
        try:
            d = yaml.safe_load(SECRETS.read_text()) or {}
            for k in ('anthropic_api_key', 'ANTHROPIC_API_KEY'):
                if k in d: return d[k]
        except Exception:
            pass
    sys.exit("missing ANTHROPIC_API_KEY (env or ha/secrets.yaml)")


def load_sidecar(tid: str):
    for sub in TEXT_DIRS:
        p = CORPUS / sub / f"{tid}.yaml"
        if p.exists():
            return p, yaml.safe_load(p.read_text())
    return None, None


def find_source(tid: str, author: str) -> Path | None:
    """Source files live under _sources/<slug(author)>/<tid>.txt."""
    import unicodedata
    def slug(s: str) -> str:
        s = unicodedata.normalize('NFKD', s).encode('ascii','ignore').decode()
        return re.sub(r'[^a-zA-Z0-9]+','-',s).strip('-').lower()
    p = SOURCES / slug(author) / f"{tid}.txt"
    return p if p.exists() else None


JSON_RX = re.compile(r'\{[\s\S]*\}', re.M)

def extract_json(text: str) -> dict | None:
    """Strict json.loads first; regex fallback for the common case where
    the model includes prose around the JSON or unescaped quotes inside."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = JSON_RX.search(text)
    if not m: return None
    raw = m.group(0)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # try repairing common issues: smart quotes, trailing commas
        repaired = raw.replace('“','"').replace('”','"').replace('‘',"'").replace('’',"'")
        repaired = re.sub(r',\s*([\]}])', r'\1', repaired)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            return None


def call_opus(client, system: str, user: str, max_tokens: int = 800) -> tuple[str, str]:
    """Try MODELS in order; return (text, model_id). Raises on total failure."""
    last_exc = None
    for m in MODELS:
        try:
            resp = client.messages.create(
                model=m,
                max_tokens=max_tokens,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user}],
            )
            return ''.join(b.text for b in resp.content if b.type == 'text'), m
        except (anthropic.NotFoundError, anthropic.BadRequestError) as e:
            last_exc = e
            continue
        except anthropic.RateLimitError as e:
            time.sleep(8)
            last_exc = e
            continue
    raise last_exc or RuntimeError("all models failed")


# --- Main loop ------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--candidates', default='/tmp/rework-candidates.yaml')
    ap.add_argument('--apply', action='store_true', help='write changes; otherwise dry-run')
    ap.add_argument('--limit', type=int, default=0, help='max items to process this run')
    ap.add_argument('--ids', nargs='*', help='restrict to specific text ids')
    ap.add_argument('--reflag-existing', action='store_true', help='reprocess items that already have excerpt_provenance')
    args = ap.parse_args()

    api_key = get_api_key()
    client = anthropic.Anthropic(api_key=api_key)

    cands = yaml.safe_load(Path(args.candidates).read_text()) or []
    if args.ids:
        cands = [c for c in cands if c['id'] in set(args.ids)]
    print(f"Loaded {len(cands)} candidates")

    # Filter to those with a source file present
    work = []
    for c in cands:
        src = find_source(c['id'], c['author'])
        if not src: continue
        sidecar_path, doc = load_sidecar(c['id'])
        if not doc: continue
        if not args.reflag_existing and (doc.get('excerpt_provenance') or {}).get('extracted_at'):
            continue
        work.append((c, src, sidecar_path, doc))
    print(f"  {len(work)} have a source file in corpus/_sources/")
    if args.limit and len(work) > args.limit:
        print(f"  limiting to first {args.limit}")
        work = work[:args.limit]

    today = datetime.date.today().isoformat()
    in_tok = out_tok = 0
    full_count = excerpt_count = empty_count = 0
    flags: list[tuple[str, str]] = []

    for c, src, sidecar_path, doc in work:
        tid = c['id']
        title  = str(doc.get('title') or c.get('title') or '')
        author = str(doc.get('author') or c.get('author') or '')
        tv = doc.get('text_variants') or {}
        current = tv.get('en') or (next(iter(tv.values())) if tv else '') or ''
        source_text = src.read_text()
        # Truncate source if huge (keep 12k chars max, focused around current
        # excerpt if we can). Most poem windows are <4k.
        if len(source_text) > 12000:
            source_text = source_text[:12000]

        user = USER_TEMPLATE.format(
            tid=tid, author=author, title=title,
            current=current.strip(), source=source_text.strip(),
        )
        try:
            text, model_used = call_opus(client, PROMPT, user, max_tokens=800)
        except Exception as e:
            print(f"  [ERR] {tid}: {e}")
            flags.append((tid, f'api-error: {e}'))
            continue

        # Token accounting (rough; the SDK exposes usage on resp but we
        # discarded it — re-call to count would be wasteful). Skip for now.
        obj = extract_json(text)
        if not obj or 'body' not in obj or 'rationale' not in obj:
            print(f"  [BAD-JSON] {tid}: {text[:140]!r}")
            flags.append((tid, 'bad-json'))
            continue

        is_full   = bool(obj.get('is_full_poem'))
        body      = (obj.get('body') or '').strip()
        rationale = (obj.get('rationale') or '').strip()
        lines     = obj.get('lines_in_source') or ''
        new_form  = (obj.get('form') or '').strip().lower()

        # Validations
        warns = []
        if not body:
            empty_count += 1
            warns.append('empty-body')
        else:
            vlines = wrapped_visual_lines(body)
            if vlines <= 4:    fit = 'summary-fit'
            elif vlines <= 14: fit = 'gallery-fit'
            else:              fit = f'too-long: {vlines} visual lines (>14)'
            if vlines > 14:
                warns.append(fit)
            # Source-substring check (informational, not a blocker — the
            # source may be wrong/corrupted and the model may have used its
            # own canonical knowledge). Punctuation- and case-permissive.
            def normalize(s):
                s = s.lower()
                s = re.sub(r'[^a-z0-9 ]+', ' ', s)
                s = re.sub(r'\s+', ' ', s).strip()
                return s
            n_body = normalize(body)
            n_src  = normalize(source_text)
            head = n_body[:30]; tail = n_body[-30:]
            if head and head not in n_src:
                warns.append('not-in-source-(may-be-canonical-recall)')

        # Tally
        marker = '⚑' if warns else '·'
        kind = 'FULL' if is_full else 'frag'
        print(f"  [{kind} {marker}] {tid:<48s} {len(body):>4d}c  {model_used}  {' '.join(warns)}")
        if warns:
            flags.append((tid, '; '.join(warns)))
        if not body:
            continue
        if is_full: full_count += 1
        else:       excerpt_count += 1

        if args.apply:
            doc['text_variants'] = doc.get('text_variants') or {}
            # Preserve any non-en variants
            preserved = {k: v for k, v in (doc['text_variants'] or {}).items() if k != 'en'}
            preserved['en'] = body + ('\n' if not body.endswith('\n') else '')
            # Re-order with en first
            doc['text_variants'] = {'en': preserved.pop('en'), **preserved}
            # Update form if the model supplied one in the recognized set
            if new_form in {'fragment','aphorism','quote','haiku','tanka',
                            'stanzaic','sonnet','free-verse','prose-poem',
                            'song-chorus','koan','proverb','epigram'}:
                doc['form'] = new_form
            doc['excerpt_provenance'] = {
                'is_full_poem': is_full,
                'rationale': rationale,
                'source_path': str(src.relative_to(ROOT)),
                'lines_in_source': lines,
                'model': model_used,
                'extracted_at': today,
            }
            sidecar_path.write_text(
                yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=110)
            )

    print(f"\n=== SUMMARY ===")
    print(f"  full-poem rewrites:  {full_count}")
    print(f"  fragment rewrites:   {excerpt_count}")
    print(f"  empty/skipped:       {empty_count}")
    print(f"  flagged for review:  {len(flags)}")
    if flags:
        print(f"\nFlags:")
        for tid, why in flags[:20]:
            print(f"  {tid}: {why}")
        if len(flags) > 20: print(f"  ... +{len(flags)-20} more")
    if not args.apply:
        print(f"\n(dry-run; pass --apply to write)")


if __name__ == '__main__':
    main()

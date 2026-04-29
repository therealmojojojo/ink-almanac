"""Build a visual review page for sidecars selected by mode.

Modes:
  extracts (default) — every sidecar touched by Stage 1 (the
    `excerpt_provenance.extracted_at` field is set). Cards group by
    FULL-poem vs FRAGMENT. Used to spot bad cuts, full-poem upgrades,
    and form-fit issues after the extract-fragments rewriter runs.

  unterminated — every sidecar whose body doesn't end at a clean
    phrase delimiter (.!?…—"')]). Cards group by terminator type
    (no-terminal / comma / semicolon / colon) with a suggestion badge:
    KEEP (genre-fragmentary author like Sappho), RE-EXTRACT (truncation
    that needs a Stage-1 pass), or REMOVE.

Each card embeds a production summary-face PNG (1200×825) rendered via
`/debug/text-summary-test.png` so the operator sees the device-equivalent
output, not just YAML. PNGs are local files (same-origin file:// loads);
iframes are NOT used because browsers block file:// → http://127.0.0.1
under Private Network Access.

Prereq: the renderer must be running on http://127.0.0.1:8585 (the test
instance). Start it with:

  cd renderer && RENDERER_PORT=8585 npm run dev

Override the renderer URL with the RENDERER_URL env var. Items marked
`summary_eligible: false` are excluded from both modes — they render in
the gallery cell with different geometry.

Usage:
  # default mode = extracts
  python pairing/corpus_build_review_page.py
  python pairing/corpus_build_review_page.py --mode extracts

  # unterminated bodies
  python pairing/corpus_build_review_page.py --mode unterminated

  # custom output location
  python pairing/corpus_build_review_page.py --out-html /tmp/review.html \\
      --out-renders-dir /tmp/review-renders

  # force re-render (skip the >5KB cache check)
  python pairing/corpus_build_review_page.py --force

  # restrict to specific ids
  python pairing/corpus_build_review_page.py --ids id1 id2 ...
"""
from __future__ import annotations
import argparse, os, re, sys, unicodedata, urllib.request
from collections import defaultdict
from html import escape
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / 'corpus'
SOURCES = CORPUS / '_sources'
TEXT_DIRS = ('texts', 'personal_library')

# Renderer URL — defaults to the test instance on 8585 to avoid colliding
# with the production renderer on 8575. Override with RENDERER_URL env var.
RENDER_URL = os.environ.get('RENDERER_URL', 'http://127.0.0.1:8585') + '/debug/text-summary-test.png'

# Per-mode default output paths; both pages live alongside the corpus
# expand-summary-pool change so reviews are in one place.
MODE_PATHS = {
    'extracts': {
        'html': ROOT / 'openspec/changes/expand-summary-pool/rework-review.html',
        'renders': ROOT / 'openspec/changes/expand-summary-pool/rework-review-renders',
    },
    'unterminated': {
        'html': ROOT / 'openspec/changes/expand-summary-pool/unterminated-review.html',
        'renders': ROOT / 'openspec/changes/expand-summary-pool/unterminated-review-renders',
    },
}

TERMINAL = set('.!?…—–-"”\'\')]}')          # accepted phrase-end markers
GENRE_FRAGMENTARY = {'Sappho', 'Heraclitus', 'Empedocles', 'Parmenides',
                     'Archilochus', 'Alcaeus', 'Anacreon'}


def author_slug(s: str) -> str:
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-zA-Z0-9]+', '-', s).strip('-').lower()


def categorize_terminator(body: str) -> str:
    text = body.rstrip()
    if not text:
        return 'no-terminal'
    last = text[-1]
    if last == ',':  return 'comma'
    if last == ';':  return 'semicolon'
    if last == ':':  return 'colon'
    if last in TERMINAL: return 'clean'
    return 'no-terminal'


def suggest_action(d: dict, cat: str) -> tuple[str, str]:
    """Return (KEEP|RE-EXTRACT|REMOVE, reason)."""
    if str(d.get('author') or '') in GENRE_FRAGMENTARY:
        return 'KEEP', 'fragmentary by genre'
    if cat == 'comma':     return 'RE-EXTRACT', 'comma-ending = mid-clause'
    if cat == 'semicolon': return 'RE-EXTRACT', 'semicolon-ending = mid-thought'
    if cat == 'colon':     return 'RE-EXTRACT', 'colon-ending = mid-thought'
    return 'RE-EXTRACT', 'no terminal punctuation'


def load_items(mode: str, only_ids: set[str] | None = None) -> list[dict]:
    """Walk corpus and return sidecars matching the mode's filter.
    Items with `summary_eligible: false` are skipped (they're gallery-only)."""
    out: list[dict] = []
    for sub in TEXT_DIRS:
        for p in (CORPUS / sub).glob('*.yaml'):
            if p.name.startswith('EXAMPLE'):
                continue
            try:
                d = yaml.safe_load(p.read_text())
            except Exception:
                continue
            if not d: continue
            if d.get('summary_eligible') is False: continue
            if only_ids and d.get('id') not in only_ids: continue
            tv = d.get('text_variants') or {}
            body = ''
            if isinstance(tv, dict) and tv:
                body = tv.get('en') or next(iter(tv.values())) or ''
            if not body: continue

            if mode == 'extracts':
                prov = d.get('excerpt_provenance') or {}
                if not prov.get('extracted_at'):
                    continue
                out.append({
                    'mode': 'extracts',
                    'id': d.get('id'),
                    'author': str(d.get('author') or ''),
                    'title':  str(d.get('title') or ''),
                    'is_full': bool(prov.get('is_full_poem')),
                    'rationale': prov.get('rationale') or '',
                    'lines_in_source': prov.get('lines_in_source') or '',
                    'body': body,
                    'folder': sub,
                    'has_pill': bool((d.get('smart_pill') or {}).get('body')),
                })
            elif mode == 'unterminated':
                cat = categorize_terminator(body)
                if cat == 'clean':
                    continue
                action, reason = suggest_action(d, cat)
                src = SOURCES / author_slug(str(d.get('author') or '')) / f"{d['id']}.txt"
                tail = body.rstrip().split('\n')[-1][-50:] if body.strip() else ''
                out.append({
                    'mode': 'unterminated',
                    'id': d.get('id'),
                    'author': str(d.get('author') or ''),
                    'title':  str(d.get('title') or ''),
                    'form':   d.get('form') or '?',
                    'category': cat,
                    'action': action,
                    'reason': reason,
                    'tail': tail,
                    'last_char': repr(body.rstrip()[-1] if body.rstrip() else ''),
                    'body': body,
                    'folder': sub,
                    'has_source': src.exists(),
                })
    return out


def render_pngs(items: list[dict], renders_dir: Path, force: bool) -> tuple[int, int, list[tuple[str, str]]]:
    renders_dir.mkdir(parents=True, exist_ok=True)
    rendered = skipped = 0
    failed: list[tuple[str, str]] = []
    for it in items:
        out = renders_dir / f"{it['id']}.png"
        if not force and out.exists() and out.stat().st_size > 5000:
            skipped += 1
            continue
        try:
            with urllib.request.urlopen(f"{RENDER_URL}?id={it['id']}", timeout=60) as r:
                data = r.read()
            out.write_bytes(data)
            rendered += 1
            if rendered % 20 == 0:
                print(f"  rendered {rendered}/{len(items)}")
        except Exception as e:
            failed.append((it['id'], str(e)))
    return rendered, skipped, failed


CSS_COMMON = (
    "body { margin:0; font-family:-apple-system,BlinkMacSystemFont,sans-serif; background:#f4f4f4; color:#222; }\n"
    "h1 { position:sticky; top:0; background:#1a1a1a; color:#fff; margin:0; padding:14px 24px; font-size:16px; z-index:10; }\n"
    "nav { position:sticky; top:46px; background:#fff; padding:8px 24px; border-bottom:1px solid #ddd; font-size:13px; z-index:9; }\n"
    "nav a { margin-right:16px; color:#06c; text-decoration:none; }\n"
    ".note { background:#fff; margin:0; padding:12px 24px; color:#555; font-size:13px; border-bottom:1px solid #ddd; }\n"
    ".card { margin:24px auto; width:1200px; background:#fff; box-shadow:0 1px 3px rgba(0,0,0,.1); }\n"
    ".card header { padding:14px 18px; border-bottom:1px solid #eee; }\n"
    ".card h2 { margin:0 0 8px 0; font-size:16px; font-family:ui-monospace,monospace; word-break:break-all; }\n"
    ".card .meta { margin:0 0 6px 0; font-size:13px; color:#777; }\n"
    ".card .meta .folder { color:#999; font-family:ui-monospace,monospace; font-size:12px; }\n"
    ".card .rationale, .card .reason { margin:0 0 8px 0; font-size:12px; color:#444; font-style:italic; }\n"
    ".card .reason code { background:#f5f5f5; padding:1px 6px; border-radius:2px; font-style:normal; }\n"
    ".card .body { margin:0; font-size:13px; line-height:1.45; color:#333; padding:8px 12px; background:#fafafa; border-left:3px solid #d0d0d0; white-space:pre-wrap; font-family:ui-monospace,monospace; }\n"
    ".badge { display:inline-block; padding:2px 8px; font-family:ui-monospace,monospace; font-size:11px; border-radius:3px; margin-left:8px; }\n"
    ".badge.full { background:#e0f0e0; color:#163; }\n"
    ".badge.frag { background:#eef; color:#336; }\n"
    ".badge.keep { background:#e0f0e0; color:#163; }\n"
    ".badge.re   { background:#ffe9c8; color:#a55; }\n"
    ".badge.rm   { background:#fee; color:#c33; }\n"
    ".form { display:inline-block; padding:2px 8px; background:#eef; color:#336; font-size:11px; border-radius:3px; margin-left:4px; font-family:ui-monospace,monospace; }\n"
    ".pill { color:#888; margin-left:6px; }\n"
    ".src  { margin-left:6px; font-size:11px; color:#888; font-family:ui-monospace,monospace; }\n"
    ".card img { display:block; width:1200px; height:auto; }\n"
)


def card_extracts(it: dict, rel: str) -> str:
    img = f"{rel}/{it['id']}.png"
    badge_class = 'full' if it['is_full'] else 'frag'
    badge_text = 'FULL POEM' if it['is_full'] else 'FRAGMENT'
    pill_dot = '●' if it['has_pill'] else '○'
    lines_suffix = f" · lines {escape(it['lines_in_source'])}" if it['lines_in_source'] else ''
    return (
        f'<section class="card">\n'
        f'  <header>\n'
        f'    <h2>{escape(it["id"])}\n'
        f'      <span class="badge {badge_class}">{badge_text}</span>\n'
        f'      <span class="pill" title="has smart_pill">{pill_dot}</span>\n'
        f'    </h2>\n'
        f'    <p class="meta">{escape(it["author"])} — {escape(it["title"])} · '
        f'<span class="folder">{escape(it["folder"])}</span></p>\n'
        f'    <p class="rationale">{escape(it["rationale"])}{lines_suffix}</p>\n'
        f'    <pre class="body">{escape(it["body"])}</pre>\n'
        f'  </header>\n'
        f'  <img src="{img}" alt="{escape(it["id"])} summary face" width="1200">\n'
        f'</section>\n'
    )


def card_unterminated(it: dict, rel: str) -> str:
    img = f"{rel}/{it['id']}.png"
    badge_class = 'keep' if it['action'] == 'KEEP' else ('re' if it['action'] == 'RE-EXTRACT' else 'rm')
    src_dot = '●' if it['has_source'] else '○'
    src_title = 'source available for re-extraction' if it['has_source'] else 'no source — would need fetch'
    return (
        f'<section class="card">\n'
        f'  <header>\n'
        f'    <h2>{escape(it["id"])}\n'
        f'      <span class="badge {badge_class}">{escape(it["action"])}</span>\n'
        f'      <span class="form">{escape(it["form"])}</span>\n'
        f'      <span class="src" title="{src_title}">{src_dot} src</span>\n'
        f'    </h2>\n'
        f'    <p class="meta">{escape(it["author"])} — {escape(it["title"])} · '
        f'<span class="folder">{escape(it["folder"])}</span></p>\n'
        f'    <p class="reason">{escape(it["reason"])} · ends with {escape(it["last_char"])} '
        f'(tail: <code>{escape(it["tail"])}</code>)</p>\n'
        f'    <pre class="body">{escape(it["body"])}</pre>\n'
        f'  </header>\n'
        f'  <img src="{img}" alt="{escape(it["id"])} summary face" width="1200">\n'
        f'</section>\n'
    )


def build_html(mode: str, items: list[dict], renders_dir: Path, html_path: Path) -> None:
    rel = renders_dir.name
    parts: list[str] = ['<!doctype html>\n<html><head><meta charset="utf-8">\n']
    if mode == 'extracts':
        title = f'Stage-1 rework review — {len(items)} sidecars'
    else:
        title = f'Unterminated bodies — {len(items)} items for review'
    parts.append(f'<title>{escape(title)}</title>\n')
    parts.append(f'<style>\n{CSS_COMMON}</style>\n</head><body>\n')
    parts.append(f'<h1>{escape(title)}</h1>\n')

    if mode == 'extracts':
        by_kind: dict[str, list[dict]] = defaultdict(list)
        for it in items:
            by_kind['FULL' if it['is_full'] else 'FRAGMENT'].append(it)
        parts.append(
            f'<nav><a href="#full">FULL poems ({len(by_kind["FULL"])})</a> '
            f'<a href="#fragment">FRAGMENTS ({len(by_kind["FRAGMENT"])})</a></nav>\n'
        )
        parts.append(
            '<p class="note">Each card renders the production summary face: the text in the delight cell '
            'on the left, its smart_pill in the pill cell on the right (if any). Look for: bodies that no '
            'longer cut off mid-clause, full-poem upgrades that fit the cell cleanly, and any cases where '
            'Stage 1 returned wrong/odd content.</p>\n'
        )
        for k in ('FULL', 'FRAGMENT'):
            parts.append(f'<a id="{k.lower()}"></a><h1>{k} — {len(by_kind[k])}</h1>\n')
            for it in sorted(by_kind[k], key=lambda x: (x['author'], x['id'])):
                parts.append(card_extracts(it, rel))
    else:  # unterminated
        cat_labels = {
            'no-terminal': 'No terminal punctuation',
            'comma':       'Ends with comma',
            'semicolon':   'Ends with semicolon',
            'colon':       'Ends with colon',
        }
        groups: dict[str, list[dict]] = defaultdict(list)
        for it in items:
            groups[it['category']].append(it)
        order = [c for c in ('no-terminal', 'comma', 'semicolon', 'colon') if c in groups]
        parts.append('<nav>' + ' '.join(
            f'<a href="#{c}">{escape(cat_labels[c])} ({len(groups[c])})</a>' for c in order
        ) + '</nav>\n')
        parts.append(
            '<p class="note">Each card renders the production summary face for one body that does not end '
            'at a clean phrase delimiter. <b>KEEP</b> = genre-conventional fragment (Sappho, Heraclitus). '
            '<b>RE-EXTRACT</b> = truncation; pass through Stage 1 to find a clean phrase end. The '
            '<b>● src</b> dot means a full-poem source already exists in <code>corpus/_sources/</code>; '
            '<b>○ src</b> means the source needs fetching first.</p>\n'
        )
        for cat in order:
            parts.append(f'<a id="{cat}"></a><h1>{escape(cat_labels[cat])} — {len(groups[cat])}</h1>\n')
            for it in sorted(groups[cat], key=lambda x: (x['author'], x['id'])):
                parts.append(card_unterminated(it, rel))

    parts.append('</body></html>\n')
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(''.join(parts))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--mode', choices=('extracts', 'unterminated'), default='extracts')
    ap.add_argument('--out-html',        type=Path)
    ap.add_argument('--out-renders-dir', type=Path)
    ap.add_argument('--force', action='store_true', help='re-render PNGs even when cached')
    ap.add_argument('--ids', nargs='*', help='restrict to a specific set of text ids')
    args = ap.parse_args()

    defaults = MODE_PATHS[args.mode]
    out_html = args.out_html or defaults['html']
    renders_dir = args.out_renders_dir or defaults['renders']

    items = load_items(args.mode, set(args.ids) if args.ids else None)
    print(f"{len(items)} sidecars matching mode={args.mode}")
    if not items:
        sys.exit(f"nothing to render for mode={args.mode}")

    rendered, skipped, failed = render_pngs(items, renders_dir, args.force)
    print(f"  rendered {rendered}  cached {skipped}  failed {len(failed)}")
    for tid, err in failed[:5]:
        print(f"    {tid}: {err[:80]}")
    if failed and len(failed) > 5:
        print(f"    ... and {len(failed)-5} more")

    build_html(args.mode, items, renders_dir, out_html)
    print(f"Wrote {out_html}  ({out_html.stat().st_size//1024}KB)")
    if args.mode == 'extracts':
        n_full = sum(1 for it in items if it['is_full'])
        print(f"  FULL:     {n_full}")
        print(f"  FRAGMENT: {len(items) - n_full}")
    else:
        n_keep = sum(1 for it in items if it['action'] == 'KEEP')
        n_re   = sum(1 for it in items if it['action'] == 'RE-EXTRACT')
        n_src  = sum(1 for it in items if it['has_source'])
        print(f"  KEEP suggested:       {n_keep}")
        print(f"  RE-EXTRACT suggested: {n_re}")
        print(f"  with source ready:    {n_src}")
        print(f"  needs source fetch:   {len(items) - n_src}")


if __name__ == '__main__':
    main()

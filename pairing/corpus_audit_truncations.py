"""Audit corpus text bodies for truncation patterns.

Three signals:
  - dangling-word : last token is a function word (article / preposition /
                    auxiliary / conjunction / relative pronoun) AND the
                    body doesn't end with terminal punctuation. Strongest
                    signal of mid-clause cut.
  - comma         : body ends with a comma. Often means the next line of
                    the source carries the thought to its close.
  - no-terminal   : body has no recognized phrase delimiter at the end.
                    Mixed bag — sometimes intentional (Blake quatrains,
                    Dickinson dashes), often a real truncation.

Each entry is reported with id, form, and the last 60 chars of the body
so the operator can scan and triage. Items belonging to a fragmentary-
genre author (Sappho, Heraclitus, etc.) are still flagged but should
typically be kept.

Use this as a recurring quality check after large ingest runs. The
matching review page (with rendered summary-face PNGs per item) is
built by `corpus build-review-page --mode unterminated`.

Usage:
  corpus_audit_truncations.py                  # walks all of corpus
  corpus_audit_truncations.py --ids id1 id2    # only those
"""
from __future__ import annotations
import argparse, re, sys
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / 'corpus'

# Function words that, when ending a body without terminal punctuation,
# almost always mean the sentence is truncated.
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


def body_of(d: dict) -> str:
    tv = d.get('text_variants') or {}
    if isinstance(tv, dict) and tv:
        return tv.get('en') or next(iter(tv.values())) or ''
    return d.get('text') or ''


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--ids', nargs='*', help='restrict to a specific set of ids')
    args = ap.parse_args()
    only = set(args.ids) if args.ids else None

    flags: list[dict] = []
    walked = 0
    for sub in ('texts', 'personal_library', 'images'):
        d = CORPUS / sub
        if not d.is_dir(): continue
        for p in sorted(d.glob('*.yaml')):
            if p.name.startswith('EXAMPLE'): continue
            try:
                doc = yaml.safe_load(p.read_text())
            except Exception:
                continue
            if not doc: continue
            if only and doc.get('id') not in only: continue
            walked += 1
            body = body_of(doc)
            if not body: continue
            text = body.rstrip()
            if not text: continue
            last_char = text[-1]
            m = re.search(r'(\w+)\W*$', text)
            last_word = (m.group(1).lower() if m else '')
            ends_clean = last_char in TERMINAL_OK
            ends_comma = last_char == ','
            dangler = last_word in DANGLERS
            if (dangler and not ends_clean) or ends_comma:
                reason = 'comma' if ends_comma else 'dangling-word'
            elif not ends_clean and last_char not in ';:':
                reason = 'no-terminal'
            else:
                continue
            flags.append({
                'id': doc.get('id'),
                'folder': sub,
                'form': doc.get('form') or '?',
                'reason': reason,
                'tail': text.split('\n')[-1][-60:],
                'last_word': last_word,
                'last_char': last_char,
            })

    order = {'comma': 0, 'dangling-word': 1, 'no-terminal': 2}
    flags.sort(key=lambda f: (order.get(f['reason'], 9), f['id']))
    by_reason: dict[str, list[dict]] = defaultdict(list)
    for f in flags:
        by_reason[f['reason']].append(f)

    print(f"Walked {walked} sidecars; flagged {len(flags)}.")
    for r in ('comma', 'dangling-word', 'no-terminal'):
        if r not in by_reason: continue
        print(f"\n=== {r} ({len(by_reason[r])}) ===")
        for f in by_reason[r]:
            print(f"  {f['id']:<48s} form={f['form']:<12s} ...{f['tail']!r}")
    return 0


if __name__ == '__main__':
    sys.exit(main())

"""Extract full poem sources from the operator's Calibre library.

For each candidate sidecar (per /tmp/rework-candidates.yaml), find the
collected-works EPUB or PDF in /Volumes/Media/Calibre-mini, extract the
poem matching the sidecar's title or first body line, and write to
corpus/_sources/<author-slug>/<sidecar-id>.txt.

Output is read-only context for the two-stage extract→pill pipeline. Not
shipped to the device; not committed to git (corpus/_sources/ is ignored).
"""
from __future__ import annotations
import argparse, html as ihtml, io, json, re, subprocess, sys, tempfile, unicodedata, zipfile
from pathlib import Path
from collections import Counter, defaultdict

import yaml

EBOOK_CONVERT = '/Applications/calibre.app/Contents/MacOS/ebook-convert'

CALIBRE = Path('/Volumes/Media/Calibre-mini')
CORPUS  = Path(__file__).resolve().parent.parent / 'corpus'
OUT     = CORPUS / '_sources'
CAND    = Path('/tmp/rework-candidates.yaml')

# Hand-authored author → Calibre-folder mapping where exact-name lookup
# is ambiguous or wrong (mostly accent / spelling normalization).
AUTHOR_FOLDER_OVERRIDES = {
    'T. S. Eliot':       ['T. S. Eliot', 'T.S. Eliot'],
    'T.S. Eliot':        ['T. S. Eliot', 'T.S. Eliot'],
    'W. B. Yeats':       ['W. B. Yeats', 'W.B.Yeats (edt)', 'William Butler Yeats'],
    'Constantine P. Cavafy': ['Constantine P. Cavafy', 'C. P. Cavafy', 'Constantine Cavafy', 'C.P. Cavafy'],
    'Rainer Maria Rilke':['Rainer Maria Rilke'],
    'Wallace Stevens':   ['Wallace Stevens'],
    'Emily Dickinson':   ['Emily Dickinson'],
    'William Blake':     ['William Blake'],
    'Robert Frost':      ['Robert Frost'],
    'Ezra Pound':        ['Ezra Pound'],
    'Sylvia Plath':      ['Sylvia Plath'],
}

def slug(s: str) -> str:
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()
    s = re.sub(r'[^a-zA-Z0-9]+', '-', s).strip('-').lower()
    return s or 'unknown'


def _name_norm(s: str) -> str:
    """Normalize an author name for matching: strip diacritics, lowercase,
    remove punctuation, collapse whitespace. 'Alfred, Lord Tennyson' →
    'alfred lord tennyson'. 'Matsuo Bashō' → 'matsuo basho'."""
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()
    s = s.lower()
    s = re.sub(r'[^a-z0-9 ]+', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


def find_calibre_folders(author: str) -> list[Path]:
    """Return Calibre folders for an author.
    1. Override list (hand-mapped).
    2. Exact name match.
    3. Fuzzy: normalized-name equality, then surname-only equality.
    Tie-break: shortest folder name (most likely the canonical author,
    not a coauthor or critic)."""
    candidates = AUTHOR_FOLDER_OVERRIDES.get(author, [author])
    found = [CALIBRE / c for c in candidates if (CALIBRE / c).is_dir()]
    if found: return found

    # Walk the top-level once and build a normalized index
    if not hasattr(find_calibre_folders, '_index'):
        idx: dict[str, list[Path]] = {}
        sur_idx: dict[str, list[Path]] = {}
        for p in CALIBRE.iterdir():
            if not p.is_dir() or p.name.startswith('.'): continue
            n = _name_norm(p.name)
            if not n: continue
            idx.setdefault(n, []).append(p)
            # surname = last token
            sur = n.split()[-1] if n.split() else ''
            if sur: sur_idx.setdefault(sur, []).append(p)
        find_calibre_folders._index = (idx, sur_idx)
    idx, sur_idx = find_calibre_folders._index
    n_author = _name_norm(author)
    if n_author in idx:
        return sorted(idx[n_author], key=lambda p: len(p.name))
    # Surname fallback — only if surname is unique enough (≤3 collisions)
    surname = n_author.split()[-1] if n_author.split() else ''
    sur_hits = sur_idx.get(surname, []) if surname else []
    if sur_hits and len(sur_hits) <= 3:
        # Filter to entries whose normalized name shares the first or
        # second token with the author (forename or middle), to avoid
        # matching unrelated authors who happen to share a surname.
        toks = set(n_author.split())
        matches = [p for p in sur_hits if toks & set(_name_norm(p.name).split())]
        if matches:
            return sorted(matches, key=lambda p: len(p.name))
    return []


def list_books(author_folder: Path) -> list[Path]:
    """Subfolders inside an author folder are individual books."""
    return [p for p in sorted(author_folder.iterdir()) if p.is_dir()]


# ---------- EPUB extraction ----------

XHTML_TAG = re.compile(r'<[^>]+>')
WS = re.compile(r'[ \t]+')
BLANK = re.compile(r'\n{3,}')

def book_to_text(path: Path) -> str:
    """Dispatch on extension. EPUB/KEPUB → zip+xhtml. PDF → PyMuPDF.
    MOBI/AZW3 → calibre's ebook-convert via TXT roundtrip."""
    ext = path.suffix.lower()
    if ext in ('.epub', '.kepub'):
        return epub_to_text(path)
    if ext == '.pdf':
        return pdf_to_text(path)
    if ext in ('.mobi', '.azw3', '.azw'):
        return ebook_convert_to_text(path)
    return ''


def pdf_to_text(pdf_path: Path) -> str:
    """Extract text via PyMuPDF preserving line breaks (poetry-friendly).
    PyMuPDF's `get_text('text')` yields one block per visual paragraph;
    line breaks within a block are kept."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return ''
    try:
        doc = fitz.open(pdf_path)
    except Exception:
        return ''
    out: list[str] = []
    for page in doc:
        out.append(page.get_text('text'))
    doc.close()
    return '\n\n'.join(out).strip() + '\n'


def ebook_convert_to_text(path: Path) -> str:
    """Universal converter for MOBI/AZW3 via calibre's ebook-convert. Writes
    a temp .txt, reads it back, deletes."""
    if not Path(EBOOK_CONVERT).exists():
        return ''
    with tempfile.TemporaryDirectory() as td:
        out_txt = Path(td) / 'out.txt'
        try:
            subprocess.run(
                [EBOOK_CONVERT, str(path), str(out_txt), '--enable-heuristics'],
                check=True, capture_output=True, timeout=120,
            )
            return out_txt.read_text(errors='replace')
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            return ''


def epub_to_text(epub_path: Path) -> str:
    """Concatenate all .xhtml/.html spine entries into plain text. Preserves
    paragraph and line breaks; collapses tags. Adequate for poetry where the
    publisher uses <p> per stanza and <br/> per line."""
    out: list[str] = []
    try:
        with zipfile.ZipFile(epub_path) as z:
            names = sorted(z.namelist())
            spine = [n for n in names if n.lower().endswith(('.xhtml','.html','.htm','.xml'))
                     and 'META-INF' not in n and 'container' not in n.lower()]
            for n in spine:
                try:
                    data = z.read(n).decode('utf-8', errors='replace')
                except Exception:
                    continue
                # Drop scripts/styles
                data = re.sub(r'<(script|style)[\s\S]*?</\1>', '', data, flags=re.I)
                # <br/> → newline
                data = re.sub(r'<br\s*/?>', '\n', data, flags=re.I)
                # Block boundaries → newline
                data = re.sub(r'</(p|div|h[1-6]|li|tr|td|article|section)>', '\n', data, flags=re.I)
                # Strip remaining tags
                data = XHTML_TAG.sub('', data)
                # HTML entities
                data = ihtml.unescape(data)
                out.append(data)
    except zipfile.BadZipFile:
        return ''
    text = '\n'.join(out)
    # Normalize whitespace
    text = WS.sub(' ', text)
    text = re.sub(r' *\n', '\n', text)
    text = BLANK.sub('\n\n', text)
    return text.strip() + '\n'


# ---------- Book selection ----------

# Title-level scoring: completeness wins over format bias. "Complete" /
# "Collected" rank highest; "Best of" / "Selected" / "Selection" next; raw
# poetry collections (no completeness modifier) get a small boost.
TITLE_RX = [
    (re.compile(r'\b(complete|collected)\b.*\b(poems?|works|poetry)\b', re.I), 12),
    (re.compile(r'\bbest of\b', re.I),                                          10),
    (re.compile(r'\b(selected)\b.*\bpoems?\b', re.I),                            9),
    (re.compile(r'\bselection\b.*\bpoems?\b', re.I),                             9),
    (re.compile(r'\bpoems?\b', re.I),                                            3),
]
TITLE_RX_PENALTY = [
    (re.compile(r'\bessays?\b', re.I), -8),
    (re.compile(r'\b(plays?|drama|cathedral|murder)\b', re.I), -6),
    (re.compile(r'\b(letters?|notebooks?|guide)\b', re.I), -6),
    (re.compile(r'\b(prophecy|sonnets to)\b', re.I), -3),  # genre-specific subset
]
# Format preference — EPUB best (clean XHTML), KEPUB ≈ EPUB, then PDF, then
# MOBI/AZW3 (need ebook-convert). Higher score = preferred.
FORMAT_PRIORITY = {'.epub': 5, '.kepub': 5, '.pdf': 3, '.mobi': 2, '.azw3': 2, '.azw': 1}

def pick_book_files(author_folders: list[Path]) -> list[tuple[Path, Path]]:
    """Pick the most useful book files for an author. Returns list of
    (book_dir, file) ranked best→worst across all books in all folders."""
    scored: list[tuple[int, Path, Path]] = []
    for af in author_folders:
        for book_dir in list_books(af):
            title = book_dir.name.lower()
            t_score = 0
            for rx, w in TITLE_RX:
                if rx.search(title):
                    t_score = max(t_score, w)
                    break
            for rx, w in TITLE_RX_PENALTY:
                if rx.search(title):
                    t_score += w
            # Walk all files in book_dir, score per format
            for f in sorted(book_dir.iterdir()):
                ext = f.suffix.lower()
                if ext not in FORMAT_PRIORITY: continue
                fmt_score = FORMAT_PRIORITY[ext]
                scored.append((t_score * 10 + fmt_score, book_dir, f))
    scored.sort(key=lambda t: -t[0])
    # Dedup per book_dir — keep best format only
    seen: set[Path] = set()
    out: list[tuple[Path, Path]] = []
    for _, bd, f in scored:
        if bd in seen: continue
        seen.add(bd)
        out.append((bd, f))
    return out


# ---------- Poem location within full text ----------

def normalize(s: str) -> str:
    s = unicodedata.normalize('NFKD', s).encode('ascii','ignore').decode()
    s = s.lower()
    s = re.sub(r'[^a-z0-9]+', ' ', s).strip()
    return s

def first_lines(body: str, k: int = 3) -> list[str]:
    out = []
    for ln in body.splitlines():
        s = ln.strip()
        if not s: continue
        out.append(s)
        if len(out) >= k: break
    return out

def find_poem_window(full: str, sidecar: dict) -> tuple[int, int] | None:
    """Locate the poem in the full text. Strategy:
    1. Try matching the FIRST line of the body (most reliable for excerpts).
    2. Fall back to title.
    Returns (start_offset, end_offset) covering ~80 lines of context, or
    None if neither matches."""
    body = sidecar['body']
    title = sidecar.get('title') or ''
    fl = first_lines(body, k=2)
    full_norm = normalize(full)

    # 1. First-line match — try first 2 in case the first is an idiom that
    # repeats elsewhere (e.g. "Once more" appears across multiple poems)
    for line in fl:
        ln_norm = normalize(line)
        if len(ln_norm) < 12:  # too short, false positives likely
            continue
        idx = full_norm.find(ln_norm)
        if idx >= 0:
            return _expand_window(full, full_norm, idx, ln_norm)
    # 2. Title — only if not a generic word
    if title:
        # Strip parenthetical hints "Easter, 1916 (opening)" → "Easter, 1916"
        clean_title = re.sub(r'\s*\([^)]*\)\s*$', '', title).strip()
        if clean_title and len(clean_title) > 4:
            t_norm = normalize(clean_title)
            idx = full_norm.find(t_norm)
            if idx >= 0:
                return _expand_window(full, full_norm, idx, t_norm)
    return None

def _expand_window(full: str, full_norm: str, hit_idx: int, hit_norm: str) -> tuple[int, int]:
    """Map a normalized-text hit back to the original text and grab a window
    of ~120 lines centered on the hit (poems are short; 120 lines ≈ a long
    poem with whitespace)."""
    # Map the normalized index back to the source by counting characters
    # in `full` until we've consumed `hit_idx` normalized chars.
    src_pos = _norm_to_src(full, hit_idx)
    # Tight windowing: prefer blank-line boundary (multi-poem EPUBs with
    # paragraph separators), but cap aggressively in chars AND in newlines.
    # Coradella-style flat dumps have no blank lines between poems; without a
    # cap the window slurps 2-3 neighboring poems.
    BACK_CHARS, BACK_LINES = 1000, 25
    FWD_CHARS, FWD_LINES   = 2000, 50
    back = 0; blanks = 0; nl_count = 0
    while src_pos - back > 0 and back < BACK_CHARS:
        c = full[src_pos - back - 1]
        if c == '\n':
            nl_count += 1
            if src_pos - back - 2 >= 0 and full[src_pos - back - 2] == '\n':
                blanks += 1
                if blanks >= 2: break
            if nl_count >= BACK_LINES: break
        back += 1
    start = max(0, src_pos - back)
    fwd = 0; blanks = 0; nl_count = 0
    while src_pos + fwd < len(full) and fwd < FWD_CHARS:
        c = full[src_pos + fwd]
        if c == '\n':
            nl_count += 1
            if src_pos + fwd + 1 < len(full) and full[src_pos + fwd + 1] == '\n':
                blanks += 1
                if blanks >= 2: break
            if nl_count >= FWD_LINES: break
        fwd += 1
    end = min(len(full), src_pos + fwd)
    return (start, end)

def _norm_to_src(full: str, norm_idx: int) -> int:
    """Walk `full` and count how many chars survive normalization until we
    reach `norm_idx`; return source index."""
    src = 0
    norm_count = 0
    skip_run = False
    while src < len(full) and norm_count < norm_idx:
        c = full[src]
        nc = unicodedata.normalize('NFKD', c).encode('ascii','ignore').decode().lower()
        if nc and nc.isalnum():
            norm_count += 1
            skip_run = False
        else:
            if not skip_run and norm_count > 0:
                norm_count += 1
                skip_run = True
        src += 1
    return src


# ---------- Main ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--top', type=int, default=10, help='process top-N authors by candidate count')
    ap.add_argument('--author', action='append', help='restrict to a specific author (repeatable)')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    if not CAND.exists():
        sys.exit(f"missing candidate list: {CAND}")
    if not CALIBRE.is_dir():
        sys.exit(f"calibre library not mounted at {CALIBRE}")

    candidates = yaml.safe_load(CAND.read_text()) or []
    print(f"Loaded {len(candidates)} candidates")

    by_author: dict[str, list[dict]] = defaultdict(list)
    for c in candidates:
        # Read body from sidecar
        sub = c['folder']
        p = CORPUS / sub / f"{c['id']}.yaml"
        try:
            d = yaml.safe_load(p.read_text())
        except Exception:
            continue
        body = ''
        tv = d.get('text_variants') or {}
        if isinstance(tv, dict) and tv:
            body = tv.get('en') or next(iter(tv.values())) or ''
        c['body'] = body
        c['title'] = d.get('title') or c.get('title') or ''
        by_author[c['author']].append(c)

    # Pick top-N authors by candidate count, or use --author overrides
    if args.author:
        target_authors = [a for a in args.author if a in by_author]
    else:
        ranked = sorted(by_author.items(), key=lambda t: -len(t[1]))
        target_authors = [a for a,_ in ranked[:args.top]]
    print(f"Targeting {len(target_authors)} authors:")
    for a in target_authors:
        print(f"  {len(by_author[a]):>3d}  {a}")

    stats = Counter()
    missing: list[tuple[str,str]] = []
    epub_cache: dict[str, str] = {}    # epub_path → full_text

    for author in target_authors:
        print(f"\n=== {author} ({len(by_author[author])} candidates) ===")
        folders = find_calibre_folders(author)
        if not folders:
            print(f"  ! no Calibre folder found")
            stats['author-not-found'] += 1
            for c in by_author[author]: missing.append((c['id'], 'no-author-folder'))
            continue
        books = pick_book_files(folders)
        if not books:
            print(f"  ! no usable book files")
            stats['no-books'] += 1
            for c in by_author[author]: missing.append((c['id'], 'no-books'))
            continue
        # Use the top-scoring EPUB as primary; if not available, PDF
        primary_book, primary_file = books[0]
        print(f"  using: {primary_book.name}/{primary_file.name}")
        # Extract once, cache
        key = str(primary_file)
        if key not in epub_cache:
            text = book_to_text(primary_file)
            if not text:
                print(f"  ! extraction failed for {primary_file.suffix}")
                stats[f'extract-failed-{primary_file.suffix}'] += 1
                for c in by_author[author]: missing.append((c['id'], f'extract-failed-{primary_file.suffix}'))
                continue
            epub_cache[key] = text
            print(f"  extracted {len(text)//1024}KB plain text")
        full = epub_cache[key]
        # Per-sidecar: find and write
        author_dir = OUT / slug(author)
        if not args.dry_run:
            author_dir.mkdir(parents=True, exist_ok=True)
            full_path = author_dir / 'full.txt'
            if not full_path.exists():
                full_path.write_text(full)
        for c in by_author[author]:
            window = find_poem_window(full, c)
            if not window:
                print(f"    ! {c['id']}  not found")
                missing.append((c['id'], 'poem-not-located'))
                stats['not-located'] += 1
                continue
            start, end = window
            poem = full[start:end].strip() + '\n'
            stats['located'] += 1
            if args.dry_run:
                print(f"    ✓ {c['id']}  {end-start}c")
            else:
                out_path = author_dir / f"{c['id']}.txt"
                out_path.write_text(poem)
                print(f"    ✓ {c['id']}  {end-start}c → {out_path.relative_to(CORPUS)}")

    print(f"\n=== SUMMARY ===")
    for k,v in stats.most_common():
        print(f"  {k:<25s} {v}")
    if missing:
        print(f"\nMissing ({len(missing)}):")
        miss_by_reason: dict[str,list[str]] = defaultdict(list)
        for tid, why in missing:
            miss_by_reason[why].append(tid)
        for why, ids in miss_by_reason.items():
            print(f"  {why} ({len(ids)}):")
            for tid in ids[:8]: print(f"    {tid}")
            if len(ids) > 8: print(f"    ... +{len(ids)-8} more")

if __name__ == '__main__':
    main()

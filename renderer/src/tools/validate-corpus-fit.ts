/**
 * Corpus fit validator.
 *
 * Checks every text item in the corpus against the empirical body-budget
 * table and the step-down sizing rule. Items that cannot fit at any size
 * down to the 25u floor are rejected.
 *
 * Budget (with title + attribution; body area ~540u × 960u):
 *   size | 1col lines | 1col chars | 2col lines | 2col chars
 *   54u  |  7         | 36         | 14         | 16
 *   52u  |  7         | 37         | 14         | 17
 *   48u  |  8         | 40         | 16         | 18
 *   44u  |  9         | 44         | 18         | 20
 *   42u  |  9         | 45         | 16         | 21
 *   36u  | 11         | 53         | 20         | 24
 *   32u  | 12         | 60         | 22         | 27
 *   28u  | 14         | 68         | 24         | 31
 *   25u  | 16         | 76         | 28         | 35
 *
 * Step-down: starting at the form's default size, try each candidate in
 * [default, 36, 32, 28, 25] first at 1 column then at 2. First fit wins.
 * None → REJECT.
 *
 * Usage:
 *   tsx src/tools/validate-corpus-fit.ts          # report only
 *   tsx src/tools/validate-corpus-fit.ts --fix    # append fits_device/rejection_reason to rejected YAMLs
 */
import fs from 'node:fs/promises';
import path from 'node:path';

const CORPUS = path.resolve(process.cwd(), '../corpus');
const TEXT_DIRS = ['texts', 'personal_library'];
const IMAGE_DIRS = ['images', 'nocturne', 'personal_library'];

const GALLERY_TITLE_CAP = 20;
const GALLERY_ATTRIB_CAP = 32;

type ColBudget = [maxLines: number, maxChars: number];
// Budget when title is shown (hero zone has title + body + attribution).
const BUDGET_WITH_TITLE: Record<number, { 1: ColBudget; 2: ColBudget }> = {
  54: { 1: [7, 36],  2: [14, 16] },
  52: { 1: [7, 37],  2: [14, 17] },
  48: { 1: [8, 40],  2: [16, 18] },
  44: { 1: [9, 44],  2: [18, 20] },
  42: { 1: [9, 45],  2: [16, 21] },
  36: { 1: [11, 53], 2: [20, 24] },
  32: { 1: [12, 60], 2: [22, 27] },
  28: { 1: [14, 68], 2: [24, 31] },
  25: { 1: [16, 76], 2: [28, 35] },
};
// Budget when title is suppressed — ~2 extra lines per config.
const BUDGET_NO_TITLE: Record<number, { 1: ColBudget; 2: ColBudget }> = {
  54: { 1: [9, 36],  2: [18, 16] },
  52: { 1: [9, 37],  2: [18, 17] },
  48: { 1: [10, 40], 2: [20, 18] },
  44: { 1: [11, 44], 2: [22, 20] },
  42: { 1: [11, 45], 2: [20, 21] },
  36: { 1: [13, 53], 2: [24, 24] },
  32: { 1: [14, 60], 2: [26, 27] },
  28: { 1: [17, 68], 2: [30, 31] },
  25: { 1: [18, 76], 2: [32, 35] },
};

const FORM_DEFAULT_SIZE: Record<string, number> = {
  haiku: 54, tanka: 54,
  aphorism: 52,
  fragment: 48,
  quote: 44,
  sonnet: 42, 'free-verse': 42, stanzaic: 42, lyric: 42, song: 42,
  'prose-poem': 36,
};

const STEP_DOWN = [42, 36, 32, 28, 25];

type Doc = {
  id?: string; form?: string; show_title?: boolean; text_variants: Record<string, string>;
  // Image-item fields:
  title?: string; artist?: string; year?: string;
  display_title?: string; display_attribution?: string;
};

// Minimal YAML reader for our fixed schema.
function parseCorpusYaml(raw: string): Doc {
  const lines = raw.split('\n');
  const out: Doc = { text_variants: {} };
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const m = line.match(/^(id|form|title|artist|year|display_title|display_attribution):\s*(.+?)\s*$/);
    if (m) {
      (out as any)[m[1]] = m[2].replace(/^["']|["']$/g, '');
      i++; continue;
    }
    if (/^render:\s*$/.test(line)) {
      i++;
      while (i < lines.length && /^  \S/.test(lines[i])) {
        const rm = lines[i].match(/^  show_title:\s*(true|false)\s*$/);
        if (rm) out.show_title = rm[1] === 'true';
        i++;
      }
      continue;
    }
    if (/^text_variants:\s*$/.test(line)) {
      i++;
      while (i < lines.length) {
        const lm = lines[i].match(/^  ([a-z]{2,3}):\s*\|[-+]?\s*$/);
        if (!lm) break;
        const lang = lm[1]; i++;
        const body: string[] = [];
        while (i < lines.length) {
          const bl = lines[i];
          if (bl.startsWith('    ')) body.push(bl.slice(4));
          else if (bl.trim() === '') body.push('');
          else break;
          i++;
        }
        out.text_variants[lang] = body.join('\n').replace(/\n+$/, '');
      }
      continue;
    }
    i++;
  }
  return out;
}

function bodyStats(body: string): { lines: number; maxChars: number } {
  const logical = body.split('\n').filter((l) => l.trim().length > 0);
  const maxChars = logical.reduce((m, l) => Math.max(m, [...l].length), 0);
  return { lines: logical.length, maxChars };
}

function tryFit(stats: { lines: number; maxChars: number }, sizes: number[], showTitle: boolean): { size: number; cols: 1 | 2 } | null {
  const table = showTitle ? BUDGET_WITH_TITLE : BUDGET_NO_TITLE;
  for (const size of sizes) {
    for (const cols of [1, 2] as const) {
      const b = table[size]?.[cols];
      if (!b) continue;
      const [maxL, maxC] = b;
      if (stats.lines <= maxL && stats.maxChars <= maxC) return { size, cols };
    }
  }
  return null;
}

type Result = {
  file: string; dir: string; id: string; form: string; lang: string; showTitle: boolean;
  lines: number; maxChars: number;
  fit: { size: number; cols: 1 | 2 } | null;
  defaultSize: number;
};

async function loadTextItems() {
  const items: Array<{ dir: string; name: string; filepath: string; doc: Doc }> = [];
  for (const dir of TEXT_DIRS) {
    const full = path.join(CORPUS, dir);
    const entries = await fs.readdir(full).catch(() => []);
    for (const name of entries) {
      if (!name.endsWith('.yaml')) continue;
      const filepath = path.join(full, name);
      const raw = await fs.readFile(filepath, 'utf8');
      const doc = parseCorpusYaml(raw);
      if (!doc.form || Object.keys(doc.text_variants).length === 0) continue;
      items.push({ dir, name, filepath, doc });
    }
  }
  return items;
}

async function loadImageItems() {
  const items: Array<{ dir: string; name: string; filepath: string; doc: Doc }> = [];
  const seen = new Set<string>();
  for (const dir of IMAGE_DIRS) {
    const full = path.join(CORPUS, dir);
    const entries = await fs.readdir(full).catch(() => []);
    for (const name of entries) {
      if (!name.endsWith('.yaml')) continue;
      const filepath = path.join(full, name);
      if (seen.has(filepath)) continue;
      seen.add(filepath);
      const raw = await fs.readFile(filepath, 'utf8');
      const doc = parseCorpusYaml(raw);
      // Image items have `artist` (not `author`) and no `text_variants`.
      if (!doc.artist || Object.keys(doc.text_variants).length > 0) continue;
      items.push({ dir, name, filepath, doc });
    }
  }
  return items;
}

function rejectionReason(r: Result, showTitle: boolean): string {
  const floor = (showTitle ? BUDGET_WITH_TITLE : BUDGET_NO_TITLE)[25];
  const [maxL, maxC] = floor[1];
  const [maxL2, maxC2] = floor[2];
  const parts: string[] = [];
  if (r.lines > maxL) parts.push(`${r.lines} lines > ${maxL} (25u 1-col) / ${maxL2} (25u 2-col)`);
  if (r.maxChars > maxC) parts.push(`${r.maxChars} chars/line > ${maxC} (25u 1-col) / ${maxC2} (25u 2-col)`);
  return parts.join('; ') || 'exceeds budget';
}

const items = await loadTextItems();
const imageItems = await loadImageItems();
const results: Result[] = [];
for (const { dir, name, doc } of items) {
  const showTitle = doc.show_title !== false;
  for (const [lang, body] of Object.entries(doc.text_variants)) {
    const stats = bodyStats(body);
    const defaultSize = FORM_DEFAULT_SIZE[doc.form!] ?? 42;
    const sizes = [defaultSize, ...STEP_DOWN.filter((s) => s < defaultSize)];
    const fit = tryFit(stats, sizes, showTitle);
    results.push({ file: name, dir, id: doc.id ?? name.replace(/\.yaml$/, ''), form: doc.form!, lang, showTitle, ...stats, fit, defaultSize });
  }
}

// A text item is REJECTED if ALL of its language variants fail to fit.
// If any variant fits, keep the item; the renderer picks a language at runtime.
const byFile = new Map<string, Result[]>();
for (const r of results) {
  const key = `${r.dir}/${r.file}`;
  const arr = byFile.get(key) ?? [];
  arr.push(r);
  byFile.set(key, arr);
}

const fileVerdicts: Array<{ key: string; file: string; dir: string; id: string; rejected: boolean; results: Result[]; reason?: string }> = [];
for (const [key, rs] of byFile) {
  const anyFits = rs.some((r) => r.fit !== null);
  const rejected = !anyFits;
  const reason = rejected ? rs.map((r) => `${r.lang}: ${rejectionReason(r, r.showTitle)}`).join(' | ') : undefined;
  fileVerdicts.push({ key, file: rs[0].file, dir: rs[0].dir, id: rs[0].id, rejected, results: rs, reason });
}

const acceptedFiles = fileVerdicts.filter((v) => !v.rejected);
const rejectedFiles = fileVerdicts.filter((v) => v.rejected);

// --- Image caption validation --------------------------------------------
type ImageVerdict = {
  file: string; dir: string; id: string;
  titleChars: number; attribChars: number;
  rejected: boolean; reason?: string;
};
const imageVerdicts: ImageVerdict[] = [];
for (const { dir, name, doc } of imageItems) {
  const title = doc.display_title ?? doc.title ?? '';
  const titleChars = [...title].length;
  const composedAttrib = doc.display_attribution ?? (
    doc.artist ? `${doc.artist.toUpperCase()} · ${doc.year ?? ''}`.replace(/\s·\s$/, '') : ''
  );
  const attribChars = [...composedAttrib].length;
  const tooLongTitle = titleChars > GALLERY_TITLE_CAP;
  const tooLongAttrib = attribChars > GALLERY_ATTRIB_CAP;
  const rejected = tooLongTitle || tooLongAttrib;
  const reasonParts: string[] = [];
  if (tooLongTitle) reasonParts.push(`title ${titleChars} > ${GALLERY_TITLE_CAP}${doc.display_title ? '' : '; supply display_title'}`);
  if (tooLongAttrib) reasonParts.push(`attribution ${attribChars} > ${GALLERY_ATTRIB_CAP}${doc.display_attribution ? '' : '; supply display_attribution'}`);
  imageVerdicts.push({
    file: name, dir, id: doc.id ?? name.replace(/\.yaml$/, ''),
    titleChars, attribChars, rejected, reason: rejected ? reasonParts.join('; ') : undefined,
  });
}
const rejectedImages = imageVerdicts.filter((v) => v.rejected);
const acceptedImages = imageVerdicts.filter((v) => !v.rejected);

function fmt(r: Result): string {
  const verdict = r.fit ? `${r.fit.size}u ${r.fit.cols}col` : 'REJECT';
  return `  ${r.form.padEnd(12)} ${r.lang.padEnd(3)} ${r.id.padEnd(46)} lines=${String(r.lines).padStart(3)} max=${String(r.maxChars).padStart(3)}  →  ${verdict}`;
}

console.log(`\n[validate-corpus-fit] TEXT: ${items.length} items · ${results.length} variants   IMAGE: ${imageItems.length} items\n`);
console.log(`Text accepted: ${acceptedFiles.length}  rejected: ${rejectedFiles.length}`);
console.log(`Image accepted: ${acceptedImages.length}  rejected: ${rejectedImages.length}\n`);
if (rejectedFiles.length) {
  console.log('REJECTED texts:');
  for (const v of rejectedFiles) for (const r of v.results) console.log(fmt(r));
  console.log('');
}
if (rejectedImages.length) {
  console.log('REJECTED images (caption overflow):');
  for (const v of rejectedImages) {
    console.log(`  ${v.dir.padEnd(17)} ${v.id.padEnd(46)} title=${String(v.titleChars).padStart(3)} attrib=${String(v.attribChars).padStart(3)}  →  ${v.reason}`);
  }
}

const FIX = process.argv.includes('--fix');
if (FIX) {
  let annotated = 0;
  for (const v of rejectedFiles) {
    const filepath = path.join(CORPUS, v.dir, v.file);
    const raw = await fs.readFile(filepath, 'utf8');
    if (/^fits_device:/m.test(raw)) continue; // already annotated
    const trailing = raw.endsWith('\n') ? '' : '\n';
    const banner = [
      `fits_device: false`,
      `rejection_reason: "${v.reason!.replace(/"/g, '\\"')}"`,
      ``,
    ].join('\n');
    await fs.writeFile(filepath, raw + trailing + banner);
    annotated++;
  }
  console.log(`\n[validate-corpus-fit] annotated ${annotated} YAML files with fits_device: false`);
} else {
  console.log(`\n(Run with --fix to mark rejected YAMLs with fits_device: false.)`);
}

process.exit(0);

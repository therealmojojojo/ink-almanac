/**
 * Validate every text item in the corpus against the empirical fit budget.
 *
 * Budget table (empirical, with title + attribution, body area ~540×960):
 *   size | 1col lines | 1col chars | 2col lines | 2col chars
 *   42u  |  9         | 45         | 16         | 21
 *   36u  | 11         | 53         | 20         | 24
 *   32u  | 12         | 60         | 22         | 27
 *   28u  | 14         | 68         | 24         | 31
 *   25u  | 16         | 76         | 28         | 35
 *
 * Step-down: start at the form's default size, step through [default, 36, 32, 28, 25],
 * try 1-col first, then 2-col. First that fits wins. None → REJECT.
 */
import fs from 'node:fs/promises';
import path from 'node:path';

// Minimal YAML reader for our fixed schema: top-level `form:`, `id:`,
// and `text_variants:` with `  <lang>: |` block scalars.
function parseCorpusYaml(raw) {
  const lines = raw.split('\n');
  const out = { text_variants: {} };
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const m = line.match(/^(id|form):\s*(.+?)\s*$/);
    if (m) { out[m[1]] = m[2].replace(/^["']|["']$/g, ''); i++; continue; }
    if (/^text_variants:\s*$/.test(line)) {
      i++;
      while (i < lines.length) {
        const langLine = lines[i];
        const lm = langLine.match(/^  ([a-z]{2,3}):\s*\|[-+]?\s*$/);
        if (!lm) break;
        const lang = lm[1];
        i++;
        const body = [];
        while (i < lines.length) {
          const bl = lines[i];
          if (/^\S/.test(bl) && bl.trim() !== '') break;
          if (/^  \S/.test(bl) && !/^    /.test(bl) && bl.trim() !== '') break;
          // body lines start with at least 4 spaces (indent under the |)
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
const YAML = { parse: parseCorpusYaml };

const CORPUS = '${INKPLATE_REPO}/corpus';
const DIRS = ['texts', 'personal_library'];

const FORM_DEFAULT_SIZE = {
  haiku: 54, tanka: 54,
  aphorism: 52,
  fragment: 48,
  quote: 44,
  sonnet: 42, 'free-verse': 42, stanzaic: 42, lyric: 42,
  'prose-poem': 36,
  song: 42,
};

const BUDGET = {
  54: { '1': [7, 36], '2': [14, 16] },
  52: { '1': [7, 37], '2': [14, 17] },
  48: { '1': [8, 40], '2': [16, 18] },
  44: { '1': [9, 44], '2': [18, 20] },
  42: { '1': [9, 45], '2': [16, 21] },
  36: { '1': [11, 53], '2': [20, 24] },
  32: { '1': [12, 60], '2': [22, 27] },
  28: { '1': [14, 68], '2': [24, 31] },
  25: { '1': [16, 76], '2': [28, 35] },
};

const STEP_DOWN = [42, 36, 32, 28, 25]; // applied after form default

function bodyStats(body) {
  if (!body) return { lines: 0, maxChars: 0 };
  const raw = String(body).replace(/\r\n/g, '\n');
  const logicalLines = raw.split('\n').filter((l) => l.trim().length > 0);
  const maxChars = logicalLines.reduce((m, l) => Math.max(m, [...l].length), 0);
  // Count blank-line separators so stanzaic poems' whitespace is accounted for.
  const totalLines = raw.split('\n').length;
  return { lines: logicalLines.length, maxChars, totalLines };
}

function tryFit(stats, sizes) {
  for (const size of sizes) {
    for (const cols of [1, 2]) {
      const b = BUDGET[size]?.[String(cols)];
      if (!b) continue;
      const [maxLines, maxChars] = b;
      if (stats.lines <= maxLines && stats.maxChars <= maxChars) {
        return { size, cols };
      }
    }
  }
  return null;
}

async function loadTextItems() {
  const items = [];
  for (const dir of DIRS) {
    const full = path.join(CORPUS, dir);
    const entries = await fs.readdir(full).catch(() => []);
    for (const name of entries) {
      if (!name.endsWith('.yaml')) continue;
      const filepath = path.join(full, name);
      const raw = await fs.readFile(filepath, 'utf8');
      let doc;
      try { doc = YAML.parse(raw); } catch { continue; }
      if (!doc?.form || !doc?.text_variants) continue; // skip images
      items.push({ dir, name, filepath, doc });
    }
  }
  return items;
}

const items = await loadTextItems();
const results = [];

for (const { dir, name, doc } of items) {
  const langs = Object.keys(doc.text_variants || {});
  for (const lang of langs) {
    const body = doc.text_variants[lang];
    const stats = bodyStats(body);
    const defaultSize = FORM_DEFAULT_SIZE[doc.form] ?? 42;
    const sizes = [defaultSize, ...STEP_DOWN.filter((s) => s < defaultSize)];
    const fit = tryFit(stats, sizes);
    results.push({
      dir, file: name, id: doc.id, form: doc.form, lang,
      lines: stats.lines, maxChars: stats.maxChars,
      fit: fit ? `${fit.size}u ${fit.cols}col` : 'REJECT',
      defaultSize,
    });
  }
}

// Group by fit outcome
const groups = { fitsAtDefault: [], fitsAfterStepdown: [], rejected: [] };
for (const r of results) {
  if (r.fit === 'REJECT') groups.rejected.push(r);
  else if (r.fit === `${r.defaultSize}u 1col` || r.fit === `${r.defaultSize}u 2col`) groups.fitsAtDefault.push(r);
  else groups.fitsAfterStepdown.push(r);
}

function fmt(r) {
  return `  ${r.form.padEnd(12)} ${r.lang.padEnd(3)} ${r.id.padEnd(46)} lines=${String(r.lines).padStart(3)} max=${String(r.maxChars).padStart(3)}  →  ${r.fit}`;
}

console.log(`\n=== Total: ${results.length} text variants across ${items.length} items ===\n`);
console.log(`Fits at form default size (${groups.fitsAtDefault.length}):`);
for (const r of groups.fitsAtDefault) console.log(fmt(r));
console.log(`\nFits after step-down (${groups.fitsAfterStepdown.length}):`);
for (const r of groups.fitsAfterStepdown) console.log(fmt(r));
console.log(`\nREJECTED — do not fit even at 25u (${groups.rejected.length}):`);
for (const r of groups.rejected) console.log(fmt(r));

await fs.writeFile(
  path.join(path.dirname(new URL(import.meta.url).pathname), 'corpus-fit-report.json'),
  JSON.stringify({ total: results.length, groups }, null, 2)
);

// Exit non-zero if any rejected
process.exit(groups.rejected.length === 0 ? 0 : 1);

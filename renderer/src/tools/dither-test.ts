/**
 * Six-image dither test harness.
 *
 * Renders each input through the image-prep + dither chain and emits:
 *   - `docs/dither-test-results.md` with per-item before/after and a fidelity note
 *   - An HTML page at GET /dither-test for in-browser inspection
 *
 * Test images live under `renderer/test/dither/` and are curated by hand per
 * category: etching, woodblock, photograph-FSA, chiaroscuro, color-painting,
 * color-photography.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import { ROOT } from '../config.js';
import { prepare } from '../image/prep.js';

const DITHER_DIR = path.join(ROOT, 'test/dither');
const OUT_DIR = path.join(ROOT, 'test/dither/out');
const DOC_DIR = path.resolve(ROOT, '..', 'docs');

interface Item {
  file: string;
  category: string;
  note: string;
}

const ITEMS: Item[] = [
  { file: 'etching.jpg', category: 'etching', note: 'strong' },
  { file: 'woodblock.jpg', category: 'woodblock', note: 'strong' },
  { file: 'photograph-fsa.jpg', category: 'photograph-FSA', note: 'strong' },
  { file: 'chiaroscuro.jpg', category: 'chiaroscuro', note: 'strong' },
  { file: 'color-painting.jpg', category: 'color-painting', note: 'weak' },
  { file: 'color-photography.jpg', category: 'color-photography', note: 'weak' },
];

export async function runDitherTest(): Promise<void> {
  await fs.mkdir(OUT_DIR, { recursive: true });
  await fs.mkdir(DOC_DIR, { recursive: true });
  const md: string[] = [
    '# Dither test results',
    '',
    `Generated: ${new Date().toISOString()}`,
    '',
  ];
  for (const it of ITEMS) {
    const src = path.join(DITHER_DIR, it.file);
    let original: Buffer;
    try {
      original = await fs.readFile(src);
    } catch {
      md.push(`## ${it.category}`, '', `_MISSING: ${it.file}_`, '');
      continue;
    }
    const out = await prepare(original, { dither: true });
    const outFile = path.join(OUT_DIR, it.file.replace(/\.[^.]+$/, '.png'));
    await fs.writeFile(outFile, out);
    md.push(
      `## ${it.category} (${it.note})`,
      '',
      `![before](${path.relative(DOC_DIR, src)})`,
      `![after](${path.relative(DOC_DIR, outFile)})`,
      '',
      `_Fidelity: TODO — fill in after visual review._`,
      '',
    );
  }
  await fs.writeFile(path.join(DOC_DIR, 'dither-test-results.md'), md.join('\n'));
  console.log('[dither-test] wrote docs/dither-test-results.md');
}

export async function renderDitherTestPage(): Promise<string> {
  const rows = ITEMS.map(
    (it) => `<tr>
      <td>${it.category}<br><small>${it.note}</small></td>
      <td><img src="/inputs/../test/dither/${it.file}" style="max-width:400px"></td>
      <td><img src="/inputs/../test/dither/out/${it.file.replace(/\.[^.]+$/, '.png')}" style="max-width:400px"></td>
    </tr>`,
  ).join('');
  return `<!doctype html><html><head><title>Dither test</title><style>
  body { font-family: system-ui; padding: 2rem; }
  table { border-collapse: collapse; }
  td { padding: 1rem; border-bottom: 1px solid #ddd; vertical-align: top; }
  </style></head><body>
  <h1>Dither test</h1>
  <p>Run <code>npm run dither-test</code> to regenerate output PNGs.</p>
  <table><thead><tr><th>Category</th><th>Input</th><th>Output</th></tr></thead>
  <tbody>${rows}</tbody></table>
  </body></html>`;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  void runDitherTest();
}

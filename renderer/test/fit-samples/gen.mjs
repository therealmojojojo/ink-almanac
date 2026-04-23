import { chromium } from 'playwright';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..', '..');
const OUT = path.join(__dirname, 'out');
const FONTS = path.join(ROOT, 'templates/fonts');

const POEMS = {
  ozymandias: {
    title: 'Ozymandias',
    poet: 'Percy Bysshe Shelley',
    dates: '1792–1822',
    body: [
      'I met a traveller from an antique land',
      'Who said: Two vast and trunkless legs of stone',
      'Stand in the desert. Near them on the sand',
      'Half sunk, a shattered visage lies, whose frown',
      'And wrinkled lip and sneer of cold command',
      'Tell that its sculptor well those passions read',
      'Which yet survive, stamped on these lifeless things',
      'The hand that mocked them and the heart that fed',
      'And on the pedestal these words appear:',
      'My name is Ozymandias, King of Kings',
      'Look on my Works, ye Mighty, and despair!',
      'Nothing beside remains. Round the decay',
      'Of that colossal Wreck, boundless and bare',
      'The lone and level sands stretch far away',
    ].join('\n'),
  },
  brightStar: {
    title: 'Bright Star',
    poet: 'John Keats',
    dates: '1795–1821',
    body: [
      'Bright star, would I were stedfast as thou art—',
      'Not in lone splendour hung aloft the night',
      'And watching, with eternal lids apart,',
      'Like nature\u2019s patient, sleepless Eremite,',
      'The moving waters at their priestlike task',
      'Of pure ablution round earth\u2019s human shores,',
      'Or gazing on the new soft-fallen mask',
      'Of snow upon the mountains and the moors—',
      'No—yet still stedfast, still unchangeable,',
      'Pillow\u2019d upon my fair love\u2019s ripening breast,',
      'To feel for ever its soft fall and swell,',
      'Awake for ever in a sweet unrest,',
      'Still, still to hear her tender-taken breath,',
      'And so live ever—or else swoon to death.',
    ].join('\n'),
  },
  daffodils: {
    title: 'I Wandered Lonely as a Cloud',
    poet: 'William Wordsworth',
    dates: '1770–1850',
    body: [
      'I wandered lonely as a cloud',
      'That floats on high o\u2019er vales and hills,',
      'When all at once I saw a crowd,',
      'A host, of golden daffodils;',
      'Beside the lake, beneath the trees,',
      'Fluttering and dancing in the breeze.',
      '',
      'Continuous as the stars that shine',
      'And twinkle on the milky way,',
      'They stretched in never-ending line',
      'Along the margin of a bay:',
      'Ten thousand saw I at a glance,',
      'Tossing their heads in sprightly dance.',
      '',
      'The waves beside them danced; but they',
      'Out-did the sparkling waves in glee:',
      'A poet could not but be gay,',
      'In such a jocund company:',
      'I gazed—and gazed—but little thought',
      'What wealth the show to me had brought:',
      '',
      'For oft, when on my couch I lie',
      'In vacant or in pensive mood,',
      'They flash upon my inward eye',
      'Which is the bliss of solitude;',
      'And then my heart with pleasure fills,',
      'And dances with the daffodils.',
    ].join('\n'),
  },
};

// Each config: {size, cols, showTitle}
const CONFIGS = [
  { size: 42, cols: 2, showTitle: true,  label: '42u_2col_title' },
  { size: 36, cols: 1, showTitle: true,  label: '36u_1col_title' },
  { size: 32, cols: 1, showTitle: true,  label: '32u_1col_title' },
  { size: 28, cols: 1, showTitle: true,  label: '28u_1col_title' },
  { size: 25, cols: 1, showTitle: true,  label: '25u_1col_title' },
  { size: 25, cols: 1, showTitle: false, label: '25u_1col_notitle' },
  { size: 28, cols: 2, showTitle: true,  label: '28u_2col_title' },
  { size: 25, cols: 2, showTitle: true,  label: '25u_2col_title' },
];

function escapeHtml(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function buildHtml(poem, cfg) {
  const stanzas = poem.body
    .split(/\n\s*\n/)
    .filter((s) => s.trim())
    .map((stanza) => {
      const lines = stanza
        .split('\n')
        .map((ln) => `<div class="line">${escapeHtml(ln || '\u00a0')}</div>`)
        .join('');
      return `<div class="stanza">${lines}</div>`;
    })
    .join('');
  const attrib = `${poem.poet.toUpperCase()} · ${poem.dates}`;
  const titleHtml = cfg.showTitle ? `<div class="gt-title">${escapeHtml(poem.title)}</div>` : '';
  return `<!doctype html>
<html><head><meta charset="utf-8"><style>
@font-face {
  font-family: 'Fraunces';
  src: url('file://${FONTS}/Fraunces[opsz,wght].woff2') format('woff2-variations');
  font-weight: 100 900; font-style: normal; font-display: block;
}
@font-face {
  font-family: 'IBM Plex Mono';
  src: url('file://${FONTS}/IBMPlexMono-Regular.woff2') format('woff2');
  font-weight: 400; font-style: normal; font-display: block;
}
:root { --u: 1px; --ink:#000; --paper:#ececec; --mid:#000; --font-serif:'Fraunces',serif; --font-mono:'IBM Plex Mono',monospace; }
* { box-sizing: border-box; margin:0; padding:0; }
html, body { width: 1200px; height: 825px; background: var(--paper); color: var(--ink); font-weight: 500; -webkit-font-smoothing: antialiased; text-rendering: geometricPrecision; overflow: hidden; }
.gt-root { width: 1200px; height: 825px; padding: calc(72 * var(--u)) calc(96 * var(--u)); display: grid; grid-template-rows: 1fr auto; justify-items: center; align-items: center; position: relative; }
.gt-content { display: flex; flex-direction: column; align-items: flex-start; gap: calc(28 * var(--u)); max-width: 1008px; }
.gt-title { font-family: var(--font-serif); font-variation-settings: 'opsz' 144, 'wght' 500; font-size: calc(56 * var(--u)); line-height: 1.1; }
.gt-body { font-family: var(--font-serif); font-variation-settings: 'opsz' 36, 'wght' 500; line-height: 1.35; columns: ${cfg.cols}; column-gap: calc(72 * var(--u)); column-fill: balance; font-size: calc(${cfg.size} * var(--u)); }
.gt-body .stanza { break-inside: avoid; margin-bottom: calc(${Math.round(cfg.size * 0.6)} * var(--u)); }
.gt-body .stanza:last-child { margin-bottom: 0; }
.gt-body .line { white-space: pre-wrap; padding-left: calc(40 * var(--u)); text-indent: calc(-40 * var(--u)); }
.gt-attrib { font-family: var(--font-mono); font-size: calc(25 * var(--u)); text-transform: uppercase; letter-spacing: 0.14em; color: var(--mid); }
.gt-badge { position: absolute; top: 18px; left: 18px; font-family: var(--font-mono); font-size: 18px; letter-spacing: 0.1em; background: #fff; padding: 4px 10px; border: 1px solid #000; }
</style></head><body>
<div class="gt-root">
  <div class="gt-badge">${escapeHtml(cfg.label)} · ${escapeHtml(poem.title)}</div>
  <div class="gt-content">
    ${titleHtml}
    <div class="gt-body">${stanzas}</div>
  </div>
  <div class="gt-attrib">${escapeHtml(attrib)}</div>
</div>
</body></html>`;
}

const browser = await chromium.launch({ args: ['--font-render-hinting=none'] });
const ctx = await browser.newContext({ viewport: { width: 1200, height: 825 }, deviceScaleFactor: 1, colorScheme: 'light' });
const page = await ctx.newPage();

await fs.mkdir(OUT, { recursive: true });
const results = [];
for (const [pname, poem] of Object.entries(POEMS)) {
  for (const cfg of CONFIGS) {
    const html = buildHtml(poem, cfg);
    await page.setContent(html, { waitUntil: 'networkidle' });
    // Detect overflow: does the .gt-body exceed available height? We compute via bounding box.
    const overflow = await page.evaluate(() => {
      const body = document.querySelector('.gt-body');
      if (!body) return { overflow: false, contentH: 0, availH: 0 };
      const root = document.querySelector('.gt-root');
      const rootRect = root.getBoundingClientRect();
      const content = document.querySelector('.gt-content');
      const contentRect = content.getBoundingClientRect();
      const attrib = document.querySelector('.gt-attrib');
      const attribRect = attrib.getBoundingClientRect();
      const scrollH = body.scrollHeight;
      const clientH = body.clientHeight;
      const contentOverflows = scrollH > clientH + 1;
      const visualOverflow = contentRect.bottom > attribRect.top - 4;
      return { overflow: contentOverflows || visualOverflow, scrollH, clientH, contentBottom: contentRect.bottom, attribTop: attribRect.top };
    });
    const file = path.join(OUT, `${pname}_${cfg.label}.png`);
    await page.screenshot({ path: file, type: 'png', clip: { x: 0, y: 0, width: 1200, height: 825 } });
    results.push({ poem: pname, cfg: cfg.label, ...overflow, file: path.basename(file) });
    console.log(`${pname.padEnd(14)} ${cfg.label.padEnd(22)} overflow=${overflow.overflow} scrollH=${overflow.scrollH} clientH=${overflow.clientH}`);
  }
}

await browser.close();
await fs.writeFile(path.join(OUT, 'results.json'), JSON.stringify(results, null, 2));
console.log(`\nWrote ${results.length} samples to ${OUT}`);

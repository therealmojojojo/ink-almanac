import { chromium } from 'playwright';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FONTS = path.resolve(__dirname, '../../templates/fonts');
const OUT = path.join(__dirname, 'out');

const body = `Life is short, though I keep this from my children.
Life is short, and I've shortened mine
in a thousand delicious, ill-advised ways,
a thousand deliciously ill-advised ways
I'll keep from my children. The world is at least
fifty percent terrible, and that's a conservative
estimate, though I keep this from my children.
For every bird there is a stone thrown at a bird.
For every loved child, a child broken, bagged,
sunk in a lake. Life is short and the world
is at least half terrible, and for every kind
stranger, there is one who would break you,
though I keep this from my children. I am trying
to sell them the world. Any decent realtor,
walking you through a real shithole, chirps on
about good bones: This place could be beautiful,
right? You could make this place beautiful.`;

const cases = [
  { size: 25, showTitle: true, label: '25u_title' },
  { size: 25, showTitle: false, label: '25u_notitle' },
  { size: 28, showTitle: false, label: '28u_notitle' },
];

function escapeHtml(s) { return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }

function html(cfg) {
  const lines = body.split('\n').map((ln) => `<div class="line">${escapeHtml(ln)}</div>`).join('');
  const title = cfg.showTitle ? `<div class="gt-title">Good Bones</div>` : '';
  return `<!doctype html><html><head><style>
@font-face { font-family:'Fraunces'; src:url('file://${FONTS}/Fraunces[opsz,wght].woff2') format('woff2-variations'); font-weight:100 900; font-display:block; }
@font-face { font-family:'IBM Plex Mono'; src:url('file://${FONTS}/IBMPlexMono-Regular.woff2') format('woff2'); font-weight:400; font-display:block; }
:root{--u:1px;--ink:#000;--paper:#ececec;--font-serif:'Fraunces',serif;--font-mono:'IBM Plex Mono',monospace;}
*{box-sizing:border-box;margin:0;padding:0}
html,body{width:1200px;height:825px;background:var(--paper);color:var(--ink);font-weight:500;-webkit-font-smoothing:antialiased;text-rendering:geometricPrecision;overflow:hidden}
.gt-root{width:1200px;height:825px;padding:calc(72*var(--u)) calc(96*var(--u));display:grid;grid-template-rows:1fr auto;justify-items:center;align-items:center;position:relative}
.gt-content{display:flex;flex-direction:column;align-items:flex-start;gap:calc(28*var(--u));max-width:1008px}
.gt-title{font-family:var(--font-serif);font-variation-settings:'opsz' 144,'wght' 500;font-size:calc(56*var(--u));line-height:1.1}
.gt-body{font-family:var(--font-serif);font-variation-settings:'opsz' 36,'wght' 500;line-height:1.35;font-size:calc(${cfg.size}*var(--u))}
.gt-body .line{white-space:pre-wrap;padding-left:calc(40*var(--u));text-indent:calc(-40*var(--u))}
.gt-attrib{font-family:var(--font-mono);font-size:calc(25*var(--u));text-transform:uppercase;letter-spacing:0.14em}
.badge{position:absolute;top:18px;left:18px;font-family:var(--font-mono);font-size:18px;background:#fff;padding:4px 10px;border:1px solid #000}
</style></head><body>
<div class="gt-root">
  <div class="badge">${cfg.label}</div>
  <div class="gt-content">${title}<div class="gt-body">${lines}</div></div>
  <div class="gt-attrib">MAGGIE SMITH · 2016</div>
</div></body></html>`;
}

const browser = await chromium.launch({ args:['--font-render-hinting=none'] });
const ctx = await browser.newContext({ viewport:{width:1200,height:825}, deviceScaleFactor:1, colorScheme:'light' });
const page = await ctx.newPage();
for (const cfg of cases) {
  await page.setContent(html(cfg), { waitUntil: 'networkidle' });
  const info = await page.evaluate(() => {
    const content = document.querySelector('.gt-content').getBoundingClientRect();
    const attrib = document.querySelector('.gt-attrib').getBoundingClientRect();
    return { overflow: content.bottom > attrib.top - 4, contentBottom: content.bottom, attribTop: attrib.top };
  });
  await page.screenshot({ path: path.join(OUT, `goodbones_${cfg.label}.png`), clip: { x:0,y:0,width:1200,height:825 } });
  console.log(cfg.label, 'overflow=', info.overflow, 'contentBottom=', info.contentBottom.toFixed(0), 'attribTop=', info.attribTop.toFixed(0));
}
await browser.close();

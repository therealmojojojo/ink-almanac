import type { DitherMask } from '../image/dither.js';
import { attributionLine, batteryIndicator } from '../templateMacros.js';
import { fitGalleryText, fitGalleryTitle, fitShortFormTitle, titleOpsz, type Form } from '../typography.js';
import { applyZone } from '../zoneApply.js';
import type { ZoneId } from '../zones.js';
import { escapeHtml, htmlShell } from './shell.js';
import type { GalleryInput } from './schema.js';

const FORM_TO_ZONE: Record<Form, ZoneId> = {
  haiku: 'haiku_body',
  tanka: 'haiku_body',
  sonnet: 'poem_body',
  'free-verse': 'poem_body',
  stanzaic: 'poem_body',
  fragment: 'poem_body',
  aphorism: 'aphorism_body',
  'prose-poem': 'poem_body',
  quote: 'quote_body',
};

export function buildHtml(input: GalleryInput): string {
  const g = input.pairing.gallery;
  return g.flavor === 'visual' ? buildVisual(input) : buildText(input);
}

/** Title size bucket — same shape as Now-Playing's, tuned for the gallery-
 * split text column. Tightened thresholds since the Gallery title zone cap
 * is 20 chars (vs NP's 24). */
function galleryTitleBucket(title: string): 'l' | 'm' | 's' | 'xs' {
  const n = [...title].length;
  if (n <= 12) return 'l';
  if (n <= 18) return 'm';
  if (n <= 26) return 's';
  return 'xs';
}

function buildVisual(input: GalleryInput): string {
  const v = input.pairing.gallery.visual;
  const title = v?.display_title ?? v?.title ?? '';
  const attrib = v?.display_attribution
    ?? (v?.artist ? attributionLine(v.artist.toUpperCase(), v.year, undefined) : '');

  // Layout dispatch — landscape keeps the existing full-frame + caption band
  // design; anything where height >= width uses the NP-style split
  // (image left at natural width, title/author/clock in the right column).
  // Images without dimensions default to landscape/native behavior so the
  // pre-existing renders stay identical.
  const haveDims = v?.pixel_width && v?.pixel_height && v.pixel_width > 0 && v.pixel_height > 0;
  const isSplit = haveDims && (v!.pixel_height! >= v!.pixel_width!);

  if (isSplit) {
    return buildVisualSplit(input, title, attrib);
  }

  // --- Existing landscape path (orientation class system) ------------------
  // Orientation class derivation from pixel dimensions. Picks one of:
  //   gv-native (panel-aspect 1.35–1.70): full-bleed, cover
  //   gv-landscape-wide (> 1.70): letterbox with mat top/bottom
  //   gv-square (0.85–1.35 outside panel-native): matted pillarbox
  // When pixel dims are absent, fall back to panel-native (preserves prior behavior).
  let orientClass = 'gv-native';
  if (haveDims) {
    const ar = v!.pixel_width! / v!.pixel_height!;
    if (ar >= 1.35 && ar <= 1.70) orientClass = 'gv-native';
    else if (ar > 1.70) orientClass = 'gv-landscape-wide';
    else orientClass = 'gv-square'; // ar < 1.35 but height < width (edge near-square landscape)
  }

  const body = `
<div class="face gv-root ${orientClass}">
  ${batteryIndicator(input.device?.battery?.percentage)}
  <section class="gv-image">
    ${
      v?.image_path
        ? `<img src="${escapeHtml(v.image_path)}" alt="">`
        : '<div class="placeholder-dash"></div>'
    }
  </section>
  <footer class="gv-caption">
    <div class="title">${escapeHtml(applyZone('gallery_title', title))}</div>
    <div class="meta">
      <div class="attrib">${escapeHtml(applyZone('gallery_attrib', attrib))}</div>
    </div>
    <div class="clock">${escapeHtml(input.clock.time)}</div>
  </footer>
</div>`;
  return htmlShell({
    title: 'Gallery — visual',
    styles: ['/static/css/gallery-visual.css'],
    body,
  });
}

/** Split layout: image on the left at its natural aspect ratio (height
 * clamped to 825, width = 825 × w/h), title + attribution + clock in the
 * remaining right column. Triggered for pixel_height >= pixel_width. */
function buildVisualSplit(input: GalleryInput, title: string, attrib: string): string {
  const v = input.pairing.gallery.visual!;
  // Compute the image width for a 825 px height, capped to 825 so a
  // perfectly-square image doesn't exceed the panel's short dimension.
  const naturalWidth = Math.round((825 * v.pixel_width!) / v.pixel_height!);
  const imgWidth = Math.min(825, naturalWidth);
  const titleBucket = galleryTitleBucket(title);

  const body = `
<div class="face gv-root gv-split" style="--gv-img-width: ${imgWidth}px">
  ${batteryIndicator(input.device?.battery?.percentage)}
  <section class="gv-image">
    ${
      v.image_path
        ? `<img src="${escapeHtml(v.image_path)}" alt="">`
        : '<div class="placeholder-dash"></div>'
    }
  </section>
  <section class="gv-right">
    <div class="title" data-size="${titleBucket}">${escapeHtml(applyZone('gallery_title', title))}</div>
    <div class="attrib">${escapeHtml(applyZone('gallery_attrib', attrib))}</div>
  </section>
  <div class="gv-clock">${escapeHtml(input.clock.time)}</div>
</div>`;
  return htmlShell({
    title: 'Gallery — visual (split)',
    styles: ['/static/css/gallery-visual.css'],
    body,
  });
}

function buildText(input: GalleryInput): string {
  const t = input.pairing.gallery.text;
  if (!t) {
    return htmlShell({
      title: 'Gallery — text',
      styles: ['/static/css/gallery-text.css'],
      body: `<div class="face gt-root">${batteryIndicator(input.device?.battery?.percentage)}<div class="gt-body placeholder-dash"></div></div>`,
    });
  }
  const form = t.form;
  const zoneId = FORM_TO_ZONE[form];
  const verseBody = applyZone(zoneId, t.body); // verse-overflow → 422

  const toStanzaHtml = (text: string): string =>
    text
      .split(/\r?\n\s*\r?\n/)
      .filter((s) => s.trim().length > 0)
      .map((stanza) => {
        const lines = stanza
          .split(/\r?\n/)
          .map((ln) => `<div class="line">${escapeHtml(ln || '\u00a0')}</div>`)
          .join('');
        return `<div class="stanza">${lines}</div>`;
      })
      .join('');

  // Anthology mode: haiku/tanka render the Japanese original above the
  // translation when `body_ja` is staged. The original uses Noto Serif JP
  // at a slightly larger size; the translation sits below in italic.
  const hasAnthology =
    (form === 'haiku' || form === 'tanka') && !!t.body_ja && t.body_ja.trim().length > 0;
  const jaStanzas = hasAnthology ? toStanzaHtml(t.body_ja!.replace(/^(?:\r?\n)+|(?:\r?\n)+$/g, '')) : '';
  const stanzas = toStanzaHtml(verseBody);

  const showTitle = !!t.title;
  const attrib = attributionLine(t.poet.toUpperCase(), t.dates);

  const titleText = showTitle ? applyZone('gallery_text_title', t.title!) : '';
  const titleLen = titleText.length;

  const bodyLines = verseBody.split(/\r?\n/);
  const stanzaCount = verseBody.split(/\r?\n\s*\r?\n/).filter((s) => s.trim().length > 0).length || 1;
  const fit = fitGalleryText(bodyLines, form, titleLen, stanzaCount);
  // "Compact" = content short enough to read as a plaque (heroic title,
  // centered cluster) instead of a page (modest title, top-aligned).
  // Keyed on line count, not `form`: a 4-line quatrain (stanzaic) and a
  // 4-line aphorism deserve the same visual treatment, even though their
  // canonical forms differ. Threshold 5 catches haiku (3), tanka (5),
  // aphorism (2–4), quote (1–4), quatrain (4), and short fragments;
  // sonnets (14), most stanzaic poems, and prose-poems stay as pages.
  const totalBodyLines = bodyLines.filter((l) => l.trim().length > 0).length;
  const isCompact = totalBodyLines <= 5;
  const titleSize = isCompact
    ? fitShortFormTitle(titleLen, fit.fontSizeU)
    : fitGalleryTitle(titleLen, fit.fontSizeU, form);
  const titleOpszVal = titleOpsz(titleSize);

  const body = `
<div class="face gt-root" data-form="${escapeHtml(form)}"${isCompact ? ' data-compact="true"' : ''}${hasAnthology ? ' data-anthology="ja"' : ''} style="--gt-size: ${fit.fontSizeU};">
  ${batteryIndicator(input.device?.battery?.percentage)}
  <div class="gt-content">
    ${
      showTitle
        ? `<div class="gt-title" style="--gt-title-size: ${titleSize}; --gt-title-opsz: ${titleOpszVal};">${escapeHtml(titleText)}</div>`
        : ''
    }
    ${
      hasAnthology
        ? `<div class="gt-body-ja" lang="ja" style="--gt-size: ${fit.fontSizeU};">${jaStanzas}</div>`
        : ''
    }
    <div class="gt-body" lang="${escapeHtml(t.language)}" data-form="${escapeHtml(form)}" data-cols="${fit.cols}" style="--gt-cols: ${fit.cols}; --gt-size: ${fit.fontSizeU};">${stanzas}</div>
  </div>
  <div class="gt-attrib">${escapeHtml(applyZone('gallery_attrib', attrib))}</div>
  <div class="gt-corner-time">${escapeHtml(input.clock.time)}</div>
</div>`;

  return htmlShell({
    title: 'Gallery — text',
    styles: ['/static/css/gallery-text.css'],
    body,
  });
}

export function ditherMask(input: GalleryInput): boolean | DitherMask {
  const g = input.pairing.gallery;
  if (g.flavor !== 'visual') return false;

  const v = g.visual;
  // Split layout: mask only the left image column — text column should
  // stay crisp (Floyd–Steinberg dithering blurs small type).
  if (v?.pixel_width && v?.pixel_height && v.pixel_height >= v.pixel_width) {
    const W = 1200;
    const H = 825;
    const imgW = Math.min(825, Math.round((825 * v.pixel_width) / v.pixel_height));
    const data = new Uint8Array(W * H);
    for (let y = 0; y < H; y++) {
      for (let x = 0; x < imgW; x++) data[y * W + x] = 1;
    }
    return { width: W, height: H, data };
  }

  // Full-frame landscape: dither the whole face (unchanged behavior).
  return true;
}

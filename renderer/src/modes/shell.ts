import fs from 'node:fs';
import path from 'node:path';
import { TEMPLATES_DIR } from '../config.js';

export interface ShellOptions {
  title: string;
  styles: string[]; // extra CSS file paths served under /static
  body: string; // innerHTML for <body>
}

// Load the shared icon sheet once at module init and inline it into every
// shell. External <use href="/static/icons.svg#id"> doesn't resolve reliably
// through Playwright screenshots; an inline sheet is always addressable.
const ICONS_SVG = (() => {
  try {
    return fs.readFileSync(path.join(TEMPLATES_DIR, 'shared/icons.svg'), 'utf8');
  } catch {
    return '';
  }
})();

export function htmlShell({ title, styles, body }: ShellOptions): string {
  const links = ['/static/css/tokens.css', '/static/css/fonts.css', '/static/css/layout.css', ...styles]
    .map((href) => `<link rel="stylesheet" href="${href}">`)
    .join('\n');
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=1200, height=825, initial-scale=1">
<title>${escapeHtml(title)}</title>
${links}
</head>
<body>
${ICONS_SVG}
${body}
</body>
</html>`;
}

export function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

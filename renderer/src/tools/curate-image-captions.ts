/**
 * Auto-suggest display_title / display_attribution for image items whose
 * caption fields overflow the gallery caption geometry caps (20/32 chars).
 *
 * Strategy:
 *   - display_title: strip trailing parenthetical, strip ", from ..." / " — ...",
 *     drop any trailing "(1950s commercial illustration)"-style annotation,
 *     and hard-cap to 20 chars at a word boundary.
 *   - display_attribution: `LAST · YEAR` where LAST is the last surname token.
 *     If year is absent, just LAST.
 *
 * Usage:
 *   tsx src/tools/curate-image-captions.ts           # report suggestions
 *   tsx src/tools/curate-image-captions.ts --fix     # write into YAMLs
 */
import fs from 'node:fs/promises';
import path from 'node:path';

const CORPUS = path.resolve(process.cwd(), '../corpus');
const DIRS = ['images', 'nocturne', 'personal_library'];
const TITLE_CAP = 20;
const ATTRIB_CAP = 32;

function readField(raw: string, key: string): string | undefined {
  const m = raw.match(new RegExp(`^${key}:\\s*(.+?)\\s*$`, 'm'));
  if (!m) return undefined;
  return m[1].replace(/^["']|["']$/g, '');
}

function shortenTitle(t: string): string {
  let s = t.trim();
  // Drop trailing parenthetical (e.g. "(Original Name)" or "(1950s ...)")
  s = s.replace(/\s*\([^)]*\)\s*$/g, '').trim();
  // Drop ", from ..." / "from ..." suffix
  s = s.replace(/[,—–-]\s*(from|plate)\s+.*$/i, '').trim();
  // Drop "— subtitle" suffix
  s = s.replace(/\s*[—–]\s.+$/g, '').trim();
  // Drop trailing ", YYYY"
  s = s.replace(/,\s*\d{4}\s*$/, '').trim();
  if ([...s].length <= TITLE_CAP) return s;
  // Take before first comma
  const commaIdx = s.indexOf(', ');
  if (commaIdx > 0 && commaIdx <= TITLE_CAP) s = s.slice(0, commaIdx).trim();
  if ([...s].length <= TITLE_CAP) return s;
  // Word-boundary truncate with ellipsis
  const chars = [...s];
  const windowed = chars.slice(0, TITLE_CAP - 1).join('');
  const lastSpace = windowed.lastIndexOf(' ');
  const cut = lastSpace > TITLE_CAP * 0.5 ? windowed.slice(0, lastSpace) : windowed;
  return cut + '…';
}

function surnameOf(artist: string): string {
  // Strip parenthetical / Latin-alternate names
  let a = artist.replace(/\s*\([^)]*\)\s*/g, '').trim();
  // Skip honorifics / compound-particle names handled naturally by last-token
  // Take the last whitespace-separated token
  const tokens = a.split(/\s+/);
  return tokens[tokens.length - 1];
}

function composeAttribution(artist: string, year: string | undefined): string {
  const yr = year ? ` · ${year}` : '';
  const full = artist.toUpperCase() + yr;
  if ([...full].length <= ATTRIB_CAP) return full;
  return (surnameOf(artist).toUpperCase() + yr).slice(0, ATTRIB_CAP);
}

const FIX = process.argv.includes('--fix');
const suggestions: Array<{ filepath: string; rel: string; current: { title: string; artist?: string; year?: string }; suggest: { display_title?: string; display_attribution?: string } }> = [];
const seen = new Set<string>();
for (const dir of DIRS) {
  const dirPath = path.join(CORPUS, dir);
  const entries = await fs.readdir(dirPath).catch(() => []);
  for (const name of entries) {
    if (!name.endsWith('.yaml')) continue;
    const filepath = path.join(dirPath, name);
    if (seen.has(filepath)) continue;
    seen.add(filepath);
    const raw = await fs.readFile(filepath, 'utf8');
    const artist = readField(raw, 'artist');
    if (!artist) continue; // text item
    const title = readField(raw, 'title') ?? '';
    const year = readField(raw, 'year');
    const hasDisplayTitle = /^display_title:/m.test(raw);
    const hasDisplayAttrib = /^display_attribution:/m.test(raw);

    const suggest: { display_title?: string; display_attribution?: string } = {};
    const titleChars = [...title].length;
    const composedAttrib = composeAttribution(artist, year);
    const rawComposedAttrib = `${artist.toUpperCase()}${year ? ' · ' + year : ''}`;

    if (titleChars > TITLE_CAP && !hasDisplayTitle) {
      suggest.display_title = shortenTitle(title);
    }
    if ([...rawComposedAttrib].length > ATTRIB_CAP && !hasDisplayAttrib) {
      suggest.display_attribution = composedAttrib;
    }
    if (Object.keys(suggest).length === 0) continue;
    suggestions.push({ filepath, rel: `${dir}/${name}`, current: { title, artist, year }, suggest });
  }
}

console.log(`\n[curate-image-captions] ${suggestions.length} items need display fields\n`);
for (const s of suggestions) {
  console.log(`  ${s.rel}`);
  console.log(`    title:               ${s.current.title}`);
  if (s.suggest.display_title !== undefined)
    console.log(`    → display_title:      "${s.suggest.display_title}"  (${[...s.suggest.display_title].length} chars)`);
  if (s.suggest.display_attribution !== undefined)
    console.log(`    → display_attribution: "${s.suggest.display_attribution}"  (${[...s.suggest.display_attribution].length} chars)`);
  console.log('');
}

if (!FIX) {
  console.log('(Run with --fix to append display fields to the YAML files.)');
  process.exit(0);
}

let written = 0;
for (const s of suggestions) {
  const raw = await fs.readFile(s.filepath, 'utf8');
  // Insert after the `year:` line if present, else after `title:` line.
  const insertAfter = /^year:.*$/m.test(raw) ? /^year:.*$/m : /^title:.*$/m;
  const lines: string[] = [];
  if (s.suggest.display_title !== undefined)
    lines.push(`display_title: "${s.suggest.display_title.replace(/"/g, '\\"')}"`);
  if (s.suggest.display_attribution !== undefined)
    lines.push(`display_attribution: "${s.suggest.display_attribution.replace(/"/g, '\\"')}"`);
  const insertion = lines.join('\n');
  const updated = raw.replace(insertAfter, (m) => `${m}\n${insertion}`);
  await fs.writeFile(s.filepath, updated);
  written++;
}
console.log(`\n[curate-image-captions] wrote display fields into ${written} YAML files.`);

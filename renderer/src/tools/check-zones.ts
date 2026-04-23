/**
 * Build-time guard: `src/zones.ts` must match the authoritative table in
 * `openspec/specs/dashboard-faces/spec.md` (or, pre-archive, the same file
 * under `openspec/changes/add-dashboard-faces/specs/...`).
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import { ROOT } from '../config.js';
import { ZONES } from '../zones.js';

const CANDIDATE_SPEC_PATHS = [
  '../openspec/specs/dashboard-faces/spec.md',
  '../openspec/changes/add-dashboard-faces/specs/dashboard-faces/spec.md',
];

interface SpecRow {
  id: string;
  maxChars: number;
  maxLines: number;
  kind: 'prose' | 'verse';
}

function parseSpecTable(md: string): SpecRow[] {
  const rows: SpecRow[] = [];
  // Table row format: | zone_id | face | maxChars | maxLines | kind | notes |
  // We skip the header and the alignment row by requiring a digit in cols 3+4.
  const rowRe =
    /\|\s*([a-z_][a-z0-9_]*)\s*\|\s*[a-z-]+\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(prose|verse)\s*\|/gi;
  for (const m of md.matchAll(rowRe)) {
    rows.push({
      id: m[1]!,
      maxChars: Number(m[2]),
      maxLines: Number(m[3]),
      kind: m[4]! as 'prose' | 'verse',
    });
  }
  return rows;
}

async function resolveSpec(): Promise<string | undefined> {
  for (const rel of CANDIDATE_SPEC_PATHS) {
    const full = path.resolve(ROOT, rel);
    try {
      return await fs.readFile(full, 'utf8');
    } catch (err) {
      if ((err as NodeJS.ErrnoException).code !== 'ENOENT') throw err;
    }
  }
  return undefined;
}

async function main(): Promise<void> {
  const md = await resolveSpec();
  if (md === undefined) {
    console.error(
      '[check-zones] no dashboard-faces spec found at any of: ' +
        CANDIDATE_SPEC_PATHS.join(', '),
    );
    process.exit(1);
  }
  const spec = parseSpecTable(md);
  if (spec.length === 0) {
    console.error('[check-zones] parsed 0 rows from spec — the table format may have changed');
    process.exit(1);
  }
  const issues: string[] = [];
  for (const row of spec) {
    const local = (ZONES as Record<string, ZoneBudget>)[row.id];
    if (!local) {
      issues.push(`missing local zone "${row.id}" (present in spec)`);
      continue;
    }
    if (
      local.maxChars !== row.maxChars ||
      local.maxLines !== row.maxLines ||
      local.kind !== row.kind
    ) {
      issues.push(
        `"${row.id}" diverges: local=${local.maxChars}×${local.maxLines} ${local.kind}, spec=${row.maxChars}×${row.maxLines} ${row.kind}`,
      );
    }
  }
  for (const id of Object.keys(ZONES)) {
    if (!spec.find((r) => r.id === id)) {
      issues.push(`local zone "${id}" not in spec table`);
    }
  }
  if (issues.length) {
    console.error('[check-zones] divergence:\n  ' + issues.join('\n  '));
    process.exit(1);
  }
  console.log(`[check-zones] ${spec.length} zones aligned with spec`);
}

interface ZoneBudget {
  maxChars: number;
  maxLines: number;
  kind: 'prose' | 'verse';
}

if (import.meta.url === `file://${process.argv[1]}`) {
  void main();
}

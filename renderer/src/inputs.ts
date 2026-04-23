import fs from 'node:fs/promises';
import path from 'node:path';
import { inputsDir } from './config.js';

export class MissingInputError extends Error {
  readonly code = 'MISSING_INPUT' as const;
  readonly inputName: string;
  constructor(name: string) {
    super(`required input "${name}" is missing`);
    this.inputName = name;
  }
}

/**
 * Load a JSON input file from INPUTS_DIR. File name is `${name}.json`.
 * Returns undefined if absent (callers decide whether that's fatal).
 */
export async function loadInput<T>(name: string): Promise<T | undefined> {
  const p = path.join(inputsDir(), `${name}.json`);
  try {
    const raw = await fs.readFile(p, 'utf8');
    return JSON.parse(raw) as T;
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === 'ENOENT') return undefined;
    throw err;
  }
}

export async function requireInput<T>(name: string): Promise<T> {
  const v = await loadInput<T>(name);
  if (v === undefined) throw new MissingInputError(name);
  return v;
}

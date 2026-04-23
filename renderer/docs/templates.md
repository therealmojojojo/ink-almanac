# Templates

## Unit system

The panel is 1200×825 at `deviceScaleFactor: 1`. One CSS pixel = one panel
pixel. Templates use `var(--u)` (= `1px`) so every sizing expression can read
in `u` units without conversion. Examples:

```css
font-size: calc(54 * var(--u));   /* 54u */
padding: calc(40 * var(--u));
```

Sizes below **25u** fail the lint step (size floor), except for chrome
indicators explicitly allowlisted in `src/tools/lint-templates.ts:CHROME_SELECTORS`.

## Palette

Four variables, defined in `templates/shared/tokens.css`. No other colors may
appear in any template CSS. `rgb()`, `hsl()`, and hex literals other than the
four palette values fail the lint.

| Variable | Value | Use |
| -------- | ----- | --- |
| `--ink` | `#000` | Primary text |
| `--paper` | `#ececec` | Background |
| `--mid` | `#555` | Labels, secondary |
| `--faint` | `#a8a8a8` | Rules, separators |

## Families

Only three:

- `var(--font-serif)` → Fraunces variable
- `var(--font-mono)` → IBM Plex Mono
- `var(--font-sans)` → IBM Plex Sans

The lint fails on any other `font-family` declaration.

## Form dispatch (Gallery text-day)

`data-form="..."` on `.gallery-hero.text` selects the typography rule.
The JS module `src/typography.ts` is the authoritative table; CSS mirrors it.

- `haiku`, `tanka` → italic, opsz 72, 54u, centered
- `sonnet`, `free-verse`, `stanzaic` → regular, opsz 72, 42u, left
- `fragment` → italic, 48u, left
- `aphorism` → italic, 52u, centered
- `prose-poem` → regular, 36u, justified
- `quote` → regular, 44u, attribution italic

## Adding a mode

1. Pick a mode id (kebab-case) and add it to `MODES` in `src/config.ts`.
2. Create `src/modes/{mode}.ts` with `buildHtml(input)` and `ditherMask(input)`.
3. Add a Zod schema in `src/modes/schema.ts`.
4. Wire gathering in `src/modes/index.ts:prepareMode`.
5. Add `templates/{mode}/{mode}.css`.
6. Add a fixture set under `test/fixtures/` for snapshot testing.

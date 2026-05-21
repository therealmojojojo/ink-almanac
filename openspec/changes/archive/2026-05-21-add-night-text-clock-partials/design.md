# Design — Night text-clock partials + pool-only poetic line

## Architecture overview

```
┌────────────────────────────────────────────────────────────────────┐
│ Build time                                                         │
│                                                                    │
│  renderer/src/tools/bake-night-phrases.ts                          │
│    ├── reads Night face CSS (font-family, size, weight)            │
│    ├── reads phrase list (hardcoded in the tool, 25 entries)       │
│    ├── for each phrase: render via Playwright →                    │
│    │     threshold to 1-bit → tight-bounding-box crop              │
│    └── emit firmware/src/generated/night_phrases.{h,cpp}           │
│        with packed bitmap table + phraseForMinute() lookup         │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│ Runtime — every wake                                               │
│                                                                    │
│  Full path (60-min cadence in Night):                              │
│    ├── fetch /display/night.png → 3-bit raster (incl. time text +  │
│    │     poetic line + sky illustration)                           │
│    ├── 3-bit display.draw3bit                                      │
│    ├── fetch /display/night/clock-zone.json → (x, y, w, h)         │
│    ├── post-Full cleanup if min is in 25-phrase set:               │
│    │     pulse phrase rect black → blit phraseForMinute() → ...    │
│    └── publish state/device                                        │
│                                                                    │
│  Partial path (15-min cadence in Night):                           │
│    ├── doPartial → look up phraseForMinute(local_min_of_day)       │
│    │     null → return false → caller may promote to Full           │
│    │     non-null → blit bitmap at cached (x, y),                  │
│    │                partialUpdate1Bit, return true                  │
│    └── back to deep sleep (no MQTT, no fetch — fully offline)      │
└────────────────────────────────────────────────────────────────────┘
```

## The 25 phrases

Indexed by (hour, minute) in the night-window minutes-of-day. Stored
in the bake tool as a Map from `(h, m)` to phrase string; the bake
order matches the array order in the generated header so
`phraseForMinute` is a small switch / lookup.

| Min-of-day | Phrase                  | Min-of-day | Phrase                |
| ---------- | ----------------------- | ---------- | --------------------- |
| 22:15 = 1335 | quarter past ten      | 02:15 = 135  | quarter past two    |
| 22:30 = 1350 | half past ten         | 02:30 = 150  | half past two       |
| 22:45 = 1365 | quarter to eleven     | 02:45 = 165  | quarter to three    |
| 23:15 = 1395 | quarter past eleven   | 03:15 = 195  | quarter past three  |
| 23:30 = 1410 | half past eleven      | 03:30 = 210  | half past three     |
| 23:45 = 1425 | quarter to midnight   | 03:45 = 225  | quarter to four     |
| 00:15 = 15   | quarter past midnight | 04:15 = 255  | quarter past four   |
| 00:30 = 30   | half past midnight    | 04:30 = 270  | half past four      |
| 00:45 = 45   | quarter to one        | 04:45 = 285  | quarter to five     |
| 01:15 = 75   | quarter past one      | 05:15 = 315  | quarter past five   |
| 01:30 = 90   | half past one         | 05:30 = 330  | half past five      |
| 01:45 = 105  | quarter to two        | 05:45 = 345  | quarter to six      |
|              |                       | 06:15 = 375  | quarter past six    |

`phraseForMinute(min_of_day)` returns `nullptr` for any minute not in
this set. The lookup is implemented as a sorted array of `(min_of_day,
bitmap_index)` pairs with a 25-element binary search, or as a single
switch statement (compiler will optimise either way; switch is more
readable).

## Bake tool — `bake-night-phrases.ts`

Sketch:

```typescript
import { chromium } from 'playwright';

const PHRASES: Array<{ min: number; text: string }> = [
  { min:  15, text: 'quarter past midnight' },
  { min:  30, text: 'half past midnight' },
  { min:  45, text: 'quarter to one' },
  // … 25 total
];

const NIGHT_FONT_CSS = readNightFaceCss(); // font-family, size, weight, color

async function main() {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const bitmaps: Bitmap[] = [];
  for (const { min, text } of PHRASES) {
    await page.setContent(`
      <html><head><style>
        body { margin: 0; background: white; }
        .phrase { ${NIGHT_FONT_CSS} color: black; padding: 8px; }
      </style></head><body>
      <span class="phrase">${escapeHtml(text)}</span>
      </body></html>
    `);
    const handle = await page.locator('.phrase');
    const png = await handle.screenshot({ type: 'png' });
    bitmaps.push(thresholdTo1Bit(png));  // returns { width, height, data: Uint8Array }
  }
  emitHeader(bitmaps, PHRASES);
  emitSource(bitmaps, PHRASES);
}
```

Output:

```cpp
// firmware/src/generated/night_phrases.h
#pragma once
#include <cstdint>
#include <cstddef>

namespace fw::night_phrases {

struct Bitmap {
  uint16_t width;
  uint16_t height;
  const uint8_t* data;  // 1-bit, MSB-first, row-major, padded to byte boundary
};

const Bitmap* phraseForMinute(int min_of_day);

}  // namespace fw::night_phrases
```

```cpp
// firmware/src/generated/night_phrases.cpp — auto-generated, do not edit
#include "generated/night_phrases.h"

namespace fw::night_phrases {

static constexpr uint8_t kPhrase00_15[] = { 0x00, 0xFF, ... };  // ~6 KB each
static constexpr uint8_t kPhrase00_30[] = { ... };
// … 25 entries

static constexpr Bitmap kBitmaps[25] = {
  { 600, 80, kPhrase00_15 },
  { 600, 80, kPhrase00_30 },
  // … 25 entries
};

const Bitmap* phraseForMinute(int min_of_day) {
  switch (min_of_day) {
    case   15: return &kBitmaps[ 0];   // quarter past midnight
    case   30: return &kBitmaps[ 1];   // half past midnight
    case   45: return &kBitmaps[ 2];   // quarter to one
    case   75: return &kBitmaps[ 3];   // quarter past one
    // … 25 cases
    default:   return nullptr;
  }
}

}  // namespace fw::night_phrases
```

The bitmap data lives in `.rodata` (constexpr), so it's flash, not
RAM. Total size ≈ 25 × (600 × 80 / 8) = **150 KB** of `.rodata`.

CMake / build wiring: the build script invokes `bake-night-phrases.ts`
when (a) `night_phrases.cpp` is missing or older than (b) any of:
the bake tool itself, the Night face's CSS, the phrase list. PlatformIO
build runs `npm run bake-night-phrases` as a pre-build step; CMake
host build mirrors via `add_custom_command`.

## Renderer changes

### Night clock-zone JSON

`renderer/src/server.ts` (or wherever the per-mode `clock-zone.json`
endpoints live) gets a Night case:

```typescript
app.get('/display/night/clock-zone.json', (req, res) => {
  res.json({
    x: NIGHT_PHRASE_X,           // matches the Night CSS layout
    y: NIGHT_PHRASE_Y,
    w: NIGHT_PHRASE_W,
    h: NIGHT_PHRASE_H,
    font_size: NIGHT_PHRASE_FONT_SIZE,  // decorative; firmware uses bitmap dims
  });
});
```

The values come from the Night face's CSS (e.g., the `.np-phrase` or
similar element's bounding box). Today they're undefined; this change
makes them concrete.

### Night PNG continues to render the time text

No change to `renderer/src/faces/night.ts` regarding the time text.
The 3-bit Full raster keeps painting it. The firmware over-paints
with the 1-bit phrase bitmap on partial wakes only; on Full wakes,
the post-cleanup logic skips the over-paint at top-of-hour Fulls
(those minutes aren't in the 25-phrase set; the PNG's own rendering
is the authoritative content).

## Firmware changes

### `presetByFontSize` extension

Today `presetByFontSize` returns one of three baked digit-glyph
presets (`kSummaryClock`, `kCompactClock`, `kCornerClock`). Night's
new "phrase" mode is fundamentally different — it doesn't compose
from glyph atoms; it blits a whole bitmap.

Rather than abuse `Preset` to represent both styles, introduce a
sibling lookup: `nightPhraseRender(panel, mode, x, y, hh, mm)`.
`doPartial` and `doFull` post-cleanup branch on `mode == Night`:

```cpp
if (active == fw::modes::Mode::Night) {
  const auto* bm = fw::night_phrases::phraseForMinute(local_min_of_day);
  if (bm) {
    // blit + partialUpdate1Bit
  }
} else {
  // existing digit-glyph composition
}
```

### `doFull` post-Full cleanup, Night branch

Today the post-Full cleanup pulses the clock zone solid black, then
white-with-digits, neutralising 3-bit anti-aliasing for subsequent
1-bit partials. For Night, do the same with the phrase bitmap as the
"new" content:

```cpp
if (active == fw::modes::Mode::Night) {
  const auto* bm = fw::night_phrases::phraseForMinute(local_min_of_day);
  if (bm) {
    h.display.fillRect1Bit(zx, zy, zw, zh, /*black=*/1);
    h.display.partialUpdate1Bit();
    blitBitmap1Bit(h.display, *bm, zx, zy);
    h.display.partialUpdate1Bit();
    fw::wake::persisted().last_drawn_hh = static_cast<uint8_t>(local_h);
    fw::wake::persisted().last_drawn_mm = static_cast<uint8_t>(local_m);
  }
}
```

For top-of-hour Fulls (no phrase in the 25-entry table), the
post-cleanup is a no-op — the 3-bit raster's time-text stands alone
until the first :15 partial.

### `doPartial`, Night branch

```cpp
if (current_mode == fw::modes::Mode::Night) {
  const auto* bm = fw::night_phrases::phraseForMinute(local_min_of_day);
  if (!bm) {
    FW_LOG("partial: no phrase for night min=%d", local_min_of_day);
    return false;
  }
  h.display.setDisplayMode(hal::IDisplay::DisplayMode::OneBit);
  // Seed: re-blit the previously-drawn phrase to seed DMemoryNew.
  if (last_drawn_phrase_min != 0xff) {
    const auto* prev = fw::night_phrases::phraseForMinute(last_drawn_phrase_min);
    if (prev) {
      blitBitmap1Bit(h.display, *prev, zx, zy);
      h.display.partialUpdate1Bit();
    }
  }
  // Draw new.
  blitBitmap1Bit(h.display, *bm, zx, zy);
  const uint32_t cycles = h.display.partialUpdate1Bit();
  h.display.setDisplayMode(hal::IDisplay::DisplayMode::ThreeBit);
  // Track which phrase was last drawn so the next partial's seed step
  // uses the right "previous" image.
  fw::wake::persisted().last_drawn_phrase_min = static_cast<uint16_t>(local_min_of_day);
  return true;
}
```

The seed-then-draw pattern matches the existing digit-clock partial
path, just with phrase bitmaps instead of digit composition. The
seed uses the previously-drawn phrase (tracked in `Persisted` as
`last_drawn_phrase_min`, a new `uint16_t`).

### `Persisted` field

```cpp
struct Persisted {
  // … existing …
  uint16_t last_drawn_phrase_min = 0xffff;  // sentinel: nothing drawn yet
};
```

## HA pool-only poetic line — sub-design

Direct lift from `replace-poetic-llm-with-pool/design.md` (with the
file moved into this change). Summary:

### Pool file

`ha/config/night_poetic_pool.yaml`. 5 lines per bucket, 13 buckets,
65 lines total. English ASCII subset only:
`[A-Za-z0-9 ,.:;!\-'"]+`. ≤ 40 graphemes per line. House voice:
plain, observational, slightly melancholy.

### Picker script

`ha/scripts/generate_poetic_weather_line.sh` becomes ~40 LOC:

```bash
#!/usr/bin/env bash
set -euo pipefail
BUCKET="${1:-cloudy}"
POOL_FILE="/config/custom/inkplate/config/night_poetic_pool.yaml"
STATE_FILE="/config/custom/inkplate/state/poetic_weather.txt"

LINE=$(POOL="$POOL_FILE" BUCKET="$BUCKET" python3 - <<'PY'
import os, random, re, yaml
pool = yaml.safe_load(open(os.environ["POOL"])) or {}
candidates = pool.get(os.environ["BUCKET"]) or pool.get("cloudy") or ["Quiet night."]
random.shuffle(candidates)
for line in candidates:
    if len(line) > 40: continue
    if not re.fullmatch(r"[A-Za-z0-9 ,.:;!\-'\"]+", line): continue
    print(line); break
else:
    print("Quiet night.")
PY
)
mkdir -p "$(dirname "$STATE_FILE")"
printf '%s' "$LINE" > "$STATE_FILE"
```

### Bucket sensor + automation

New template sensor `sensor.inkplate_night_poetic_bucket` whose state
is the bucket key (lifted from the existing automation's variable
block). Automation `ha/automations/poetic_weather.yaml` is rewritten
to fire on `state_changed` of that sensor + `homeassistant.start`.

### Cleanup

- Delete `ha/config/poetic_weather_line.yaml` (provider config no
  longer read).
- Keep `ha/secrets.yaml`'s `anthropic_api_key` (still used by
  `generate_astro_event.py`).

## Out of scope

- Phrase localisation (English-only, hardcoded).
- Operator runtime override of phrases.
- Removing the time text from the Night PNG (kept as 3-bit fallback).
- `00:00` / `06:30` / other non-partial Night minutes — no phrase, the
  Full's PNG is the only content.

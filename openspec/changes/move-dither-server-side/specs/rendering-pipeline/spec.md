## MODIFIED Requirements

### Requirement: Rendering engine

Rendering SHALL use Playwright with Chromium at a fixed viewport of 1200×825, `deviceScaleFactor: 1`. Template URLs SHALL be resolved locally (no external network for the HTML itself); external font loading via `@font-face` is permitted and SHALL be cached at startup.

The Chromium screenshot SHALL be converted to greyscale, palette-quantized against the 8-level Inkplate palette, and returned as the response body for `/display/{mode}.png`. No server-side supersample, Lanczos resample, or contrast manipulation is performed.

#### Scenario: Network disabled for template loading

- **WHEN** the renderer loads a mode's template
- **THEN** the URL is `file://` or `http://localhost`, never a remote origin (other than cached font CDN at startup)

#### Scenario: Raw PNG dimensions

- **WHEN** a mode is rendered via `/display/{mode}.png`
- **THEN** the returned PNG is exactly 1200×825, single-channel 8-bit greyscale, and was produced from a single Chromium screenshot — not via an intermediate upscale/downsample pass

#### Scenario: No tonal manipulation

- **WHEN** a mode PNG is produced
- **THEN** no linearization, contrast scaling, or endpoint crush has been applied between screenshot and palette quantization — the only transformations are greyscale conversion and palette mapping

### Requirement: Image-preparation chain

Between Chromium screenshot and returned PNG, the renderer SHALL perform exactly two transformations:

1. Greyscale conversion to a true single-channel image via `sharp.toColourspace('b-w')`. `sharp.greyscale()` alone desaturates but leaves three identical channels; the output SHALL be one channel.
2. Palette mapping onto `[0, 36, 73, 109, 146, 182, 219, 255]` — Floyd–Steinberg error diffusion within the mode's dither mask, nearest-palette quantization outside it.

The renderer SHALL NOT apply linearization, contrast adjustment, endpoint crush, or gamma round-trips. The orphaned `prep.ts` chain SHALL NOT be reinstated.

#### Scenario: Reproducibility

- **WHEN** the renderer is invoked twice with identical inputs
- **THEN** the two output PNGs are byte-for-byte identical

#### Scenario: Single-channel output

- **WHEN** a mode PNG's metadata is inspected
- **THEN** `channels` is 1, not 3

#### Scenario: Palette-constrained output

- **WHEN** a mode PNG is inspected pixel-by-pixel
- **THEN** every pixel value is a member of `[0, 36, 73, 109, 146, 182, 219, 255]`, and `assertPaletteOnly()` passes

### Requirement: Selective dithering

Floyd–Steinberg error diffusion SHALL be applied server-side, scoped by the mode's dither mask. Each mode SHALL export a `ditherMask()` returning either `false` (no dithered region) or a `DitherMask` covering that face's photographic zones.

Within the mask, pixels SHALL be dithered by palette-aware Floyd–Steinberg error diffusion. Outside the mask, pixels SHALL be hard-quantized to the nearest palette value with no error propagation, so text and rule edges carry no palette-noise halo.

The device SHALL NOT dither. The firmware draw path passes `dither=false`, and the panel's level selector `RGB3BIT(v,v,v) = floor(v/32)` maps the palette 1:1 onto levels 0–7. Exactly one error-diffusion pass SHALL exist in the pipeline, and it SHALL be the renderer's.

Rationale: the Inkplate library's monochrome `ditherGetPixelBmp` diffuses quantization error against `oldPixel & 0xE0` ∈ {0…224} while the panel emits {0…255} — a 1.1384 gain mismatch absent from the error term, compounded by truncating quantization, per-term `>>4` shifts that discard errors below 16, and an unsigned error accumulator. Measured against a real face: RMSE 19.97 and +19.05/255 brightness bias, versus 2.67 and −0.02 for the renderer's implementation.

#### Scenario: Exactly one dither pass

- **WHEN** a mode PNG is returned by the renderer and drawn by the device
- **THEN** the renderer contributed exactly one Floyd–Steinberg pass, the device contributed zero, and glyph edges on the panel are visually crisp

#### Scenario: Text zones are not dithered

- **WHEN** a Gallery split-layout face is rendered and the text column is inspected
- **THEN** pixels outside the dither mask take only nearest-palette values with no error diffusion — a flat paper field carries a single palette value, not a mixture

#### Scenario: Photo zones are dithered

- **WHEN** a Gallery visual-day face is rendered and the image region is inspected
- **THEN** the region contains a mixture of palette values forming an error-diffusion pattern, and its blurred mean tracks the pre-quantization greyscale mean to within 3/255

#### Scenario: Mode without photographic content

- **WHEN** a Weather face is rendered and its `ditherMask()` returns `false`
- **THEN** the entire face is hard-quantized to nearest palette value and no error diffusion is performed

### Requirement: Output specifications

Every rendered PNG SHALL conform to the following:

- Exact dimensions 1200×825 pixels
- 8-bit greyscale, single channel
- Pixel values restricted to the palette `[0, 36, 73, 109, 146, 182, 219, 255]`
- No alpha channel
- sRGB colorspace, or none

#### Scenario: Out-of-palette value

- **WHEN** a rendered PNG is inspected and contains any pixel with a value not in the Inkplate palette
- **THEN** the rendering pipeline's self-test reports a failure for that mode

#### Scenario: Channel count

- **WHEN** a rendered PNG is inspected
- **THEN** it has exactly one colour channel and no alpha channel

## ADDED Requirements

### Requirement: Dither-placement switch

The renderer SHALL honour a `RENDERER_DITHER` environment variable selecting where dithering happens:

- `server` — the renderer applies masked Floyd–Steinberg and emits palette-constrained output.
- `device` — the renderer emits full-range 8-bit greyscale and ignores the mode's dither mask, matching the pre-change behavior for firmware that still passes `dither=true`.

The value SHALL default to `device` until hardware validation confirms the server-side path, after which the default SHALL become `server`. The switch exists so that rollback does not require reflashing the device; it SHALL be removed once the change is settled.

#### Scenario: Server mode

- **WHEN** the renderer runs with `RENDERER_DITHER=server` and a mode is fetched
- **THEN** the returned PNG's pixel values are all members of the Inkplate palette

#### Scenario: Device mode

- **WHEN** the renderer runs with `RENDERER_DITHER=device` and a mode is fetched
- **THEN** the returned PNG's pixel values span the full 0–255 range and are not palette-constrained

#### Scenario: Unset

- **WHEN** `RENDERER_DITHER` is not set
- **THEN** the renderer behaves as if set to `device` and logs the effective mode once at startup

### Requirement: Dither mask geometry is verified against rendered layout

Each mode's `ditherMask()` rectangles SHALL be verified against the actual rendered geometry of that face rather than assumed from the constants in source. The masks were authored while the code path was inactive and their coordinates predate later layout edits.

A mask SHALL cover the photographic region fully and SHALL NOT extend into text or rule zones.

#### Scenario: Mask matches the image column

- **WHEN** a Gallery split-layout face is rendered for an image of known dimensions
- **THEN** the dither mask's right edge coincides with the image column's right edge as laid out by CSS, within 2 px

#### Scenario: Mask does not cover the caption band

- **WHEN** a Gallery visual-day landscape face is rendered
- **THEN** no pixel in the caption band is inside the dither mask

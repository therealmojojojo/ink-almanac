## MODIFIED Requirements

### Requirement: Rendering engine

Rendering SHALL use Playwright with Chromium at a fixed viewport of 1200×825, `deviceScaleFactor: 1`. Template URLs SHALL be resolved locally (no external network for the HTML itself); external font loading via `@font-face` is permitted and SHALL be cached at startup.

The Chromium screenshot SHALL be converted to a single-channel 8-bit greyscale PNG via `sharp.greyscale()` and returned as the response body for `/display/{mode}.png`. No server-side supersample, Lanczos resample, contrast manipulation, or palette quantization is performed in the default path.

#### Scenario: Network disabled for template loading

- **WHEN** the renderer loads a mode's template
- **THEN** the URL is `file://` or `http://localhost`, never a remote origin (other than cached font CDN at startup)

#### Scenario: Raw PNG dimensions

- **WHEN** a mode is rendered via `/display/{mode}.png`
- **THEN** the returned PNG is exactly 1200×825, 8-bit greyscale, and was produced from a single Chromium screenshot — not via an intermediate upscale/downsample pass

### Requirement: Image-preparation chain

Between Chromium screenshot and returned PNG, the renderer SHALL perform exactly one transformation: greyscale conversion via `sharp.greyscale()`. Output SHALL be an 8-bit greyscale PNG.

The renderer SHALL NOT apply linearization, contrast adjustment, endpoint crush, Floyd-Steinberg error diffusion, or palette quantization in the default path. The device's Inkplate library performs its own Floyd-Steinberg dither onto the 8-shade panel palette during `drawImage()` decode; any server-side palette manipulation compounds with the library's dither and produces visible smudge on the physical panel.

#### Scenario: Reproducibility

- **WHEN** the renderer is invoked twice with identical inputs
- **THEN** the two output PNGs are byte-for-byte identical

#### Scenario: Greyscale output, not palette-quantized

- **WHEN** a mode PNG is inspected pixel-by-pixel
- **THEN** pixel values span the full 0–255 greyscale range (the library will quantize them on device), and are NOT constrained to the 8-shade Inkplate palette at this stage

### Requirement: Selective dithering

Server-side Floyd-Steinberg dithering SHALL NOT be applied in the default path. The device's Inkplate library performs Floyd-Steinberg error diffusion onto the 8-shade panel palette during image decode when `drawImage(url, x, y, invert=false, dither=true)` is called; this is the single dither pass the pipeline relies on.

A future change MAY reintroduce server-side palette mapping for specific modes that embed large photos (Gallery, Night) whose unquantized greyscale PNGs overflow the device's pngle decoder memory budget. That change will scope the server-side step to photo zones only, will set `dither=false` in firmware for those modes so the server output is not re-dithered, and will document the added processing as an explicit exception to this default.

#### Scenario: No double-dithering

- **WHEN** a mode PNG is returned by the renderer and drawn by the device with `dither=true`
- **THEN** the device has performed exactly one Floyd-Steinberg pass on the pixel data — the renderer contributed zero dither passes — and glyph edges on the panel are visually crisp (no palette-noise halo around hard edges)

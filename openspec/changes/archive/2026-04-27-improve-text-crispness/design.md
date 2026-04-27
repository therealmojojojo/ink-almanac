## Context

The `add-rendering-pipeline` change committed to a specific 7-step image-preparation chain between Chromium and the final PNG: greyscale → linearize → contrast → crush → Floyd-Steinberg (pictorial zones) or hard-quantize (UI zones) → quantize → PNG. The design goal was control: produce a PNG whose every pixel is already a palette value, so nothing downstream could add noise.

That design didn't survive contact with the hardware.

## The recorded dead end

The first iteration of this change hypothesized that text smudge came from insufficient greyscale anti-aliasing at 1× — only 1 pixel of AA per glyph edge, which the 8-shade palette can't represent faithfully. Fix proposed: render at `deviceScaleFactor: 2`, Lanczos3-downsample to 1200×825, and loosen the contrast crush from 0.05/0.95 to 0.10/0.90 to keep AA edge greys alive through quantization.

This passed in-browser A/B inspection (glyph edges visibly carried palette greys in the saved PNGs) and looked better in goldens. Tested on the physical Inkplate 10: **no visible difference.** The user's description — "no crispness at all, glyphs are smudged" — persisted. The entire reasoning that drove the first iteration was valid in-browser and irrelevant on the panel.

Recording this in the design doc (not erasing it) because future pipeline decisions will want to know: optimizing PNGs in the browser for e-paper can be misleading. Hardware is the only arbiter.

## The actual fix

The smudge has a different cause. Our pipeline output a PNG whose every pixel was already one of the 8 Inkplate palette values. The Soldered Inkplate library, given any PNG, runs its own Floyd-Steinberg error-diffusion dither during decode (via `drawImage(url, x, y, invert=false, dither=true)`). Passing an already-quantized input through a dither pass that assumes unquantized input does not no-op — it produces error terms based on the quantization gaps and spreads them across neighboring pixels, which looks like noise/smudge around every hard edge, especially glyph edges.

Proof: switching the device's cycling firmware to display MagInkDash's native 1200×825 greyscale PNG (their renderer outputs plain `Chromium screenshot → PNG`, no palette steps) produced visibly crisp text on the same panel. Same library, same dither call, same dither=true setting — different input → different output.

The fix therefore is to match MagInkDash's pipeline: render at 1×, convert to 8-bit greyscale, emit the PNG. Let the library do the palette mapping exactly once, as it was designed to.

## Goals / Non-Goals

**Goals:**
- Match the pipeline of the only native-Inkplate-10 reference known to produce crisp text on this hardware.
- Keep the renderer's public contract intact: `/display/{mode}.png` still returns a valid 1200×825 PNG; the firmware needs no changes.

**Non-Goals:**
- Pursuing further AA tricks in the renderer. None of them survive the device's dither pass. If we want more control, the path is a per-zone server-side quantize BEFORE the PNG leaves the server, combined with `dither=false` in firmware — but that's photo-mode territory, not a default.
- Fridge-distance readability. Text is now crisp; it's still small. That's a layout/typography problem, not a pipeline problem, and belongs in a separate change against `dashboard-faces`.

## Decisions

**1. Delete the Lanczos + prep pipeline from the default path, don't feature-flag it.**
Options considered: (a) keep both paths behind an env flag `RENDERER_LEGACY_PIPELINE=1`; (b) delete. Chose (b). The legacy path is validated-worse on the only hardware that matters, and keeping dead paths behind flags rots fast. `prep.ts` stays in the tree because photo-mode quantization will want to reuse parts of it.

**2. Emit 8-bit greyscale PNG, not 8-bit RGB.**
Sharp's `.greyscale()` + `.png()` by default emits a 3-channel RGB PNG where R=G=B. Same bytes of data, triple the payload. `.toColorspace('b-w')` would force single-channel but risks a compatibility issue with the ESP32 pngle decoder. Kept 3-channel for now; revisit if bandwidth matters.

**3. Gallery mode's 914 KB greyscale overflow is a known breakage, not a regression.**
The prior pipeline hid this by palette-quantizing the photo down to a ~130 KB PNG. The new pipeline exposes that our approach to photos needs its own thought: either server-side palette-aware Floyd-Steinberg on photo zones (the old pipeline's pictorial-zone path), or pre-shrinking images to lower effective resolution. Scheduling as a follow-up — the tracked failure on one of five modes is an acceptable cost of pulling the other four into a correct state.

**4. Don't change the firmware's `dither` argument.**
`display.drawImage(url, 0, 0, invert=false, dither=true)` stays. The Inkplate library's behavior with `dither=true` on a full-greyscale input is exactly what we want (one clean pass of Floyd-Steinberg onto the 8-shade palette). `dither=false` is saved for the photo-mode path once that lands.

## Risks / Trade-offs

- **[Risk] Photo-mode regression.** Gallery mode is currently broken. Night mode also displays a photo (the nocturne image) but the PNG size came out under the library's threshold (~430 KB) and it decoded successfully. If Night ever gets a higher-resolution source image it will hit the same ceiling. Mitigation: follow-up change for targeted photo quantization.
- **[Trade-off] Larger PNGs over WiFi.** Weather went from ~24 KB to ~64 KB, Summary 25→65 KB. On-device fetch + draw still completes in ~9 s per frame, well under the wake-budget. No action.
- **[Lesson, non-actionable] In-browser PNG previews lie.** The first iteration looked better in A/B pixel-peeping; the second looked about the same. The hardware result was the reverse. Future renderer changes that claim visual improvements must be validated on-device before being committed as the default.

## Migration Plan

No migration — the public contract (`/display/{mode}.png`) is unchanged; only the bytes differ. Snapshot goldens get re-seeded once; the palette-invariant test is removed (no zone currently guarantees palette-only output). If a photo-mode quantize step later needs it back, it's reintroduced with an explicit scope (photos only, not text zones).

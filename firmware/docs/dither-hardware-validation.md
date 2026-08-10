# Dither A/B — hardware validation, 2026-08-10

Hardware gate for `openspec/changes/move-dither-server-side`. The case for the
change was a faithful port of the Inkplate library's `ditherGetPixelBmp`, not a
photograph, so it did not ship until the panel agreed.

## Method

`firmware/src/dither_ab.cpp` (env `dither_ab`), flashed to the Inkplate 10 over
`/dev/cu.usbserial-220`. It alternates the **same** rendered Gallery face every
20 s, tagged `A`/`B` in the top-left corner so photographs are self-identifying:

| | PNG | `drawImage` dither | meaning |
|---|---|---|---|
| A | full-range greyscale, 550 KB | `true` | what the panel did before this change |
| B | palette-constrained, 137 KB | `false` | the proposed path |

Both served as static files from the renderer host on port 8888, so the probe
needs no renderer, HA, or MQTT. No production firmware was installed until the
result was in.

## Result

**Confirmed.** The operator's verdict on first look: *"the difference is
obvious and clearly B is better."*

Draw timing over 5 consecutive cycles, from the serial log:

| | draws | mean draw time |
|---|---|---|
| A — device dither | 2 | 9146 ms |
| B — server dither | 3 | 6455 ms |

B is **2.7 s faster per draw (-29%)** on top of looking better — the payload is
4× smaller, so less radio time and less time awake. That was not a predicted
benefit; the change was argued on image quality alone.

One `B DRAW FAILED` was logged in the first cycle after boot, alongside
`WiFiClient setSocketOption` errors, and did not recur across any later cycle.
Reads as a WiFi race at association, not a decode failure. Worth watching
during rollout rather than treating as resolved.

### Related: this also addresses a known pngle limit

`smoketest.cpp` excludes the Gallery face outright, with the note that its
full-greyscale PNG "inflates to ~900 KB, which pngle on the ESP32 can't decode
cleanly," and names server-side palette quantization as the fix. That is this
change, arrived at independently. Gallery is the face most at risk under the
old path; server mode brings it to 137 KB.

## Finding: `--paper` had to move to `#ffffff`

The first B frames showed the whole non-photo background a step darker than A,
with a visible seam at the image border — the paper reading darker than the
photo's own light edges.

Cause, and it is not a dithering fault:

```
--paper #ececec = 236
  old device path : 236 & 0xE0 = 224 -> level 7 -> panel emits 255
  honest quantize : nearest palette  -> 219      -> level 6
```

The panel had **always** shown that paper as pure white. `#ececec` never
rendered as 236; the library's truncation pushed it a full level up. Correct
quantization dropped it to 219, and photo highlights — which dither around
their true value — then sat *lighter* than the surrounding paper, which is what
produced the seam.

`--paper: #fff` lands exactly on level 7, so the paper matches what was on the
panel before and the seam is gone. Operator confirmed: *"much better."*

This is not a design change. It makes the token say what the hardware was
already doing. An audit of every greyscale token found `--paper` to be the only
one whose panel output moves under the new path:

| token | value | was | now |
|---|---|---|---|
| `--ink` | `#000` | 0 | 0 |
| `--mid` | `#000` | 0 | 0 |
| `--faint` | `#000` | 0 | 0 |
| `--rule-faint` | `#909090` | 146 | 146 |
| `--paper` | `#ececec` → `#fff` | 255 | 255 |

**Rule this establishes:** greyscale tokens should sit exactly on palette
entries (`0, 36, 73, 109, 146, 182, 219, 255`). A token that lands between them
either shifts a level or produces a seam against dithered content. Pinned by a
test in `renderer/test/dither.test.ts`.

## Panel level calibration — the eight levels are NOT evenly spaced

Follow-on measurement, same day, using the `DITHER_AB_WEDGE` build: a step
wedge of all eight levels drawn with `dither=false` after three black/white
flush cycles.

The target is built so a photograph can be trusted. Each level appears twice at
mirrored positions (row 1 runs 0→7, row 2 runs 7→0), so averaging a level's two
patches cancels any left–right lighting gradient — which mattered, the first
shot had a 30/255 gradient across the panel. Four registration marks give a
homography, so angle and rotation don't need controlling.

Two photographs, deliberately different in rotation, lighting, surface and
angle, so they are replicates rather than a repeat:

| level | nominal | shot A | shot B | mean | error |
|---|---|---|---|---|---|
| 0 | 0 | 0 | 0 | 0 | — |
| 1 | 36 | 28.7 | 29.0 | 28.9 | −7.1 |
| 2 | 73 | 61.0 | 68.5 | 64.8 | −8.2 |
| 3 | 109 | 91.4 | 102.7 | 97.1 | −11.9 |
| 4 | 146 | 104.3 | 115.5 | 109.9 | **−36.1** |
| 5 | 182 | 136.4 | 147.8 | 142.1 | **−39.9** |
| 6 | 219 | 201.2 | 207.5 | 204.3 | −14.7 |
| 7 | 255 | 255 | 255 | 255 | — |

Mean disagreement between the two shots: **6.0/255**. Registration correlation
0.963 and 0.981.

Two findings:

1. **Levels 3 and 4 nearly coincide.** The step measures 12.9 in shot A and
   12.8 in shot B, against 32–37 for every other step. Independently identical
   to one decimal. A third, earlier photograph found the same collapse. The
   panel effectively offers ~7 distinguishable levels, not 8.
2. **Midtones run dark.** Every interior level is darker than the palette
   assumed, levels 4 and 5 by 36 and 40.

### Why this needed two arrays, not one

The obvious fix — drop the measured values into `INKPLATE_PALETTE` — does not
work. The device selects a level with `floor(v/32)`, so a value must lie in its
own 32-wide bucket, and three of the eight measured values do not (28.9, 109.9,
142.1). Emitting them would select the wrong level.

So the single array was doing two incompatible jobs, and is now split:

- `INKPLATE_PALETTE` — the byte written to the PNG. A *selector*. Its only
  constraint is `floor(v/32) == level`.
- `PANEL_APPEARANCE` — what the level *looks like*. Quantization and error
  diffusion work here.

### This was implemented, then REVERTED the same day

Quantizing against the measured values was shipped and the operator rejected it
immediately: *"this last change removed the details from the Goya drawing — it
is back to where it was when we started."*

The cause is the gaps. The measured curve puts **62** between levels 5 and 6 and
51 between 6 and 7, where nominal has a uniform 36. Error diffusion across a
62-wide gap is far coarser, and the Goya's hatching lives in exactly that light
midtone band, so fine tonal steps collapsed into visible grain.

Analysis had scored the change as tonally *more* accurate — but only when
measured against the very numbers that produced it, which was circular. Read
against the nominal model, it runs **+9 to +23 too bright** on every test image,
matching the operator's description of "white washed". If the measured palette
described the panel, that version would have looked right. It did not.

Conclusion: the *relative* finding (levels 3 and 4 nearly coincide) reproduced
across three photographs and is probably real. The *absolute* curve is not
trustworthy — a phone camera applies its own tone curve, and normalising only
the endpoints leaves it in the interior values. Redoing this needs a reference
of known reflectance in frame (a grey card or printed step chart), not a bare
panel.

The numbers are kept as `PANEL_APPEARANCE_MEASURED` in `palette.ts`, explicitly
unused, so a future attempt starts from the finding rather than repeating the
experiment.

## Not answered here

`design.md` open question — whether linear-light error diffusion beats
sRGB-space on the panel — was **not** tested. The sRGB-space result was good
enough on hardware that the comparison was not run. It remains open.

## Reproducing

```sh
# serve the pair
cd <scratch>/hw/ab && python3 -m http.server 8888 --bind 0.0.0.0

# flash + watch
cd firmware
pio run -e dither_ab -t upload --upload-port /dev/cu.usbserial-220
pio device monitor -e dither_ab --port /dev/cu.usbserial-220

# restore the real firmware
pio run -e inkplate10 -t upload --upload-port /dev/cu.usbserial-220
```

## Blue noise replaces Floyd–Steinberg for photo zones

Same day, after the operator judged Floyd–Steinberg output still "not clean"
against the source on a high-key image.

Decomposing the residual showed why the earlier resampling work barely helped:
dither texture sat **+32 to +45** above ideal continuous tone, while switching
Chromium's resampler for Lanczos was worth only **+0.8 to +11.4**. The dominant
term was the dither, not the resample.

### The measurement that reversed the decision

Scored first at a 1px perceptual blur, blue noise looked *worse* on three of
four images and was nearly discarded. That was a bad metric, not a bad result —
1px models an observer with their nose against the glass. Repeating across blur
radii:

| blur (viewing distance) | winner |
|---|---|
| 0.5 – 1.5 (inspection) | Floyd–Steinberg |
| 3.0 | blue noise, 3 of 4 |
| **4.0 (across a room)** | **blue noise, 4 of 4** |

Floyd–Steinberg conserves error exactly, so it is more accurate up close. But
its error is *correlated*, surfacing as worm and maze texture. Blue noise places
the same error at high spatial frequency, where distance removes it — on the
Hiroshige, RMSE at 4px falls from 2.87 to 0.79.

A fridge panel is read from across a room, so the far-field number is the one
that counts.

### Notes

- Mean tone is unchanged (within ±1.5). An early hypothesis that blue noise
  "drifts dark" was wrong and was withdrawn after measurement; the operator's
  impression of extra density comes from evenly-spread dots reading as more
  continuous ink than clumped ones at equal coverage.
- The matrix is baked by `npm run bake:blue-noise` into
  `renderer/src/image/blueNoise.generated.ts` (void-and-cluster, 64×64,
  seeded and reproducible). Spectrum check: high/low frequency energy 68:1.
- `floydSteinberg` is retained in `dither.ts`, unused by the render path, for
  comparison work.

**Twice today an operator's eye overruled a metric of mine** — first on the
palette calibration, then here. Both times the metric was measuring the wrong
thing at the wrong scale. Worth remembering before trusting the next one.

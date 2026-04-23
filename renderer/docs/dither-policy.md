# Dither policy

Floyd-Steinberg error-diffusion against the Inkplate 8-level palette is
applied **only to pictorial zones**. UI zones hard-quantize so text and rules
stay sharp.

## Per-mode policy

| Mode | Dithered zones | Hard-quantized zones |
| ---- | -------------- | -------------------- |
| Summary | Delight image (when present) | Clock, weather, HN, climate, paper background |
| Weather | — | All zones |
| Gallery visual-day | Hero image | Footer chrome |
| Gallery text-day | — | All zones (typography must be sharp) |
| Night | Nocturne image | Clock, poetic weather line, fragment |
| Now-Playing | Album art | Title, artist, source, clock |

## Masks

Per-mode `ditherMask(input)` returns one of:

- `false` → hard-quantize the entire image
- `true` → dither everywhere
- `DitherMask` → per-pixel selection (1 = dither, 0 = hard-quantize)

Masks are computed at render time because image zones depend on input
(e.g. Summary's delight-zone image is absent for some pairings; Night's
nocturne image is optional).

## Why not dither everything?

Sibbl's prior-art convergence: text-heavy content dithered to 8 levels picks
up error-diffusion noise that reads as "hobby project" rather than
"intentional". Sharp black-on-paper typography on a panel that _can_ render
intermediate greys looks strictly better than dithered text.

## Why not dither nothing?

Photographs and paintings with smooth tonal gradients band severely when
quantized to 8 levels without error diffusion. FSA photography and
chiaroscuro painting are the hardest cases; both need dither.

See `/dither-test` or `docs/dither-test-results.md` for concrete evidence
on six categories (four strong, two weak).

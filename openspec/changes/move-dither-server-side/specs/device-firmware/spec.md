## ADDED Requirements

### Requirement: Panel draw path does not dither

The firmware SHALL draw mode PNGs with the Inkplate library's dither disabled. `RealDisplay::drawImageFromUrl` SHALL call `Inkplate::drawImage(url, x, y, dither=false, invert=false)`.

The renderer delivers pixel values already constrained to the Inkplate palette `[0, 36, 73, 109, 146, 182, 219, 255]`. With dithering disabled, the library's level selector `RGB3BIT(r,g,b) = (54r + 183g + 19b) >> 13` reduces for greyscale input to `floor(v/32)`, mapping the palette 1:1 onto panel levels 0–7 with no arithmetic loss:

```
0→0   36→1   73→2   109→3   146→4   182→5   219→6   255→7
```

The firmware SHALL NOT re-enable library dithering. The library's monochrome `ditherGetPixelBmp` diffuses error against a quantizer whose output range ({0…224}) does not match what the panel emits ({0…255}), producing a systematic brightness bias; see `rendering-pipeline` → "Selective dithering".

#### Scenario: Drawing a mode PNG

- **WHEN** the device fetches `/display/gallery.png` and draws it during a full-cycle wake
- **THEN** `drawImage` is called with `dither=false`, and each PNG pixel maps to exactly one panel level with no error diffusion on device

#### Scenario: Palette round-trip is exact

- **WHEN** a PNG pixel carrying any of the eight palette values is decoded
- **THEN** the resulting panel level equals that value's palette index, and no two distinct palette values collapse to the same level

### Requirement: Firmware and renderer dither settings are co-deployed

The firmware's dither flag and the renderer's `RENDERER_DITHER` setting SHALL be changed together. The two mismatch states both degrade the panel:

| Firmware | Renderer | Result |
|---|---|---|
| `dither=true` | `server` | Double error diffusion over already-quantized input — visible smudge |
| `dither=false` | `device` | Hard 3-bit truncation of full-range greyscale — heavy banding |

Deployment SHALL flash the firmware first and flip the renderer second, so that the transient mismatch is the banding case — degraded but obviously wrong — rather than the smudge case, which is subtle enough to be mistaken for correct output.

#### Scenario: Correct deployment order

- **WHEN** the operator rolls out this change
- **THEN** the firmware is OTA'd with `dither=false` while the renderer is still in `device` mode, the panel bands visibly for the duration, and the renderer is then flipped to `server` and restarted, after which the panel renders correctly

#### Scenario: Rollback without reflashing

- **WHEN** hardware output is judged worse than before and the operator sets `RENDERER_DITHER=device` and restarts the renderer
- **THEN** the panel returns to banded-but-legible output without an OTA cycle, and a subsequent firmware revert restores the pre-change rendering

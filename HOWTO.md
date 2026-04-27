# How-tos

Recipe-level guides for the most common edits. For deeper context, follow
the cross-references into [`ARCHITECTURE.md`](ARCHITECTURE.md), per-area
READMEs, or the source.

- [Add a corpus item](#add-a-corpus-item)
- [Override today's triplet](#override-todays-triplet)
- [Customize the schedule (tier cadences and main faces)](#customize-the-schedule)
- [Change which face the tap flips to](#change-which-face-the-tap-flips-to)
- [Add a new face](#add-a-new-face)
- [Add a new render input](#add-a-new-render-input)
- [Re-bake the on-device clock glyphs](#re-bake-the-on-device-clock-glyphs)
- [Debug a tap that didn't register](#debug-a-tap-that-didnt-register)
- [Debug a face that's not refreshing](#debug-a-face-thats-not-refreshing)
- [Roll out a firmware change](#roll-out-a-firmware-change)
- [Roll out an HA change](#roll-out-an-ha-change)

---

## Add a corpus item

A corpus item is a single sidecar YAML under `corpus/<tier>/` describing
one image or text. Tiers: `public_domain/`, `personal_library/`, `cc0/`.

```sh
# Sketch a sidecar from a URL (use a similar item as a template)
cp corpus/personal_library/oliver-uses-of-sorrow.yaml \
   corpus/personal_library/<your-poet>-<your-poem>.yaml
$EDITOR corpus/personal_library/<your-poet>-<your-poem>.yaml

# Validate
corpus validate            # structural + taxonomy + manifest
corpus validate --full     # also sha256-verify all manifest entries

# If image, also run
corpus refetch             # in case panel_fidelity verdict needs a re-fetch
```

Required fields depend on the item's `kind` (image vs text). Common ones:

```yaml
id: <slug>                                # MUST match filename basename
kind: image | text
tier: personal_library | public_domain | cc0
title: ...
artist: ... (or author: ... for texts)
year: 1932                                # int or YYYY-MM-DD-ish range
panel_fidelity: native | robust           # NOT color-dependent (rejected)
themes: [theme1, theme2]                  # from corpus/_taxonomy/themes.yaml
mood: [...]                               # from mood.yaml
register: [...]                           # from register.yaml
form: aphorism | sonnet | haiku | ...     # text only, from form.yaml
citation: 'Source URL or print citation'  # required for personal_library
smart_pill:
  body: 'A 400-character interpretive gloss.'
  generated_at: 'YYYY-MM-DD'
  model: 'claude-haiku-4-5'
```

The taxonomy is **closed** — adding a new mood/register/theme/form term
requires going through the amendment procedure in
[`corpus/_taxonomy/README.md`](corpus/_taxonomy/README.md). Items
referencing unknown terms fail validation.

After validate passes, the item is in the pool. Triplets are regenerated
by `pairing/build_triplets.py` (run manually after a substantial edit
batch) — the daily picker reads the existing triplet pool, so new items
won't be picked until you regenerate.

---

## Override today's triplet

Pick any triplet (e.g., for testing a new sidecar):

```sh
python3 pairing/publish_today.py --id <triplet-id>
```

`<triplet-id>` is the basename of any file under `corpus/_triplets/`.
Today's panel will display the override on the next render. Tomorrow at
06:00 the natural rotation resumes (the override doesn't persist).

To preview without committing files:

```sh
python3 pairing/publish_today.py --id <triplet-id> --dry-run
```

---

## Customize the schedule

The schedule lives in **two** places that have to stay aligned.

### Device-side cadence — `firmware/src/wake.cpp`

```cpp
constexpr Tier tierFor(int min_of_day) {
  if (min_of_day >= 1320 || min_of_day < 390) return {15, 0, 0, false}; // Night
  if (min_of_day < 600 || min_of_day >= 1020) return {15, 3, 1, false}; // Morning + Evening
  return {30, 0, 5, true};                                              // Midday
}
```

`Tier{full_min, poll_min, partial_min, partial_brings_poll}`. Boundaries
are `(start_min_of_day, end_min_of_day)` half-open. Modify and reflash
the device.

### HA-side alternation — `ha/automations/schedule.yaml`

```yaml
target: >-
  {% if m < 10*60 %}
    {% set tier_start = 6*60 + 30 %}
    {% set tier_full = 15 %}
    {% set tier_main = 'summary' %}
  {% elif m < 17*60 %}
    {% set tier_start = 10*60 %}
    {% set tier_full = 30 %}
    {% set tier_main = 'gallery' %}
  {% else %}
    {% set tier_start = 17*60 %}
    {% set tier_full = 15 %}
    {% set tier_main = 'gallery' %}
  {% endif %}
```

Three things to keep aligned with `firmware/src/wake.cpp`:

- `tier_start` and `tier_end` boundaries.
- `tier_full` (Full cadence in minutes) — must match the device's
  `full_min`, otherwise mode-change publishes won't land on a Full wake.
- `tier_main` — the face that alternates with Weather in this tier.

After editing, `make deploy-ha` and reflash if you also touched the
firmware tier table. The device's first wake under the new cadence will
re-read the retained `active_mode` and pick up the new schedule.

---

## Change which face the tap flips to

The tap handler in `ha/automations/gesture_override.yaml` flips
`input_number.inkplate_alternation_offset` between 0 and 1. Currently
that XORs against the natural parity, so a tap toggles the displayed
face within whatever pair the current tier is alternating
(Summary↔Weather or Gallery↔Weather).

To change *what* the tap does:

- **Different action target** (e.g. tap → Now-Playing instead of phase
  flip): edit the `action:` block in `inkplate_gesture_tap_phase_flip`.
  Probably you want to drop the offset flip and instead publish
  `active_mode = now-playing` (and an override entry).
- **Different gesture maps to different action**: re-introduce a
  distinct single-tap automation. Be aware that on the wire-tied frame
  mount, the LSM6DSO often latches `double` for what feels like a
  single tap (the frame ring crosses threshold twice). Splitting them
  practically means firm taps go one way and soft taps go the other —
  hard to operate consistently.
- **Suppress in additional contexts**: add conditions to the
  automation. The existing ones gate on quiet hours and active
  override.

Apply with `make deploy-ha`.

---

## Add a new face

A face is a (mode-name, template, dispatcher, optional schema)
quadruple. The naming convention is the kebab-case mode name throughout.

1. **Template**: `renderer/templates/<mode>/{<mode>.css}`. Inheriting
   from `templates/shared/tokens.css` and `layout.css` is conventional.
2. **Mode dispatcher**: `renderer/src/modes/<mode>.ts`. Implements
   `buildHtml(input)` and (optionally) `ditherMask(input)`. Looks at
   `input.<things>` and emits an HTML string. Use `htmlShell({title,
   styles, body})` from `modes/shell.js`.
3. **Schema**: extend `renderer/src/modes/schema.ts` with the new mode's
   Zod input contract, and add a `gather<Mode>()` in `modes/index.ts`
   that loads the relevant `inputs/*.json` files.
4. **Mode constant**: add the kebab-case name to `MODES` in
   `src/config.ts`.
5. **Test fixture**: drop `renderer/test/fixtures/<mode>.json` with a
   minimal valid input shape. `npm test` snapshots and asserts the PNG
   is stable.
6. **HA wiring**: if you want the schedule alternation to surface the
   new face, edit `ha/automations/schedule.yaml`'s `tier_main` for the
   relevant tier OR introduce a new override.
7. **Firmware mode constant**: `firmware/include/modes.h` enum + the
   `parse()` mapping in `firmware/src/modes.cpp`. Add the timer/cadence
   the device should use when this is the active mode.

After all of the above:

```sh
cd renderer && npm run build && npm test       # check schema + snapshot
make deploy-ha                                  # redeploy automation if needed
cd firmware && pio run -e inkplate10 --target upload
```

Don't forget to consider whether the new face needs a clock zone (and
if so, whether its font_size already has a baked preset — if not,
re-bake per [Re-bake the on-device clock glyphs](#re-bake-the-on-device-clock-glyphs)).

---

## Add a new render input

Inputs are JSON files in `renderer/inputs/` that templates consume.
Existing: `clock.json`, `weather.json`, `pairing.json`, `news.json`,
`sonos.json`, `device.json`. To add `<your-input>`:

1. **Decide on the publisher path**:
   - Push from HA: `POST /inputs/<your-input>` (auth-bearer token in
     `RENDERER_INPUT_TOKEN`). HA wires this through
     `ha/integrations/rest_commands.yaml` + a publisher automation in
     `ha/automations/publish_inputs.yaml`.
   - Direct file write from a daily script: write
     `renderer/inputs/<your-input>.json` directly (this is what
     `pairing/publish_today.py` does for `pairing.json`).
2. **Whitelist in the renderer**: add `'<your-input>'` to
   `WRITABLE_INPUTS` in `renderer/src/server.ts:17`. Otherwise the POST
   endpoint returns 404.
3. **Schema**: add a Zod schema in
   `renderer/src/modes/schema.ts`.
4. **Loader**: extend the relevant `gather<Mode>()` in
   `renderer/src/modes/index.ts` with `await requireInput('<your-input>')`
   (fails the render if missing) or `await loadInput('<your-input>')`
   (graceful-degradation: returns `undefined` if missing).
5. **Use it in the template**: read `input.<your-input>` in your mode's
   `buildHtml()`.
6. **Update the publisher**: HA REST command, or daily script.

Atomic-write convention is enforced by `server.ts:writeInputAtomic` —
temp file + rename. Direct disk writers should also use mv-after-write
to avoid templates reading half-written JSON.

---

## Re-bake the on-device clock glyphs

If you change the CSS for any clock element (`.clock`, `.gv-clock`,
`.np-clock`, `.gt-corner-time`), the firmware's baked Fraunces glyphs
will no longer match the renderer's output, and partial-refresh digits
will visibly drift from the Full's pixels.

```sh
cd renderer
npm run bake:clock-glyphs

# Verify the bake size — three presets (Summary 160u, Compact 44u,
# Corner 28u) sum to ~13 KB of bitmap data.
ls -la ../firmware/src/generated/clock_glyphs.cpp

# Reflash
cd ../firmware
pio run -e inkplate10 --target upload
```

The bake script renders all 11 chars (10 digits + colon) in a single
tnum-enabled string, measures each via the Range API, and writes
`firmware/src/generated/clock_glyphs.{h,cpp}`. The firmware build picks
them up automatically.

If you add a new clock font_size that's not in `PRESETS` of
`bake-clock-glyphs.ts` (e.g. introducing a 36u clock for a new face),
add it to that array, re-bake, AND extend `presetByFontSize()` in
`firmware/src/main_loop.cpp`.

---

## Debug a tap that didn't register

The chain has many points of failure. Start at the device:

```sh
# 1. Are taps reaching the IMU? (USB-tethered.)
pio device monitor -b 115200
# Tap the frame; look for "[IMU] drain: TAP_SRC=0xNN" with bits 4
# (DOUBLE) and/or 5 (SINGLE) set. If you see "spurious ext0 wake
# (TAP_SRC empty)" the IMU INT1 fired but no event latched — likely
# tap force below threshold, kTapThreshold=1 already minimum.

# 2. Is the gesture publishing?
mosquitto_sub -h <ha-host> -t inkplate/state/gesture -v -C 1
# A real tap publishes {"kind":"single"} or {"kind":"double"} within
# ~3 s of wake.

# 3. Is HA's gesture handler firing?
curl -H "Authorization: Bearer $HA_TOKEN" \
     "http://$HA_HOST:8123/api/states/automation.inkplate_tap_schedule_flip_alternation_phase" | jq .last_triggered

# 4. Is the new active_mode landing?
mosquitto_sub -h <ha-host> -t inkplate/command/active_mode -v -C 1
```

If steps 1–3 work but the panel doesn't update, the tap flipped a
phase that resolved to the same face you're already on (taps in Night
are no-ops; tap during a tier whose `tier_main` matches the alternated
face produces the same target). Try a second tap to flip back.

If the tap-ack badge (the dot or two-dots near the battery indicator)
also doesn't appear, the IMU likely didn't latch — the issue is at
step 1, not the network.

---

## Debug a face that's not refreshing

```sh
# 1. Is HA's alternation tick firing?
curl -H "Authorization: Bearer $HA_TOKEN" \
     "http://$HA_HOST:8123/api/states/automation.inkplate_per_tier_face_alternation_tick" | jq

# 2. Is the master kill switch on?
curl -H "Authorization: Bearer $HA_TOKEN" \
     "http://$HA_HOST:8123/api/states/input_boolean.inkplate_publisher_enabled" | jq .state
# Should be 'on'. If 'off', NOTHING flows from HA to the renderer.

# 3. Is the device heartbeating?
mosquitto_sub -h <ha-host> -t inkplate/state/device -v -C 1
# Should land within 15-30 min in any tier. Look at the wake_reason
# and active_mode fields.

# 4. Is the renderer healthy?
curl http://<renderer-host>:8575/healthz

# 5. Is the renderer producing the right mode?
curl http://<renderer-host>:8575/display/<mode>/preview
# Open in browser; rules out renderer-side rendering bugs.

# 6. Tail the device.
pio device monitor -b 115200
```

The renderer's `inputs/*.json` mtimes tell you which publishers are
firing (and which aren't):

```sh
ls -la renderer/inputs/*.json
# clock.json should bump every minute (when publisher enabled).
# pairing.json should be 06:00 today.
# weather.json on each weather sensor change.
```

---

## Roll out a firmware change

```sh
# Sanity: build + run host tests
cd firmware
cmake -B build_host -S . && cmake --build build_host
./build_host/firmware_sim                        # 49 scenarios should pass

# USB-tether the device, then
pio run -e inkplate10 --target upload
pio device monitor -b 115200                     # watch first boot

# OTA isn't wired (device is in deep sleep most of the time).
# All updates are USB.
```

Common gotchas:

- Don't break the wake-mode contract that HA depends on — modes are
  paired by name in `firmware/src/modes.cpp` and
  `ha/automations/*.yaml`.
- After changing the schedule planner, host-test with new
  `firmware/test/scenarios/schedule_tests.cpp` cases.
- Adding a 1-bit drawing primitive? It must compose with the
  post-Full zone cleanup and the partial-clock seed-and-draw — verify
  ghost cleanup is still clean.

---

## Roll out an HA change

```sh
# Validate YAML locally (catches obvious syntax errors)
python3 -c "import yaml; [yaml.safe_load(open(p)) for p in __import__('glob').glob('ha/**/*.yaml', recursive=True)]"

# Push
make deploy-ha
# The script:
# - rsync-equivalent (tar over SSH) ha/ → /config/custom/inkplate/
# - copies secrets.yaml separately
# - ha core check && ha core restart  (full restart, not reload —
#   needed for new entities/helpers)
# - tails recent log

# Verify in HA UI:
# - Settings → Automations: new ones present, enabled
# - Settings → Helpers: new input_* helpers exist
# - Developer Tools → States: new entities reporting expected values
```

If something breaks:

```sh
# Quick rollback
ssh root@<HA_HOST> -p <HA_SSH_PORT>
rm -rf /config/custom/inkplate
# remove the three include lines from /config/configuration.yaml
ha core check && ha core restart
```

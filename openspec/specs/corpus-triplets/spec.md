# corpus-triplets Specification

## Purpose
TBD - created by archiving change add-corpus-schema. Update Purpose after archive.
## Requirements
### Requirement: Triplet as the unit of composition

A triplet SHALL be a curated, authored artifact binding three corpus items into a single daily composition:

- **`anchor`** — the hidden theme: a short text item whose `form` is anchor-eligible (`haiku`, `aphorism`, `fragment`, `quote`, `song-chorus`, or `lyric`).
- **`summary`** — the Summary face's delight-zone content: a single item, either an image or a short text, appropriate to the delight-zone size.
- **`gallery`** — the Gallery face's hero content: an image for visual-day triplets, a text for text-day triplets.

Triplets SHALL additionally carry:

- **`aligned_nocturne`** (optional) — the id of a nocturne-pool image for the Night face on days this triplet runs. When absent, the Night face falls back to the general nocturne pool for that date.
- **`note`** — a one-sentence operator-readable description of why these three items belong together. Not shown on the device; archival record of curatorial intent.

The anchor is the curatorial reason `summary` and `gallery` sit together. The viewer does not see the anchor by default; it is revealed only by an explicit gesture (triple-tap, subject to revision in `add-device-firmware`).

#### Scenario: Valid triplet

- **WHEN** a triplet file declares `anchor: basho-old-pond`, `summary: hcb-sunday-marne`, `gallery: atget-parc-saint-cloud`, and `note: "Quiet attention to an ordinary afternoon."`
- **THEN** validation accepts the triplet

#### Scenario: Anchor form ineligible

- **WHEN** a triplet declares `anchor: rilke-duino-first-elegy-opening` and that item's `form` is `stanzaic` (not anchor-eligible)
- **THEN** validation rejects the triplet with `anchor must be anchor-eligible form (haiku, aphorism, fragment, quote, song-chorus, lyric)`

### Requirement: Triplet filesystem layout

Triplets SHALL live under `corpus/_triplets/` as YAML files, one per triplet. Each file SHALL be named `<triplet-id>.yaml` where the id is kebab-case and unique across all triplets. Ids SHALL NOT overlap with item ids.

Triplet files SHALL be git-tracked (they are authored curatorial artifacts, not generated content).

#### Scenario: Triplet directory layout

- **WHEN** a new triplet `stillness-of-sundays` is authored
- **THEN** the file `corpus/_triplets/stillness-of-sundays.yaml` exists and is tracked by git, and no other triplet shares that id

### Requirement: Triplet sidecar schema

Each triplet YAML SHALL contain the following top-level fields:

- `id` — string, matches the file basename
- `anchor` — string, the id of an existing anchor-eligible text item
- `summary` — string, the id of an existing corpus item (image or text)
- `gallery` — string, the id of an existing corpus item (image for visual-day, text for text-day)
- `flavor` — one of `visual-day` or `text-day`; SHALL match the `gallery` item's type (visual-day → image, text-day → text)
- `aligned_nocturne` — string (optional), the id of an existing image item suited to the Night face's tall-format zone
- `note` — string, one-sentence curatorial description
- `themes` — array of theme keys from `corpus/_taxonomy/themes.yaml`; the thematic bridge between the three items
- `added` — ISO date string, when the triplet was authored

Triplets SHALL NOT carry their own `mood` or `register` fields; those are properties of the constituent items.

#### Scenario: Triplet references a nonexistent item

- **WHEN** a triplet declares `gallery: nonexistent-work`
- **THEN** validation rejects the triplet with `triplet references unknown item: nonexistent-work`

#### Scenario: Flavor/gallery-type mismatch

- **WHEN** a triplet declares `flavor: visual-day` and `gallery: cavafy-ithaca` (a text item)
- **THEN** validation rejects the triplet

#### Scenario: Triplet with aligned nocturne

- **WHEN** a triplet declares `aligned_nocturne: brassai-paris-nuit-steps` and that id exists with the item flagged as nocturne-eligible
- **THEN** validation accepts the triplet; the Night face uses this image on days the triplet runs

### Requirement: Item reuse across triplets

Triplet authoring SHALL treat the corpus as a shared pool: a single corpus item MAY appear in any number of triplets (as anchor, summary, gallery, or aligned nocturne, in any combination across different triplets). Reuse is the expected pattern — items are a pool; triplets are the authored compositions that draw from that pool.

Within a single triplet, the same item id MUST NOT appear in two slots (e.g., the same image cannot be both `summary` and `gallery`).

#### Scenario: Same item in two triplets

- **WHEN** triplet A and triplet B both reference `hokusai-great-wave` as `gallery`
- **THEN** validation accepts both triplets; the pairing pipeline handles recency-spacing at selection time

#### Scenario: Same item in two slots of one triplet

- **WHEN** a triplet declares `summary: hokusai-great-wave` and `gallery: hokusai-great-wave`
- **THEN** validation rejects the triplet with `triplet cannot use the same item in multiple slots`

### Requirement: Anchor visibility contract

The anchor SHALL NOT be rendered as part of the default Summary, Gallery, or Night face composition. It SHALL only appear through an explicit user-initiated reveal gesture, as defined by `add-device-firmware` (currently triple-tap, subject to change).

This invariant is load-bearing: the summary and gallery items must stand alone as aesthetic events. The anchor is a secret the device keeps, revealed to the viewer who asks.

#### Scenario: Summary face renders

- **WHEN** the Summary face renders with an active triplet
- **THEN** the summary item appears in the delight zone; the anchor text does not appear anywhere on the default face

#### Scenario: Reveal gesture fired

- **WHEN** the firmware reports a reveal-theme gesture while a triplet is active
- **THEN** the anchor text is rendered (typography per the item's `form`) as an overlay; after the configured dwell time or a second gesture, the default face returns

### Requirement: Pair-stands-alone invariant

For every authored triplet, the pair (`summary` + `gallery`) SHALL be operator-judged to stand alone as a composition without requiring the anchor to be understood. The anchor enriches the pair; it does not glue it together. Triplets that only "work" when the anchor is known SHALL NOT be approved.

This is an ingestion-review invariant rather than a machine-checkable rule. It is recorded here as a ratified curatorial commitment against which triplet batches are reviewed.

#### Scenario: Review rejects anchor-dependent triplet

- **WHEN** during triplet batch review the operator judges that `summary` and `gallery` have no aesthetic connection without reading the anchor
- **THEN** the triplet is rejected with reason `anchor-dependent; pair does not stand alone`

### Requirement: Panel-fidelity constraint on image slots

Any image item used in a triplet — whether as `gallery` on a visual-day triplet, as `summary` when that slot holds an image, or as `aligned_nocturne` — SHALL have `panel_fidelity ∈ {native, robust}` per `corpus-schema`. `color-dependent` items are structurally impossible because they are refused at ingestion, but triplet validation SHALL enforce the rule defensively in case a sidecar slips the ingestion gate.

This is a fidelity requirement, not a stylistic one: the 3-bit greyscale panel cannot render hue, and the pair-stands-alone invariant fails when an image's composition depends on chromatic structure the viewer cannot see.

Triplet authoring SHOULD prefer `native`-fidelity images for visual-day heroes where the curatorial idea permits; `robust` items remain eligible where the pair demands a specific tonally-strong color-origin work (a Hiroshige snow scene, a Vermeer interior). The `note` field MAY reference the value logic of the pair ("two densities of line", "silver-gelatin black against engraved black") — such notes are a signal the triplet is native to the device.

#### Scenario: Visual-day triplet with a color-dependent gallery

- **WHEN** a triplet declares `flavor: visual-day` and `gallery: warhol-marilyn` where `warhol-marilyn` has `panel_fidelity: color-dependent`
- **THEN** validation rejects the triplet with `triplet image slot requires panel_fidelity native or robust`

#### Scenario: Image in summary slot on a text-day triplet

- **WHEN** a text-day triplet declares `summary: matisse-red-studio` (an image item with `panel_fidelity: color-dependent`)
- **THEN** validation rejects the triplet with the same reason

### Requirement: Anchor items stored as regular corpus items

An anchor SHALL be referenced by id from a triplet, and the anchor text itself SHALL live in the normal corpus — under `corpus/texts/` for PD/CC0 or `corpus/personal_library/` for in-copyright, with the usual sidecar and body-file rules. There SHALL NOT be a separate "anchors" pool; anchor-eligibility is derived from the item's `form`.

A single short-form text MAY therefore serve as an anchor in one triplet and as a gallery hero (on a text-day) in another.

#### Scenario: Anchor-eligible text used as gallery

- **WHEN** `basho-old-pond` is the `anchor` in one triplet and the `gallery` in another (text-day flavor)
- **THEN** both triplets are valid; the pairing pipeline handles recency-spacing

### Requirement: Image slot orientation

Each image slot in a triplet has a rendering zone with a fixed aspect ratio on the 1200×825 panel, and images are fitted into those zones with `object-fit: cover`. The following orientation constraints SHALL be enforced at validation time based on an image item's `pixel_width` (W) and `pixel_height` (H):

- **`summary`** — when the summary slot holds an image, it SHALL be landscape or square (`W ≥ H`). Portrait images (`H > W`) are rejected.
- **`gallery`** — when the gallery slot holds an image (visual-day flavor), any orientation is permitted (landscape, portrait, or square).
- **`aligned_nocturne`** — the night image SHALL be portrait or square (`H ≥ W`). Landscape images (`W > H`) are rejected.

Square images (`W == H`) are allowed in every image slot.

Text slots have no orientation and are unaffected.

This is a composition requirement, not a fidelity one: the Summary face's delight zone is a wide landscape band; a portrait image fitted into it crops out nearly the full composition. The Night face's nocturne column is a narrow tall band; a landscape image fitted into it collapses to a thin horizontal strip of the middle. The Gallery face's canvas is large and near-square enough to accept any orientation without catastrophic loss.

Enforcement is at authoring time (in `corpus validate`), not at render time — the renderer applies the zone and trusts the authoring layer.

#### Scenario: Portrait image in summary slot

- **WHEN** a triplet declares `summary: utamaro-beauty-yamauba-kintaro` where that image has `pixel_width: 2250, pixel_height: 3000`
- **THEN** validation rejects the triplet with `summary slot -> 'utamaro-beauty-yamauba-kintaro' is portrait (2250x3000); summary requires landscape/square`

#### Scenario: Landscape image in aligned_nocturne slot

- **WHEN** a triplet declares `aligned_nocturne: brassai-pont-neuf-dawn` where that image has `pixel_width: 3000, pixel_height: 2000`
- **THEN** validation rejects the triplet with `aligned_nocturne slot -> 'brassai-pont-neuf-dawn' is landscape (3000x2000); aligned_nocturne requires portrait/square`

#### Scenario: Portrait image in gallery slot

- **WHEN** a visual-day triplet declares `gallery: friedrich-wanderer-mist` where that image has `pixel_width: 2327, pixel_height: 2980`
- **THEN** validation accepts the triplet; gallery is unconstrained on orientation

#### Scenario: Square image in any image slot

- **WHEN** a triplet declares any image slot (`summary`, `gallery`, or `aligned_nocturne`) pointing to an item with `pixel_width == pixel_height`
- **THEN** validation accepts the triplet; square is allowed in every image slot

### Requirement: Gallery hero-density for text slots

When a triplet's `gallery` slot resolves to a text item, the text body SHALL contain at least **4 lines**, unless the item's `form` is `haiku` or `tanka`. Body lines are measured by splitting the item's `text` (or first entry of `text_variants` if no `text`) on `\n` and taking the count after trimming surrounding whitespace.

The Gallery face is the day's hero. Its text zones (`poem_body`, `aphorism_body`, `quote_body`) are sized for longer hero content; short texts of 1–3 lines render with the text floating in mostly-empty space and read as sparse rather than emphatic. The Summary face's `delight_text` zone is explicitly sized for short companion texts (4 lines × 24 chars per line), and short texts SHOULD be routed there as `summary` slots.

Haiku and tanka are exempt. The 3-line haiku form is canonical; the Gallery face carries a dedicated `haiku_body` zone sized at exactly 24 × 3 for that form. A 3-line haiku is hero-sized by design.

Short texts (≤ 3 lines, non-haiku/non-tanka) remain fully eligible as `summary` or `anchor`. They are never deleted for this rule — they are routing-constrained, not corpus-excluded.

#### Scenario: Two-line quote in gallery slot

- **WHEN** a triplet declares `gallery: wright-live-forever` where that item has `form: quote` and a 2-line body
- **THEN** validation rejects the triplet with `gallery slot -> 'wright-live-forever' is too short for hero zone (2 lines, form='quote'); short texts (< 4 lines) belong in the summary slot, not gallery (haiku/tanka are exempt)`

#### Scenario: Three-line haiku in gallery slot

- **WHEN** a triplet declares `gallery: basho-old-pond` where that item has `form: haiku` and a 3-line body
- **THEN** validation accepts the triplet; `haiku` and `tanka` are exempt from the line-count floor

#### Scenario: Four-line fragment in gallery slot

- **WHEN** a triplet declares `gallery: sappho-fragment-31` where that item has `form: fragment` and a 4-line body
- **THEN** validation accepts the triplet; 4 lines meets the floor

#### Scenario: Short quote used as summary

- **WHEN** a triplet declares `summary: stein-rose` (2-line `quote`) and `gallery: hokusai-great-wave` (visual)
- **THEN** validation accepts the triplet; the gallery-density rule does not constrain `summary` slots. The `summary` slot is instead governed by `Summary text fits delight_text zone`.

### Requirement: Summary text fits delight_text zone

When a triplet's `summary` slot resolves to a text item (an item with `text` or `text_variants`), the text body SHALL fit the Summary face's `delight_text` zone budget declared in `renderer/src/zones.ts`: **max 4 lines, max 24 characters per line**.

Enforcement is at validation time. The validator SHALL read the body from `text` or (if absent) the first entry of `text_variants`, split on newlines, and report an error if:

- the number of lines exceeds 4, OR
- any single line has more than 24 characters.

A validation error SHALL include the slot id, the observed line count, the observed maximum line length, and the budget, so the operator can pick a substitute or tighten the fragment without re-reading the item sidecar.

This is a zone-fit requirement, not a taste one. The renderer returns an HTTP `VERSE_OVERFLOW` response for over-budget inputs and refuses to produce a PNG; an over-budget triplet therefore fails to render and violates the pair-stands-alone invariant by producing a blank Summary face.

Image summaries are unaffected (they are subject instead to the orientation and panel-fidelity rules).

The validator's budget constants SHALL mirror `renderer/src/zones.ts` and SHALL be updated when the zone is retuned — drift between the two produces triplets that validate but fail at render, or vice versa.

#### Scenario: Text summary exceeds line count

- **WHEN** a triplet declares `summary: keats-ode-nightingale-fragment` whose `text_variants.en` body spans 34 lines
- **THEN** validation rejects the triplet with `summary slot -> 'keats-ode-nightingale-fragment' text overflows delight_text budget (34 lines, max line N chars; budget 4 lines / 24 chars per line)`

#### Scenario: Text summary exceeds line width

- **WHEN** a triplet declares `summary: gluck-snowdrops` where at least one line of the body is 37 characters long (budget 24)
- **THEN** validation rejects the triplet with the same error message, substituting the observed line count and the 37-char maximum

#### Scenario: Text summary fits

- **WHEN** a triplet declares `summary: basho-old-pond` whose body is three short haiku lines, no line exceeding 24 characters
- **THEN** validation accepts the triplet; the delight_text zone renders without overflow

#### Scenario: Image summary

- **WHEN** a triplet declares `summary: hcb-sunday-marne` (an image item)
- **THEN** this requirement does not apply; image summaries are governed by `Image slot orientation` and `Panel-fidelity constraint on image slots`


## ADDED Requirements

### Requirement: Text body fits gallery-text zone

Every text item ingested into the corpus SHALL have a body that fits the gallery-text zone budget corresponding to its declared `form`. The zone budgets are defined in `renderer/src/zones.ts`; the form → zone mapping is defined in `renderer/src/modes/gallery.ts` (`FORM_TO_ZONE`). Both the form enumeration and the per-form budget are authoritative; `pairing/corpus_validate.py` mirrors them defensively and the two SHALL be kept in sync when the zone table is retuned.

**Form → zone → budget (at the time of this change):**

| form | zone | maxChars | maxLines |
|---|---|---:|---:|
| haiku, tanka | `haiku_body` | 24 | 3 |
| sonnet, free-verse, stanzaic, fragment, prose-poem | `poem_body` | 64 | 32 |
| aphorism | `aphorism_body` | 48 | 6 |
| quote | `quote_body` | 56 | 10 |

**Fit criteria (measured against the item's `text`, or the first entry of `text_variants` if no `text`):**

- Split the body on `\n`.
- The number of lines SHALL NOT exceed the form's `maxLines`.
- Every individual line SHALL be at most the form's `maxChars` (measured in extended grapheme clusters per `dashboard-faces`).
- For `poem_body` forms (`sonnet|free-verse|stanzaic|fragment|prose-poem`) the number of lines SHALL additionally NOT exceed the **practical 16-line 2-column cap**. The gallery-text flow uses at most 2 columns × 8 lines/col; content past this overflows vertically on the face even though it's within the hard maxLines budget.

**Form taxonomy:** A text item's `form` SHALL be one of the nine values above. Items with a form outside this taxonomy cannot be routed to any zone and SHALL be rejected.

**Enforcement points:**

- `corpus ingest-personal --commit` rejects a batch if any staged text item fails the fit check.
- `corpus validate` errors on every corpus-resident text item that fails the fit check.

**Rationale:** The renderer returns `VERSE_OVERFLOW` for over-budget inputs and produces no PNG; the Gallery face breaks. Verse zones are never truncated (per `dashboard-faces` "Zone character budgets" measurement rules). The authoring/selection layer owns the fit, and this requirement lifts that ownership from triplet-build-time back to ingest-time, where mis-fitting sidecars can be caught before they enter the active pool.

#### Scenario: Line-count overflow on ingestion

- **WHEN** `corpus ingest-personal --commit --batch-id <id>` stages a text with `form: stanzaic` whose body is 61 lines
- **THEN** the commit is aborted with `text body overflows stanzaic zone budget (61 lines, max line <N> chars; budget 32 lines / 64 chars per line)` and no files move out of staging

#### Scenario: Line-width overflow (ingestion-bug symptom)

- **WHEN** ingestion stages a text whose body is a single 259-character line (line breaks stripped during parse)
- **THEN** the commit is aborted with `text body overflows <form> zone budget (1 lines, max line 259 chars; budget N lines / M chars per line)`; the operator re-ingests with verse breaks restored

#### Scenario: Practical 2-column overflow on a poem_body form

- **WHEN** `corpus validate` encounters a `stanzaic` text item with 18 lines, all lines under 64 chars
- **THEN** validation errors with `text body exceeds practical 2-column cap (18 lines > 16; fits hard budget 32 but overflows vertically on gallery face)`

#### Scenario: Unknown form

- **WHEN** a text item declares `form: villanelle` (not in the gallery-text taxonomy)
- **THEN** validation errors with `text item has form 'villanelle' outside the gallery-text taxonomy [...]`

#### Scenario: Fitting item passes

- **WHEN** `corpus validate` encounters a `haiku` text with three lines, each ≤ 24 chars
- **THEN** validation accepts the item

### Requirement: Rejected triplets excluded from integrity checks

`corpus validate` SHALL skip a triplet's integrity checks (refs, forms, orientation, panel-fidelity, zone fit, duplicate-slot, theme taxonomy) when the triplet carries a `triplet_verdict` of `reject-content` or `reject-layout`. Rejected triplets remain in the repo as a record of the authoring decision, but they are excluded from the active pool and therefore cannot break the pool's invariants.

The triplet's own structural fields (`id` matching filename, YAML parse validity) SHALL still be checked.

#### Scenario: Rejected triplet with dangling refs

- **WHEN** a triplet is marked `triplet_verdict: reject-layout` and references an item that has since been removed from the corpus
- **THEN** `corpus validate` does NOT report the dangling reference; the triplet is ignored for integrity purposes

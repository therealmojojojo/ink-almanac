# Triplet generation (v2)

`pairing/corpus_build_triplets_v2.py` generates the daily-rotation triplet
pool for the device. One triplet per day; each bundles an anchor text, a
summary-delight text, and a gallery hero (image or text), plus an
optional aligned nocturne for the Night face.

## Quick usage

```sh
# Dry-run — stats only, writes nothing
python3 pairing/corpus_build_triplets_v2.py

# Regenerate the pool (wipes corpus/_triplets/ and writes fresh)
python3 pairing/corpus_build_triplets_v2.py --apply

# Variation via seed
python3 pairing/corpus_build_triplets_v2.py --apply --seed 7
```

The script reads from `corpus/texts/` and `corpus/personal_library/`,
writes to `corpus/_triplets/`, and caches image dark-fractions in
`corpus/_caches/dark-fractions.json`.

## What a triplet is

```yaml
id: <anchor18>-<summary18>-<gallery18>  # deterministic from slot ids
sequence: 149                            # 1-based ordering (1 triplet per day)
anchor: adams-take-or-make-photograph    # text, anchor-eligible form
summary: cicero-friendship-more-light    # text, zone-fit (≤4 lines × ≤24 chars)
gallery: horst-salvador-dal-with-melting-watch   # image (visual-day) OR text (text-day)
flavor: visual-day                       # visual-day | text-day
themes: [craft-and-play, attention-and-listening, portrait-and-face]
note: Where the line ends and the shape begins.
added: '2026-04-21'
aligned_nocturne: tmatsu-sandwich-man-shinjuku   # optional
```

Operator review verdicts, when present, live in the same sidecar:

```yaml
triplet_verdict: keep | reject-content | reject-layout
triplet_verdict_reason: "…operator note…"
triplet_verdict_reviewed_at: '2026-04-20'
```

## Rules the generator enforces

### 1. Summary is always a text
Every triplet's summary slot is drawn from the `summary_texts` pool:
- kind = text
- has at least one theme
- body fits the `delight_text` zone: ≤ 4 non-empty lines and ≤ 24 chars
  per line.

Summary-face delight is therefore always text. The Summary-face image
delight path (from the old text-day flavor) is retired.

### 2. Gallery split — 65% image, 35% text
Controlled by `TEXT_DAY_SHARE = 0.35`. A rolling random choice per
attempt; the actual output hovers within ±2% of the target.

- `visual-day` → gallery is an image (any orientation)
- `text-day`   → gallery is a text (≥ 4 lines OR form ∈ {haiku, tanka})

### 3. Per-item cap — 5
`PER_ITEM_CAP = 5`. Every item (anchor, summary, gallery, or nocturne)
appears in at most 5 triplets across the generated pool. Prevents the
runaway reuse you saw pre-v2 (e.g., Syrus' "money rules the world"
appearing in 46 triplets).

### 4. Recency window — 100 positions
`RECENCY_WINDOW = 100`. For triplet at position N, no item that appeared
in triplets N-99 … N-1 may appear again. Over an ordered roll-out where
one triplet runs per day, each item is guaranteed ≥ 100 days between
reuses.

Combined with cap = 5, the minimum span between an item's first and
last appearance is 400 days (≈ 1 year 1 month).

### 5. Nocturne eligibility by darkness
The `aligned_nocturne` slot is optional; when present, roughly 50% of
the time (`ALIGNED_NOCTURNE_SHARE`). Eligibility:
- kind = image, portrait or square (H ≥ W)
- `panel_fidelity ∈ {native, robust}`
- dark-fraction ≥ 50% (mean luminance threshold 128 on 0–255 scale,
  computed on a 200×200 thumbnail of the image binary)

This replaces the older theme-based rule (item carries the
`night-and-lamplight` theme). Current pool size: 394 (old was 33).

### 6. No theme-matching preference
Picks within each pool are uniform random. Items still must carry at
least one theme as a basic corpus-hygiene filter, but theme overlap
between anchor/summary/gallery is not required or preferred. Triplet
themes in the sidecar are composed post-hoc from the slot items'
themes.

### 7. Distinctness
Every triplet's three slot items are distinct. A given
`(anchor, summary, gallery)` combination never repeats in the pool.

## Pools, caps, and ceilings

Run the dry-run to see the current snapshot. Typical output after
this session's corpus growth:

```
POOLS: anchors=581  summary=347  gal-text=328
       gal-image=1057  nocturne=394

Generated: 1098 triplets
  visual-day:  713
  text-day:    385
  w/ nocturne: 557
  items at cap: 356
  years of daily content: 3.0
```

The bottleneck is `summary` (347 items). Each ≥ 100 summary-eligible
aphorisms or haiku adds roughly 300 more triplets.

## Dark-fraction cache

First run computes dark-fraction for every image binary with PIL
(~18 s for ~1000 images). Results cache at
`corpus/_caches/dark-fractions.json`, keyed by item id. Subsequent
runs load the cache instantly.

Delete the cache file to recompute (e.g., after replacing image
binaries).

## Verdict preservation

Before wiping `corpus/_triplets/`, the script snapshots any triplet
verdicts. After generating the new pool, for every new triplet whose
id matches an old one, the verdict is copied forward. Orphaned
verdicts (triplet ids that don't survive into the new pool) are
reported in the apply log and dropped.

Since triplet ids are deterministic from slot ids
(`<anchor18>-<summary18>-<gallery18>`), verdict carry-over works as
long as the same three items happen to be paired again under the new
randomization.

## Changing the rules

Constants are at the top of `corpus_build_triplets_v2.py`:

```python
PER_ITEM_CAP = 5            # bump to 6-7 if you want more triplets at
                            # the cost of repetition
RECENCY_WINDOW = 100        # days; shrink to 60 for a denser 2-year pool
TEXT_DAY_SHARE = 0.35       # gallery=text share
ALIGNED_NOCTURNE_SHARE = 0.50
DARK_AREA_MIN = 0.50        # raise for stricter nocturne pool
SUMMARY_MAX_LINES = 4       # keep synced with renderer/src/zones.ts
SUMMARY_MAX_CHARS = 24
GALLERY_MIN_LINES = 4
```

Most rules trade pool size against variety. Rule of thumb:
- widening nocturne darkness threshold (e.g., 0.40 → 0.60) → smaller
  pool, darker nocturnes; look at the Night face variety
- raising PER_ITEM_CAP → more triplets, more repetition
- shrinking RECENCY_WINDOW → denser pool, items recycle faster

After changing a constant, re-run `--apply` and re-inspect with the
review tool (`corpus review`).

## Interaction with the review tool

`pairing/corpus_review.py` walks every triplet in `corpus/_triplets/`
and lets the operator mark verdicts. Verdicts persist across
regeneration (see above).

The review tool also does a runtime nocturne-pool fallback when a
triplet declares no `aligned_nocturne` — it picks deterministically
from the same nocturne pool the generator used (dark-fraction based).
Once v2 pairs ~50% of triplets with an explicit `aligned_nocturne`,
the fallback only fires for the remaining half.

## Validator compatibility

`pairing/corpus_validate.py` enforces:
- every triplet's slots reference existing items
- summary-slot text is zone-fit
- anchor is anchor-eligible by form
- images used as image slots have panel_fidelity native|robust and
  correct orientation
- `aligned_nocturne` (if present) is portrait/square

v2 triplets comply with all of the above by construction. The validator
does NOT check the new rules (cap, recency, dark-fraction, text-only
summary, gallery split), because those are generator-level policy,
not corpus schema. If you change `corpus_build_triplets_v2.py` and
want the validator to enforce something, add it there explicitly.

## Reproducibility

The seed (`--seed N`, default 42) plus the input corpus fully
determines the output. Same seed + same corpus → same 1,098 triplets
in the same order. Change a sidecar and the downstream sequence
changes deterministically from that point.

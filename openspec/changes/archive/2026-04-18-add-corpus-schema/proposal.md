## Why

The dashboard's daily Gallery and Summary content is driven by a curated pool of images and texts. Every downstream capability — ingestion, pairing, rendering, typography routing — depends on a shared, unambiguous contract for how corpus items are described. Without that contract defined first, tagging drifts, retrieval queries break, and the daily pipeline cannot be implemented reliably.

This change establishes the structural foundation: the sidecar YAML schema for corpus items, the filesystem layout, tier conventions, and the initial controlled vocabularies (themes, mood, register, form) that all subsequent changes consume.

## What Changes

- Define a YAML sidecar schema for corpus items covering identity, attribution, provenance, rights tier, form, language, and three tag dimensions (themes, mood, register).
- Define filesystem layout under `corpus/` separating images, texts, nocturne pool, and personal-library tier.
- Define a rights-tier convention: `public_domain`, `cc0`, `personal_library` (EU private-copy exception, Romania Law 8/1996 Art. 34). The `personal_library` tier covers any in-copyright work admitted for private, non-commercial display on the operator's own device, whether acquired by scanning a personally owned book OR by fetching a publicly visible reproduction from the web (museum page, artist site, literary archive, publisher preview). Citation to a canonical published source is required regardless of acquisition channel.
- Introduce a starting **theme vocabulary** of 33 entries grouped as register, time & pace, subject, traditions, orientations.
- Introduce a **controlled mood vocabulary** (~25 terms) and **controlled register vocabulary** (~15 terms), enforced at ingestion and amendable only through explicit vocabulary changes.
- Introduce a **form vocabulary** (text forms: `haiku`, `tanka`, `sonnet`, `free-verse`, `stanzaic`, `fragment`, `aphorism`, `prose-poem`, `quote`, `song-chorus`, `lyric`; image forms: `etching`, `engraving`, `woodblock`, `lithograph`, `drawing`, `photograph`, `painting`, `ink-wash`, `silverpoint`). Drives per-form typography routing in the renderer. A subset of text forms (`haiku`, `aphorism`, `fragment`, `quote`, `song-chorus`, `lyric`) is **anchor-eligible** for triplet composition.
- Introduce a **triplet artifact**: authored YAML files under `corpus/_triplets/` that bind an anchor (hidden theme), a Summary content item, a Gallery hero, and an optional aligned nocturne. Triplets are the unit of daily composition; the pairing pipeline selects a triplet per day rather than sampling items by tag overlap.
- Define a binary-storage policy: sidecars are git-tracked (metadata only); binaries are git-ignored and restored from external backup via a manifest with checksums. For `rights_tier: personal_library` text items, the text body itself is treated as a binary — stored in a git-ignored sibling file and covered by the manifest — so that copyrighted text bodies never enter git history.
- Gitignore + manifest + restore-script convention documented but implementation deferred to `add-corpus-ingestion`.

## Capabilities

### New Capabilities

- `corpus-schema`: The structural contract for corpus items — sidecar fields, filesystem layout, rights tiers, binary-storage policy, and manifest format.
- `corpus-taxonomy`: The controlled vocabularies (themes, mood, register, form) and the rules for amending them.
- `corpus-triplets`: The structural contract for authored triplets — the unit of daily composition binding a hidden anchor, a Summary-face content item, and a Gallery-face hero, with an optional aligned nocturne for the Night face. Anchor visibility is gesture-gated (triple-tap reveal).

### Modified Capabilities

None — this is the foundation; nothing pre-exists.

## Impact

- **New files**: `corpus/` directory tree, `corpus/_taxonomy/themes.yaml`, `corpus/_taxonomy/mood.yaml`, `corpus/_taxonomy/register.yaml`, `corpus/_taxonomy/form.yaml`, `corpus/_manifest.json` (schema only; content populated by ingestion).
- **Gitignore rules** for `corpus/images/*.{jpg,jpeg,png,tif,tiff,webp}`, `corpus/nocturne/*.{jpg,jpeg,png,tif,tiff,webp}`, `corpus/personal_library/*.{jpg,jpeg,png,tif,tiff,webp}`.
- **No code yet**: this change defines contracts consumed by downstream changes. Ingestion (`add-corpus-ingestion`), pairing (`add-pairing-pipeline`), and rendering (`add-rendering-pipeline`) all bind to these shapes.
- **Supersedes** the ad-hoc YAML examples in `requirements/Requirements.md`. Once specs ratify, that doc is reference-only.

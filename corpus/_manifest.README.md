# corpus/_manifest.json

Binary inventory: one entry per content body that is not in git (every image binary under `corpus/images/`, `corpus/nocturne/`, `corpus/personal_library/`, plus any optional `<id>.body.<lang>.txt` files). The manifest is the source of truth for restoration — a fresh clone rebuilds the working corpus from git + this file + the configured backup.

## Schema

```json
{
  "schema_version": 1,
  "created": "YYYY-MM-DD",
  "entries": [
    {
      "path": "corpus/images/<id>.jpg",
      "sha256": "<64-hex>",
      "bytes": 1234567,
      "mime": "image/jpeg",
      "backup_uri": "file:///absolute/path/or/scheme-url"
    }
  ]
}
```

### Top-level

| Field | Type | Meaning |
|---|---|---|
| `schema_version` | integer | Increment on a breaking schema change. Current: `1`. |
| `created` | ISO date | When the manifest was first initialised. |
| `entries` | array | One entry per content body. Order is not significant. |

### Entry fields

| Field | Type | Meaning |
|---|---|---|
| `path` | string | Corpus-relative file path (starts with `corpus/`). Must resolve to a file on disk for validation to pass. |
| `sha256` | string | Lowercase 64-char hex digest of the file contents. Verified by `corpus_validate.py --full` and by restore. |
| `bytes` | integer | File size in bytes. |
| `mime` | string | `image/jpeg`, `image/png`, `image/tiff`, `image/webp`, `text/plain`. |
| `backup_uri` | string | Where the binary can be retrieved from external backup. See "Backup URIs" below. |

## Backup URIs

Scheme determines routing policy. Supported schemes:

| Scheme | Tier eligibility | Meaning |
|---|---|---|
| `file://` | all tiers | Operator-local path (the seed baseline). Acts as both authoritative copy and backup for now. |
| `icloud://` | all tiers, incl. personal-library | Operator iCloud Drive container. |
| `b2://` | PD / CC0 only by default; personal-library requires explicit opt-in | Backblaze B2 bucket. |
| `s3://` | PD / CC0 only by default; personal-library requires explicit opt-in | S3-compatible bucket. |

The tier restriction reflects the personal-library non-distribution obligation: content backed by a third-party object store leaves operator control, so it's opt-in only. The ingestion tool is expected to enforce this when it lands (see `openspec/changes/add-corpus-ingestion/`).

## Invariants

- Every on-disk binary under a gitignored corpus folder has exactly one manifest entry.
- Every manifest entry resolves to a file on disk.
- Manifest is regenerated whenever binaries are added, replaced, or removed.

`corpus_validate.py` checks the bidirectional invariant; `--full` additionally verifies sha256.

## Operational notes

- Regenerate after adding a binary; do not hand-edit `bytes` or `sha256`.
- Do not include sidecar YAMLs in the manifest — those are in git.
- For text items stored inline in the sidecar YAML (the default), there is no manifest entry. Only when a `.body.<lang>.txt` file exists alongside a sidecar does it earn one.

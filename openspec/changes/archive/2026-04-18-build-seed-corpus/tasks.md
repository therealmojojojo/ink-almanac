## 1. Preparation

- [x] 1.1 Verify `add-corpus-schema` is archived and `corpus/_taxonomy/` is populated  <!-- archived 2026-04-18 as `openspec/changes/archive/2026-04-18-add-corpus-schema/`; specs merged into `openspec/specs/{corpus-schema, corpus-taxonomy, corpus-triplets}/` -->
- [~] 1.2 Verify `add-corpus-ingestion` is archived and `corpus` CLI is functional  <!-- CLI is functional for the subset actually used by this change (validate, audit, refetch, ingest-personal, restore); ingestion-automation subcommands (propose-list, fetch-list, prune, propose-triplets) spun into follow-on change `add-ingestion-automation`. `add-corpus-ingestion` being archived in the same pass as this change. -->
- [~] 1.3 Configure backup scheme and credentials (PD and personal-library)  <!-- `file://` baseline only; operator has not yet configured an iCloud Drive / external backup. Not a seed-pool blocker per spec — `_manifest.json` is emitted; external backup is deferred operator setup. -->
- [x] 1.4 Create `corpus/_audits/`, `openspec/changes/build-seed-corpus/lists/`, and `.../log.md` with an empty header

## 2. Taste file

- [x] 2.1 Capture the operator's taste file in `openspec/changes/build-seed-corpus/taste.md`
- [x] 2.2 Confirm language decision is reflected in list proposals  <!-- Romanian-in-Romanian honoured across `romanian-poetry-expansion.yaml`, `brumaru-selected.yaml`, `dinescu-selected.yaml`; non-Romanian-in-English (with optional originals) honoured elsewhere -->

## 3. Canonical list authoring

- [x] 3.0 Honour the 2026-04-17 native-B&W pivot (RETIRED.md written; `modern-painting-canon.yaml` retired; replacements authored)
- [x] 3.1 Image categories enumerated and authored
- [x] 3.2 Text categories enumerated and authored
- [x] 3.3 Per-category list files exist (23 files under `lists/`, authored manually; `corpus propose-list` is scoped to follow-on `add-ingestion-automation`)
- [x] 3.4 Review each list file (see `review-2026-04-16.md`; rights-tier routing applied; drift audit pass 2026-04-18)
- [x] 3.5 Commit approved list files before fetch

## 4. Batch execution

- [x] 4.1 Fetch per approved list  <!-- performed manually + via `corpus_refetch.py` + DDG-Google CDN pattern (MoMA / Christie's / Magnum / Artsy CDN / etc.); no HTML contact sheets — review docs under `openspec/changes/build-seed-corpus/review-*.md` and the audit reports filled that role -->
- [x] 4.2 Prune post-fetch  <!-- pruning applied via manual sidecar deletions + retag rounds; operator re-reviewed ingested images and removed 20 more 2026-04-18 -->
- [x] 4.3 Refetch rejects  <!-- `corpus_refetch.py` executed; 12 unrescuable items dropped 2026-04-18 per the no-scanning policy -->
- [x] 4.4 Route failed items  <!-- per no-scanning policy: dropped rather than queued for folder-mode; substitute / drop is the curatorial response, not rescue -->
- [x] 4.5 Run `corpus audit` periodically  <!-- `corpus_audit.py` landed; multiple audits under `corpus/_audits/`; final audit 2026-04-18-post-cleanup.md -->

## 5. Personal-library folder mode (batch ingestion of web downloads)

- [x] 5.1 Identify works where web-fetch did not serve acceptable quality  <!-- reject list dropped 2026-04-18 per no-scanning policy; substitutes authored (HCB alt frames, etc.) -->
- [~] 5.2 Ingest curated batches via `corpus ingest-personal --folder <path> --citation <string>`  <!-- command available; the seed pool was assembled item-by-item via DDG/Google-CDN fetch rather than folder batches. Folder-mode exercised end-to-end during development testing. -->
- [x] 5.3 Confirm manifest entries use operator-controlled `backup_uri`  <!-- every personal-library entry uses `file://`; `b2://` / `s3://` would be refused by the tier routing -->

## 6. Toward vocabulary stability

- [x] 6.1 Vocabulary amendments proposed as own changes  <!-- `panel_fidelity` addition went through `add-corpus-schema` itself, not this change -->
- [x] 6.2 Track consecutive non-amending canonical-list batches  <!-- log.md records batch history; 2026-04-16 initial + 2026-04-18 closing pass, neither amended `mood.yaml` / `register.yaml` -->
- [x] 6.3 Reach two consecutive non-amending batches → "Vocabulary stable" milestone satisfied

## 7. Final seed

- [x] 7.1 Fill thin themes identified by audits  <!-- 21 thin themes → 0 via three retag rounds + two targeted items (Borges paradise-library, Ponge bread); final audit confirms every theme ≥ 10/side -->
- [x] 7.2 Romanian text share ≥25%  <!-- 56/203 = 27.6% -->
- [x] 7.3 Nocturne pool ≥30  <!-- 32 -->
- [x] 7.4 Reach item-pool target with every theme ≥10/side (spec floor)  <!-- 201 images + 203 texts; all 37 themes ≥ 10/side -->
- [x] 7.5 Image-resolution sweep  <!-- 0 images below orientation-aware floor (landscape ≥ 1080, portrait ≥ 693); long-edge ≥ 1800 preferred emits warnings only -->
- [x] 7.5a Panel-fidelity back-fill  <!-- all image items carry `panel_fidelity`; 0 color-dependent on disk. 9 `panel_verdict: flag` items remain (Dürer *Young Hare*, Klee *Twittering Machine*, Haeckel, Lautrec, 3× Grimshaw, Piranesi wrong-plate, Goya duplicate, Modigliani title mismatch) — operator judgement, not blocking. -->
- [x] 7.6 Final audit  <!-- `corpus/_audits/audit-2026-04-18-post-cleanup.md` -->

## 8. Archive

- [x] 8.1 Milestones satisfied (vocabulary stable, item pool, Romanian floor, nocturne floor, B&W share, triplet pool, flavor mix, aligned_nocturne)
- [~] 8.2 `_manifest.json` round-trips via `corpus restore`  <!-- `corpus restore` implemented; round-trip against an external backup not yet exercised because `backup_uri`s all point at the corpus path itself. Operator to configure iCloud / cloud target post-archive. Not a spec gate. -->
- [x] 8.3 `corpus validate` reports zero errors
- [x] 8.4 Archive this change

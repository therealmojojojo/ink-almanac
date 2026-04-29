#!/usr/bin/env python3
"""corpus — unified CLI dispatcher for Inkplate corpus tooling.

This is the entry point described in `openspec/changes/add-corpus-ingestion/`
(§1.1, §3.5). Subcommands delegate to the standalone scripts that live
alongside this file, which remain runnable on their own.

Usage:
    corpus validate [--full]
    corpus audit [--out PATH] [--format md|json]
    corpus refetch [ids...] [--dry]
    corpus ingest-personal --folder PATH --citation STRING [...]
    corpus ingest-personal --commit --batch-id ID
    corpus restore [--check | --verify | --force] [paths...]
    corpus help

From the repo root during development:
    python3 pairing/inkplate_corpus_cli.py <subcommand> [...]

Subcommands not yet implemented (planned under add-corpus-ingestion):
    propose-list, fetch-list, fetch-binaries, prune
"""
from __future__ import annotations
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))


HELP = """\
corpus — Inkplate corpus CLI

Implemented subcommands:
  validate [--full]                  Check every sidecar, triplet, and manifest
                                     entry. --full additionally verifies sha256.
  audit    [--out PATH] [--format md|json]
                                     Read-only coverage / gate-status report.
  refetch  [ids...] [--dry]          Rotate rejected image items through
                                     Commons / ARTIC / Met at ≥ 1200 px.
  ingest-personal --folder <path> --citation <string> [--nocturne]
                                     Phase 1: stage a folder of web-downloaded
                                     images / typed text fragments into
                                     corpus/_staging/<batch-id>/.
  ingest-personal --commit --batch-id <id>
                                     Phase 2: move a reviewed staged batch into
                                     corpus/personal_library/ and append to
                                     _manifest.json.
  restore  [--check | --verify | --force] [paths...]
                                     Rebuild missing binaries / body files from
                                     the manifest's backup_uri. Verifies sha256.
  review   [--port N] [--renderer URL] [--only-unreviewed] [--start ID]
                                     Open an in-browser triplet review UI
                                     backed by the local renderer. Captures
                                     accept / reject-content / reject-layout
                                     per triplet and writes verdicts back to
                                     the triplet sidecar.
  build-review-page  [--mode extracts|unterminated] [--out-html PATH]
                                     [--out-renders-dir PATH] [--force]
                                     Build a static HTML review page.
                                     mode=extracts (default) shows every
                                     sidecar touched by Stage-1 fragment
                                     extraction. mode=unterminated shows
                                     every body that doesn't end at a
                                     phrase delimiter (with KEEP / RE-
                                     EXTRACT suggestions). Each card
                                     embeds a production summary-face
                                     PNG rendered via the test renderer.
  audit-truncations  [--ids id ...]  Print every corpus body that ends
                                     with a comma, a dangling function
                                     word, or no terminal punctuation —
                                     a quick text-only audit of
                                     truncation patterns. Run after
                                     large ingest passes.
  harvest  <creator> [--shortlist PATH] [--query STR] [--max-results N]
                                     Photographer-level DDG harvest: query,
                                     gate, pHash dedup, render contact sheet
                                     and decisions.yaml under
                                     corpus/_staging/harvest-<creator>/.
  harvest --commit <creator>         Read decisions.yaml and commit accepted
                                     items via Claude-vision tagging.
  harvest --auto-commit <creator> [--all] [--confidence-min high|medium]
                                     Skip operator review; commit every
                                     gate+vision+confidence-passing item.
  fetch-work --creator <id> [--id <entry-id>] [--escalate]
                                     Targeted per-work fetch through a
                                     query-expansion ladder for Stage-2
                                     entries not surfaced by harvest.
  reconcile-checklist [--creator <id>] [--file PATH] [--dry-run]
                                     Match committed sidecars against Stage-2
                                     checklists and update `status` fields.
  help                               Show this message.

Planned (see openspec/changes/add-ingestion-automation/):
  propose-shortlist  Claude-drafted creator shortlist (Stage-1).
  propose-checklist  Claude-drafted per-creator works checklist (Stage-2).

Run `corpus <subcommand> --help` for subcommand-specific flags.
"""


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        sys.stdout.write(HELP)
        return 0

    sub = sys.argv.pop(1)
    sys.argv[0] = f"corpus {sub}"

    if sub == "validate":
        import corpus_validate as m
    elif sub == "audit":
        import corpus_audit as m
    elif sub == "refetch":
        import corpus_refetch as m
    elif sub == "ingest-personal":
        import corpus_ingest_personal as m
    elif sub == "restore":
        import corpus_restore as m
    elif sub == "review":
        import corpus_review as m
    elif sub == "build-review-page":
        import corpus_build_review_page as m
    elif sub == "audit-truncations":
        import corpus_audit_truncations as m
    elif sub == "harvest":
        import corpus_harvest as m
    elif sub == "fetch-work":
        import corpus_fetch_work as m
    elif sub == "reconcile-checklist":
        import corpus_reconcile as m
    elif sub == "dedup":
        import corpus_dedup as m
    elif sub in ("propose-shortlist", "propose-checklist", "propose-list",
                 "fetch-list", "fetch-binaries", "prune"):
        sys.stderr.write(
            f"corpus: '{sub}' is planned but not yet implemented.\n"
            f"See openspec/changes/add-ingestion-automation/tasks.md for status.\n"
        )
        return 2
    else:
        sys.stderr.write(f"corpus: unknown subcommand '{sub}'\n\n{HELP}")
        return 2

    result = m.main() if hasattr(m, "main") else 0
    return result if isinstance(result, int) else 0


if __name__ == "__main__":
    sys.exit(main())

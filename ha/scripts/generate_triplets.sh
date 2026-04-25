#!/usr/bin/env bash
# Regenerate the entire triplet pool in one run via SSH against the Mac host
# that holds the corpus + renderer.
#
# This is a rare operation, NOT a weekly cadence:
#  - The generator (`pairing/corpus_build_triplets_v2.py`) runs to exhaustion,
#    producing every triplet the corpus + cap-and-recency rules allow (~870
#    triplets at the time of writing → roughly 2.5 years of one-per-day
#    rotation). Once committed under `corpus/_triplets/`, the device cycles
#    through them in `sequence` order with no further runs needed.
#  - You only re-run this when (a) the corpus has grown enough to be worth
#    a fresh pool, (b) you change generation parameters (PER_ITEM_CAP,
#    flavor mix, recency window), or (c) you add a new mode that needs
#    different selection rules.
#
# There is no HA automation for this. Operators invoke the registered
# `shell_command.generate_triplets` from HA Developer Tools → Services
# (or run the python directly on the host). The shell command captures
# stdout/stderr + exit code so HA can surface failure inline.
set -euo pipefail

HOST="${RENDERER_HOST:-renderer.local}"
USER="${RENDERER_USER:-inkplate}"
KEY="${RENDERER_SSH_KEY:-/config/.ssh/id_ed25519}"

ssh -i "$KEY" -o StrictHostKeyChecking=accept-new "$USER@$HOST" \
  "cd ${INKPLATE_REPO} && python3 pairing/corpus_build_triplets_v2.py --apply"

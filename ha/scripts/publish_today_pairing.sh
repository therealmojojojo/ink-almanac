#!/usr/bin/env bash
# Pick today's triplet by sequence rotation and write it to renderer/inputs/.
#
# Fired daily at 06:00 by ha/automations/publish_today_pairing.yaml, just
# before the 06:30 schedule transition activates the morning Summary face.
# The device's first wake of the day fetches /display/summary.png from the
# renderer, which serves whatever was just written here.
#
# Idempotent: running multiple times in the same day picks the same
# triplet. Re-run safely if the morning automation fails.
#
# Rotation is opaque to HA. Mac-host state in
# pairing/_state/triplet_epoch.json records "day 1" of the cycle; from
# there the script computes today's index. To re-anchor (e.g. after
# regenerating the pool), delete that file and the next run picks up
# today as the new day 1.
set -euo pipefail

HOST="${RENDERER_HOST:-renderer.local}"
USER="${RENDERER_USER:-inkplate}"
KEY="${RENDERER_SSH_KEY:-/config/.ssh/id_ed25519}"

ssh -i "$KEY" -o StrictHostKeyChecking=accept-new "$USER@$HOST" \
  "cd ${INKPLATE_REPO} && python3 pairing/publish_today.py"

#!/usr/bin/env bash
# HAOS-side wrapper: SSH to Mac host to purge stale Sonos album-art.
set -euo pipefail

HOST="${RENDERER_HOST:-renderer.local}"
USER="${RENDERER_USER:-inkplate}"
KEY="${RENDERER_SSH_KEY:-/config/.ssh/id_ed25519}"

ssh -i "$KEY" -o StrictHostKeyChecking=accept-new "$USER@$HOST" \
  "${INKPLATE_REPO}/renderer/scripts/purge_stale_sonos_art.sh"

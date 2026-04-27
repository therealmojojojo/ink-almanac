#!/usr/bin/env bash
# HAOS-side wrapper: SSH into the Mac host and run the actual art fetch.
# The renderer inputs + album-art staging live on the Mac, so all the work
# happens there. Arguments and env pass through.
set -euo pipefail

HOST="${RENDERER_HOST:-${RENDERER_HOST}}"
USER="${RENDERER_USER:-${OPERATOR_USER}}"
KEY="${RENDERER_SSH_KEY:-/config/.ssh/id_ed25519}"

# shell-quote args so spaces/ampersands survive the double hop.
printf -v ARGS '%q ' "$@"

ssh -i "$KEY" -o StrictHostKeyChecking=accept-new "$USER@$HOST" \
  "${INKPLATE_REPO}/renderer/scripts/fetch_sonos_art.sh $ARGS"

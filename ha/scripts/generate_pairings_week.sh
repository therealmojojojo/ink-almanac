#!/usr/bin/env bash
# Run `corpus pair generate-week` via SSH against the Mac host that runs the
# renderer + corpus CLI. HAOS VM cannot run the CLI itself (wrong arch, no
# Python env); delegating over SSH keeps the canonical process on the host.
#
# The automation consumes the script's exit code + captures stdout/stderr
# for the success/failure notification.
set -euo pipefail

HOST="${RENDERER_HOST:-renderer.local}"
USER="${RENDERER_USER:-inkplate}"
KEY="${RENDERER_SSH_KEY:-/config/.ssh/id_ed25519}"

ssh -i "$KEY" -o StrictHostKeyChecking=accept-new "$USER@$HOST" \
  "cd ${INKPLATE_REPO} && corpus pair generate-week"

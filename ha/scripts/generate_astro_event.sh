#!/usr/bin/env bash
# Generate tonight's Stars-cell statement on the renderer host (where
# Skyfield + DE421 + the Anthropic SDK are pip-installed) and write the
# resulting line into HA's state file.
#
# Why SSH-from-HA instead of running directly in the homeassistant
# container: Skyfield + NumPy aren't installed in HAOS's Python (and
# wouldn't survive a core update if we sideloaded them). The renderer
# host already has Python with scientific deps for the corpus tooling, so
# this matches the same pattern as `generate_triplets.sh` and
# `publish_today_pairing.sh`.
#
# The remote script prints the rendered statement to stdout and `--dry-run`
# suppresses its own state-file write; this wrapper writes locally on the
# HA volume so the freshness sensor (`astro_event_tonight`) sees an
# updated mtime regardless of whether the remote ran.
#
# Fired by ha/automations/astro_event.yaml at 07:00 daily and on HA-start.
set -euo pipefail

HOST="${RENDERER_HOST:-${RENDERER_HOST}}"
USER="${RENDERER_USER:-${OPERATOR_USER}}"
KEY="${RENDERER_SSH_KEY:-/config/.ssh/id_ed25519}"

LAT="${1:?lat required}"
LON="${2:?lon required}"
TZ_OFFSET="${3:?tz_offset required}"

STATE_FILE="/config/custom/inkplate/state/astro_event.txt"
mkdir -p "$(dirname "$STATE_FILE")"

# Run remotely; capture stdout (the rendered Stars line). On any non-zero
# exit, leave the existing state file untouched — the freshness sensor's
# 30 h guard will eventually surface the staleness if cron keeps failing.
LINE="$(
  ssh -i "$KEY" -o StrictHostKeyChecking=accept-new "$USER@$HOST" \
    "cd ${INKPLATE_REPO} && python3 ha/scripts/generate_astro_event.py \
      --lat '$LAT' --lon '$LON' --tz-offset '$TZ_OFFSET' \
      --ephem ${INKPLATE_REPO}/ha/data/de421.bsp \
      --secrets ${INKPLATE_REPO}/ha/secrets.yaml \
      --dry-run"
)"

# Write only on a non-empty result; an empty line would knock the panel
# back to the literal "no event tonight" treatment unnecessarily.
if [[ -n "$LINE" ]]; then
  printf '%s\n' "$LINE" > "$STATE_FILE"
fi

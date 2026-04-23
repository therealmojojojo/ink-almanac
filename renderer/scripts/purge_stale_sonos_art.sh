#!/usr/bin/env bash
# Remove staged Now-Playing album art older than 24h. Called daily.
set -u
STAGING_DIR="${INKPLATE_NP_STAGING:-$HOME/inkplate-cache/now-playing}"
[[ -d "$STAGING_DIR" ]] || exit 0
find "$STAGING_DIR" -type f -mtime +1 -delete

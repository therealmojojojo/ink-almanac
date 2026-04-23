#!/usr/bin/env bash
# Fetch tonight's astronomical event from in-the-sky.org and print the title.
# Replaces the YAML `scrape` sensor, which no longer supports platform setup
# in HA 2025+. Cached via the sensor's `scan_interval` (12 h).
set -euo pipefail

URL="https://in-the-sky.org/newscalyear.php"

raw=$(curl -fsSL --max-time 15 "$URL" || echo "")

if [[ -z "$raw" ]]; then
  echo "unknown"
  exit 0
fi

script=$(cat <<'PY'
import re, sys
html = sys.stdin.read()
# The homepage lists upcoming events in .newscal_item blocks; the title of the
# first one is inside .newscal_title. Regex is sufficient — avoids pulling in
# BeautifulSoup which isn't installed in the add-on.
m = re.search(
    r'class="newscal_item".*?class="newscal_title"[^>]*>([^<]+)',
    html, re.DOTALL,
)
print((m.group(1).strip() if m else "unknown")[:64])
PY
)

printf '%s' "$raw" | python3 -c "$script"

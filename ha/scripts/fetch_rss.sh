#!/usr/bin/env bash
# fetch_rss.sh <url> <max_items> [ignored_json_path]
# Emits {"count": N, "stories": [{"title","url","domain","score":0}, ...]}.
#
# The raw feed body is piped to Python via stdin — never embedded in a Python
# string literal — so a feed containing quotes, triple-quotes, or backslashes
# cannot corrupt the parser or inject code.
set -euo pipefail

URL="$1"
N="${2:-5}"

if ! raw=$(curl -fsSL "$URL"); then
  echo '{"count": 0, "stories": []}'
  exit 0
fi

script=$(cat <<'PY'
import json, os, sys
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

raw = sys.stdin.read()
n = int(os.environ.get("MAX_ITEMS", "5"))

try:
    root = ET.fromstring(raw)
except ET.ParseError:
    print(json.dumps({"count": 0, "stories": []}))
    sys.exit(0)

items = []
for it in root.iter():
    tag = it.tag.split('}')[-1]
    if tag not in ("item", "entry"):
        continue
    title = ""
    link = ""
    for c in it:
        ctag = c.tag.split('}')[-1]
        if ctag == "title":
            title = (c.text or "").strip()
        elif ctag == "link":
            link = (c.attrib.get("href") or c.text or "").strip()
    if title and link:
        domain = urlparse(link).netloc.replace("www.", "")
        items.append({"title": title, "url": link, "domain": domain, "score": 0})
    if len(items) >= n:
        break

print(json.dumps({"count": len(items), "stories": items}))
PY
)

MAX_ITEMS="$N" python3 -c "$script" <<<"$raw"

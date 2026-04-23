#!/usr/bin/env bash
# Fetch HN top 5 → emit JSON with {"count": N, "stories": [...]}.
# Invoked by the hn_top_stories command_line sensor every 30 minutes.
#
# All JSON parsing happens inside a single Python process; no interpolation of
# network content into a shell or Python literal.
set -euo pipefail

N=5
API="https://hacker-news.firebaseio.com/v0"

ids_json=$(curl -fsS "$API/topstories.json" || echo "[]")

script=$(cat <<'PY'
import json, os, sys
from urllib.parse import urlparse
from urllib.request import urlopen

n = int(os.environ.get("MAX_ITEMS", "5"))
api = os.environ["HN_API"]

try:
    ids = json.loads(sys.stdin.read())[:n]
except Exception:
    ids = []

stories = []
for sid in ids:
    try:
        with urlopen(f"{api}/item/{sid}.json", timeout=10) as resp:
            d = json.loads(resp.read().decode("utf-8"))
    except Exception:
        continue
    url = d.get("url") or f"https://news.ycombinator.com/item?id={d.get('id')}"
    try:
        domain = urlparse(url).netloc.replace("www.", "")
    except Exception:
        domain = ""
    stories.append({
        "title": d.get("title", ""),
        "url": url,
        "domain": domain,
        "score": d.get("score", 0),
    })

print(json.dumps({"count": len(stories), "stories": stories}))
PY
)

MAX_ITEMS="$N" HN_API="$API" python3 -c "$script" <<<"$ids_json"

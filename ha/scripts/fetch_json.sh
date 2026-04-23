#!/usr/bin/env bash
# fetch_json.sh <url> <max_items> <json_path>
# json_path uses dotted access: "data.items" means obj["data"]["items"].
# Each item is expected to expose at least title + url fields.
#
# The raw JSON body is piped to Python via stdin so payload content cannot
# corrupt the interpreter. The path and max_items travel via env vars.
set -euo pipefail

URL="$1"
N="${2:-5}"
PATH_EXPR="${3:-}"

if ! raw=$(curl -fsSL "$URL"); then
  echo '{"count": 0, "stories": []}'
  exit 0
fi

script=$(cat <<'PY'
import json, os, sys
from urllib.parse import urlparse

raw = sys.stdin.read()
n = int(os.environ.get("MAX_ITEMS", "5"))
path = os.environ.get("JSON_PATH", "").strip()

try:
    obj = json.loads(raw)
except Exception:
    print(json.dumps({"count": 0, "stories": []}))
    sys.exit(0)

cur = obj
if path:
    for segment in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(segment, [])
        else:
            cur = []
            break

items = []
if isinstance(cur, list):
    for it in cur[:n]:
        if isinstance(it, dict):
            title = it.get("title") or it.get("name") or ""
            url = it.get("url") or it.get("link") or ""
            if title and url:
                domain = urlparse(url).netloc.replace("www.", "")
                items.append({"title": title, "url": url, "domain": domain, "score": 0})

print(json.dumps({"count": len(items), "stories": items}))
PY
)

MAX_ITEMS="$N" JSON_PATH="$PATH_EXPR" python3 -c "$script" <<<"$raw"

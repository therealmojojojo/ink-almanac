#!/usr/bin/env bash
# Fetch Kottke + Atlas Obscura + Aeon RSS feeds, pick the 3 most
# interesting items via Claude Haiku, and write the result to
# /config/custom/inkplate/state/curated_news.json.
#
# Shape (matches the existing HN input shape so publish_inputs.yaml needs
# only trivial edits):
#   { "count": 3, "items": [{"title": "...", "subtitle": "..."}, ...] }
#
# Zone budgets (must match renderer/src/zones.ts):
#   title    ≤ 28 chars × 2 lines (~56 visible chars)
#   subtitle ≤ 32 chars × 1 line
#
# Fallback: if Claude is unavailable or its output fails validation, take
# the first 3 Kottke items, trim each title to 28 chars at a word
# boundary. Kottke alone is usually enough to fill the block honestly.

set -euo pipefail

BASE="/config/custom/inkplate"
CONFIG="$BASE/config/poetic_weather_line.yaml"
SECRETS_FILE="$BASE/secrets.yaml"
STATE_DIR="$BASE/state"
STATE_FILE="$STATE_DIR/curated_news.json"
mkdir -p "$STATE_DIR"

if [[ -z "${ANTHROPIC_API_KEY:-}" && -f "$SECRETS_FILE" ]]; then
  ANTHROPIC_API_KEY=$(SECRETS_FILE="$SECRETS_FILE" python3 - <<'PY' || true
import os, yaml
from pathlib import Path
data = yaml.safe_load(Path(os.environ["SECRETS_FILE"]).read_text()) or {}
key = data.get("anthropic_api_key", "")
if key and key != "REPLACE_ME":
    print(key)
PY
)
  export ANTHROPIC_API_KEY
fi

# --- Fetch + parse all three RSS feeds -----------------------------------
# Emits a JSON array of {source, title} candidate objects. Handles Atom
# and RSS 2.0 transparently by walking the XML tree and matching local
# tag names. Per-source cap keeps any one feed from dominating when it
# publishes ten items in a burst.
candidates=$(python3 - <<'PY'
import json, re, urllib.request
from xml.etree import ElementTree as ET

SOURCES = [
    ("kottke.org",       "https://feeds.kottke.org/main"),
    ("atlasobscura.com", "https://www.atlasobscura.com/feeds/latest"),
    ("aeon.co",          "https://aeon.co/feed.rss"),
]
PER_SOURCE_CAP = 8
TOTAL_CAP = 24

def clean(s):
    s = re.sub(r"<[^>]+>", "", s or "")
    s = re.sub(r"&amp;", "&", s)
    s = re.sub(r"&(?:#?[A-Za-z0-9]+);", "", s)
    return re.sub(r"\s+", " ", s).strip()

def local(tag): return tag.split("}")[-1] if "}" in tag else tag

merged = []
for domain, url in SOURCES:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "inkplate-news/1"})
        with urllib.request.urlopen(req, timeout=12) as r:
            data = r.read()
        root = ET.fromstring(data)
    except Exception:
        continue
    taken = 0
    for item in root.iter():
        if local(item.tag) not in ("item", "entry"):
            continue
        title = None
        for c in item:
            if local(c.tag) == "title":
                title = clean(c.text or "")
                break
        if not title:
            continue
        merged.append({"source": domain, "title": title})
        taken += 1
        if taken >= PER_SOURCE_CAP:
            break

print(json.dumps(merged[:TOTAL_CAP], ensure_ascii=False))
PY
)

# Sanity: if we couldn't fetch anything, bail to fallback (which will
# itself likely be empty, producing an empty items list — honest).
if [[ -z "$candidates" || "$candidates" == "[]" ]]; then
  echo "fetch: zero candidates (all feeds unreachable)" >&2
  printf '%s' '{"count": 0, "items": []}' > "$STATE_FILE"
  exit 0
fi

# --- Read provider + model config (same file as poetic/astro) -----------
read_config() {
  CONFIG="$CONFIG" python3 - <<'PY'
import os, yaml
from pathlib import Path
cfg = yaml.safe_load(Path(os.environ["CONFIG"]).read_text()) or {}
print(cfg.get("provider", ""))
print(cfg.get("model", ""))
PY
}
mapfile -t _cfg < <(read_config)
PROVIDER="${_cfg[0]:-}"
MODEL="${_cfg[1]:-}"

# --- Build the LLM request body -----------------------------------------
# Candidates are numbered and labelled with source. Claude's job: pick 3,
# rewrite titles to fit within the zone budget, emit as compact JSON.
build_body() {
  CANDIDATES="$candidates" MODEL="$1" PROVIDER="$2" python3 - <<'PY'
import json, os
cands = json.loads(os.environ["CANDIDATES"])
model = os.environ["MODEL"]
provider = os.environ["PROVIDER"]

numbered = "\n".join(f"{i+1}. [{c['source']}] {c['title']}" for i, c in enumerate(cands))

sys_prompt = (
    "You are a curator for an ambient kitchen display. Pick the 3 most "
    "interesting-at-a-glance items from the numbered candidates and return "
    "them as strict JSON.\n\n"
    "Rules:\n"
    "- No politics, no breaking news, no celebrity gossip.\n"
    "- Prefer: science, design, craft, history, curiosities, essays, "
    "unusual discoveries, things with a twist.\n"
    "- Each title must read as a standalone one-liner: ≤56 characters, "
    "prose-style, no clickbait ellipses, no code fences.\n"
    "- Do not include source attribution — the display shows titles only.\n\n"
    "Output must be exactly this JSON shape, no preamble or code fence:\n"
    "{\"items\":[{\"title\":\"...\"},"
    "{\"title\":\"...\"},"
    "{\"title\":\"...\"}]}"
)

user_msg = f"Candidates:\n{numbered}"

if provider == "claude":
    body = {
        "model": model,
        "max_tokens": 400,
        "system": [{"type": "text", "text": sys_prompt, "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": user_msg}],
    }
else:
    body = {"model": model, "prompt": sys_prompt + "\n\n" + user_msg, "stream": False}
print(json.dumps(body, ensure_ascii=False))
PY
}

# Extract + validate the API response in one Python call. Outputs the
# final state-file JSON on stdout on success, exits non-zero on any
# failure (API shape, JSON parse, budget). The Python code comes in via
# `python3 -c "$script"` rather than `python3 - <<<heredoc`, because the
# heredoc would replace stdin and mask the piped payload from the caller.
extract_and_validate() {
  local py_script
  py_script=$(cat <<'PY'
import json, os, sys

provider = os.environ["PROVIDER"]

try:
    resp = json.loads(sys.stdin.read())
except Exception as e:
    print(f"extract: response not JSON: {e}", file=sys.stderr); sys.exit(1)

try:
    if provider == "claude":
        raw = resp["content"][0]["text"]
    else:
        raw = resp["response"]
except Exception as e:
    print(f"extract: response shape unexpected: {e}", file=sys.stderr); sys.exit(1)

raw = (raw or "").strip()
# Extract the first top-level JSON object by brace bounds. Robust against
# ``` code fences, preamble text, or trailing commentary the LLM sometimes
# adds despite the "no preamble" instruction.
i, j = raw.find("{"), raw.rfind("}")
if i < 0 or j <= i:
    print(f"validate: no braces found in {len(raw)} chars: {raw[:60]!r}", file=sys.stderr); sys.exit(1)
inner = raw[i:j+1]
try:
    d = json.loads(inner)
except Exception as e:
    print(f"validate: json parse failed: {e}", file=sys.stderr); sys.exit(1)

items = d.get("items") if isinstance(d, dict) else None
if not isinstance(items, list) or len(items) != 3:
    print(f"validate: items not a 3-list: {items!r}", file=sys.stderr); sys.exit(1)

out = []
for it in items:
    if not isinstance(it, dict):
        sys.exit(1)
    t = str(it.get("title", "")).strip()
    if not t or len(t) > 56:
        print(f"validate: budget fail t={len(t)} title={t!r}", file=sys.stderr); sys.exit(1)
    out.append({"title": t})

print(json.dumps({"count": len(out), "items": out}, ensure_ascii=False))
PY
)
  PROVIDER="$1" python3 -c "$py_script"
}

generate_claude() {
  local key="${ANTHROPIC_API_KEY:-}"
  [[ -z "$key" ]] && return 1
  local body resp status payload
  body=$(build_body "${MODEL:-claude-haiku-4-5-20251001}" "claude")
  resp=$(curl -sS -w $'\n__HTTP_STATUS__%{http_code}' https://api.anthropic.com/v1/messages \
    -H "x-api-key: $key" \
    -H "anthropic-version: 2023-06-01" \
    -H "content-type: application/json" \
    -d "$body") || return 1
  status="${resp##*__HTTP_STATUS__}"
  payload="${resp%$'\n__HTTP_STATUS__'*}"
  [[ "$status" == "200" ]] || { echo "generate_claude: http $status: $(printf '%s' "$payload" | head -c 200)" >&2; return 1; }
  printf '%s' "$payload" | extract_and_validate "claude"
}

generate_ollama() {
  local host="${OLLAMA_HOST:-http://localhost:11434}"
  local body
  body=$(build_body "${MODEL:-llama3.2}" "ollama")
  local resp
  resp=$(curl -fsS "$host/api/generate" -d "$body") || return 1
  printf '%s' "$resp" | extract_and_validate "ollama"
}

validated=""
case "$PROVIDER" in
  claude) validated=$(generate_claude || true) ;;
  ollama) validated=$(generate_ollama || true) ;;
  *)      validated="" ;;
esac

if [[ -n "$validated" ]]; then
  printf '%s' "$validated" > "$STATE_FILE"
  echo "wrote (llm): $(printf '%s' "$validated" | head -c 200)..."
  exit 0
fi
echo "llm unavailable or output rejected; falling back" >&2

# --- Fallback: first 3 Kottke items, title trimmed to 56 chars ----------
fallback=$(CANDIDATES="$candidates" python3 - <<'PY'
import json, os
cands = json.loads(os.environ["CANDIDATES"])
picks = [c for c in cands if c["source"] == "kottke.org"][:3]
def trim(s, n=56):
    s = s.strip().rstrip("…")
    if len(s) <= n:
        return s
    s = s[:n]
    sp = s.rfind(" ")
    if sp >= 32:
        s = s[:sp]
    return s.rstrip(".,;: -")
out = [{"title": trim(p["title"])} for p in picks]
print(json.dumps({"count": len(out), "items": out}, ensure_ascii=False))
PY
)
printf '%s' "$fallback" > "$STATE_FILE"
echo "wrote (fallback): $fallback"

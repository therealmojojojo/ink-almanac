#!/usr/bin/env bash
# Generate the single deep-dive entry rendered in the Smart pill — the lower-
# right zone of the Summary face. The pill is a structured word/meaning study
# of one word drawn from the day's text companion (the small text on the
# bottom-left of the same face). 400-500 chars. No history, no feeds.
#
# Pipeline:
#   1. Pull today's pairing companion from renderer/inputs/pairing.json (HTTP,
#      LAN). The companion's body, poet, title, and source language are the
#      input.
#   2. Ask Claude to (a) pick one word that appears in the companion (or its
#      original-language root if translated), (b) write a 400-500-char gloss
#      that unpacks etymology, source-language root, and how the word works
#      in this specific passage.
#
# Voice: warm, confident, plain English. Museum wall label by someone who
# loves their subject. The gloss should make re-reading the companion richer.
#
# Output (publish_inputs.yaml consumes this shape — count 0 or 1 only):
#   { "count": 1, "items": [{"body": "..."}] }
#
# Layout budget (must stay in sync with renderer/src/zones.ts news_body
# 34 cols × 11 lines and the Smart pill's measured visual fit at the 25u
# size floor):
#   target 320-360 chars; 380 hard cap enforced by trim_to_fit.
#
# Fallback: empty items list when the LLM is unavailable or pairing.json is
# unreachable — the Smart pill shows its placeholder-dash state rather than
# leaking content.

set -euo pipefail

BASE="/config/custom/inkplate"
CONFIG="$BASE/config/poetic_weather_line.yaml"
SECRETS_FILE="$BASE/secrets.yaml"
STATE_DIR="$BASE/state"
STATE_FILE="$STATE_DIR/curated_news.json"
RENDERER_URL="${INKPLATE_RENDERER_URL:-http://${RENDERER_HOST}:8575}"
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

DATE_ISO=$(date +%Y-%m-%d)
echo "date=$DATE_ISO" >&2

# --- Pull today's companion text (the source for the word) --------------
companion_json=$(curl -fsS --max-time 8 "$RENDERER_URL/inputs/pairing.json" 2>/dev/null || echo "{}")
companion=$(printf '%s' "$companion_json" | python3 -c "
import sys, json
try: d = json.loads(sys.stdin.read())
except Exception: d = {}
c = (d.get('gallery', {}) or {}).get('companion', {}) or {}
body = (c.get('body') or '').strip()
body_ja = (c.get('body_ja') or '').strip()
poet = (c.get('poet') or '').strip()
title = (c.get('title') or '').strip()
form = (c.get('form') or '').strip()
print(json.dumps({'body': body, 'body_ja': body_ja, 'poet': poet,
                  'title': title, 'form': form}, ensure_ascii=False))
" 2>/dev/null || echo "{}")

# Bail if we have no companion text — without it the pill has nothing to
# bind to. Better to render the placeholder dash than to invent a gloss.
has_companion=$(printf '%s' "$companion" | python3 -c "
import sys, json
try: print('1' if (json.loads(sys.stdin.read()).get('body') or '').strip() else '0')
except Exception: print('0')
" 2>/dev/null || echo "0")
if [[ "$has_companion" != "1" ]]; then
  printf '%s' '{"count": 0, "items": []}' > "$STATE_FILE"
  echo "no companion in pairing.json; wrote empty fallback" >&2
  exit 0
fi

# --- Read provider + model config ---------------------------------------
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
build_body() {
  COMPANION="$companion" MODEL="$1" PROVIDER="$2" python3 - <<'PY'
import json, os

try: companion = json.loads(os.environ["COMPANION"] or "{}")
except Exception: companion = {}
model = os.environ["MODEL"]
provider = os.environ["PROVIDER"]

attrib = companion.get("poet", "")
if companion.get("title"):
    attrib += f', "{companion["title"]}"'
form = companion.get("form") or ""
ja_block = ""
if companion.get("body_ja"):
    ja_block = f'\nOriginal-language version (where applicable):\n{companion["body_ja"]}\n'

companion_block = (
    "TODAY'S COMPANION TEXT (rendered next to the Smart pill on the "
    "same face — the reader sees both at a glance):\n\n"
    f'{companion["body"]}\n'
    f'  — {attrib}\n'
    f'  form: {form}\n'
    f'{ja_block}'
)

shared = (
    "You write the Smart pill: a single deep-dive entry on one word drawn "
    "from the companion text the reader sees on the left side of the same "
    "panel. The pill should make re-reading the companion richer — a "
    "well-read friend leaning over to point at one word.\n\n"
    "Layout constraint (exact): the body renders into a column ~437u "
    "wide, ~360u tall, in a 25u proportional sans-serif at 1.3 line-"
    "height. That fits ~11 lines × ~34 chars ≈ 370 characters of prose. "
    "Target 320-360 chars. A 380-char hard cap is enforced; going over "
    "gets trimmed to the last clean sentence boundary.\n\n"
    "Word choice rules:\n"
    "- Pick ONE word that appears in the companion text (or, for "
    "translations like classical aphorisms or haiku, the source-language "
    "root word — *paideia* for Aristotle's 'educated mind,' *kareno* for "
    "Bashō's 'withered fields,' *vitium* for Syrus's 'fault').\n"
    "- Prefer words whose etymology, polysemy, or original-language sense "
    "is non-obvious to a curious adult reader. Surface what translation or "
    "common usage flattens.\n"
    "- For visual companions (no body text — rare today), draw the word "
    "from the artist, title, or subject metadata.\n\n"
    "Structure of the gloss (in this order):\n"
    "1. The word in asterisks, language/part-of-speech in parentheses, "
    "em-dash, then the working sense: '*Paideia* (Greek, n.) — what "
    "Aristotle means by educated.'\n"
    "2. Etymology and/or original-language nuance — what the word "
    "literally meant; what its parts mean; what English translation "
    "loses or shifts. Concrete details: roots, cognates, the older "
    "sense.\n"
    "3. How the word works in *this specific passage* — why this poet/"
    "thinker reaches for it; what the line means once you carry the full "
    "weight of the word back into it.\n"
    "4. End on a fact or image, not a moral. No 'reminds us that,' no "
    "'a lesson in,' no 'we can learn,' no closing reflection.\n\n"
    "Voice: plain, warm, confident English; museum wall label by someone "
    "who loves their subject. Concrete over abstract. No jargon, no essay "
    "voice, no showing-off.\n\n"
    "Exclusions: no politics, no harm, no sermon. The word is the subject; "
    "the companion is the occasion.\n\n"
    "Output exactly this JSON, nothing else:\n"
    '{"items":[{"body":"..."}]}'
)

user_msg = companion_block + (
    "\nWrite the Smart pill entry for today's companion. 320-360 "
    "characters. One word, properly unpacked."
)

if provider == "claude":
    body = {
        "model": model,
        "max_tokens": 900,
        "system": [{"type": "text", "text": shared, "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": user_msg}],
    }
else:
    body = {"model": model, "prompt": shared + "\n\n" + user_msg, "stream": False}
print(json.dumps(body, ensure_ascii=False))
PY
}

# --- Extract + validate + trim (single Python process) ------------------
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
    raw = resp["content"][0]["text"] if provider == "claude" else resp["response"]
except Exception as e:
    print(f"extract: response shape unexpected: {e}", file=sys.stderr); sys.exit(1)

raw = (raw or "").strip()
i, j = raw.find("{"), raw.rfind("}")
if i < 0 or j <= i:
    print(f"validate: no braces in {len(raw)} chars: {raw[:60]!r}", file=sys.stderr); sys.exit(1)
try:
    d = json.loads(raw[i:j+1])
except Exception as e:
    print(f"validate: json parse failed: {e}", file=sys.stderr); sys.exit(1)

items = d.get("items") if isinstance(d, dict) else None
if not isinstance(items, list) or len(items) != 1:
    print(f"validate: items not a 1-list: {items!r}", file=sys.stderr); sys.exit(1)

def trim_to_fit(s, target=380):
    s = s.strip()
    if len(s) <= target:
        return s
    ends = [k+1 for k in range(len(s)) if s[k] in ".!?" and (k+1 == len(s) or s[k+1] == " ")]
    best = 0
    for e in ends:
        if e <= target and e > best:
            best = e
    if best >= 220:
        return s[:best].strip()
    cut = s[:target]
    sp = cut.rfind(" ")
    if sp > target * 0.7:
        cut = cut[:sp]
    return cut.rstrip(".,;:—-") + "…"

it = items[0]
if not isinstance(it, dict):
    sys.exit(1)
b = str(it.get("body") or "").strip()
if not b:
    print("validate: empty body", file=sys.stderr); sys.exit(1)
if len(b) > 600:
    print(f"validate: body runaway len={len(b)}: {b[:120]!r}…", file=sys.stderr); sys.exit(1)
if len(b) < 200:
    print(f"validate: body too short for a deep-dive len={len(b)}: {b[:120]!r}", file=sys.stderr); sys.exit(1)
out = [{"body": trim_to_fit(b, target=380)}]

print(json.dumps({"count": 1, "items": out}, ensure_ascii=False))
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

printf '%s' '{"count": 0, "items": []}' > "$STATE_FILE"
echo "llm unavailable or output rejected; wrote empty fallback" >&2

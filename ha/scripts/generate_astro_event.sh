#!/usr/bin/env bash
# Generate a ≤40-char line describing tonight's most notable naked-eye
# astronomy observation from the operator's coordinates and write it to
# /config/custom/inkplate/state/astro_event.txt.
#
# Usage: generate_astro_event.sh "<moon_phase>" "<lat>" "<lon>" "<date>"
#
# Provider/model mirrors the poetic-weather-line generator. On any failure
# (API error, schema violation, length > 40), falls back to a simple moon
# line derived from the passed-in phase so the Weather face's TONIGHT block
# always has something to show.
#
# This replaces the earlier in-the-sky.org scraper (fetch_astro_event.sh),
# which broke when the site's DOM changed and returned "unknown" for every
# poll.

set -euo pipefail

MOON_PHASE="${1:-}"
LAT="${2:-}"
LON="${3:-}"
DATE_ISO="${4:-$(date -u +%Y-%m-%d)}"

BASE="/config/custom/inkplate"
CONFIG="$BASE/config/poetic_weather_line.yaml"
SECRETS_FILE="$BASE/secrets.yaml"
STATE_DIR="$BASE/state"
STATE_FILE="$STATE_DIR/astro_event.txt"
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

# Hand-drawn fallback derived from the moon phase alone. Always produces
# something renderable. Keep ≤ 40 chars.
moon_fallback() {
  case "${MOON_PHASE}" in
    new_moon|new)             echo "new moon, dark skies tonight" ;;
    waxing_crescent)          echo "waxing crescent moon, sets early" ;;
    first_quarter)            echo "first-quarter moon tonight" ;;
    waxing_gibbous)           echo "waxing gibbous, bright moon late" ;;
    full_moon|full)           echo "full moon tonight" ;;
    waning_gibbous)           echo "waning gibbous, moon rises late" ;;
    last_quarter|third_quarter) echo "last-quarter moon, rises midnight" ;;
    waning_crescent)          echo "waning crescent, moon rises near dawn" ;;
    *)                        echo "" ;;
  esac
}

validate() {
  local py_script
  py_script=$(cat <<'PY'
import re, sys
s = sys.stdin.read().strip()
# Strip surrounding quotes if the model added them despite the rule.
if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
    s = s[1:-1].strip()
allowed = re.compile(r"^[A-Za-z0-9 ,.:;!\-'’°°–—]+$")
if len(s) == 0 or len(s) > 40 or not allowed.match(s):
    sys.exit(1)
sys.stdout.write(s)
PY
)
  python3 -c "$py_script"
}

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

build_body() {
  MOON_PHASE="$MOON_PHASE" LAT="$LAT" LON="$LON" DATE_ISO="$DATE_ISO" \
  MODEL="$1" PROVIDER="$2" python3 - <<'PY'
import json, os
phase = os.environ["MOON_PHASE"].replace("_", " ")
lat = os.environ["LAT"]; lon = os.environ["LON"]
date = os.environ["DATE_ISO"]
model = os.environ["MODEL"]
provider = os.environ["PROVIDER"]

sys_prompt = (
    "You are an astronomy editor. Given a date, coordinates, and moon phase, "
    "return a single lowercase line (max 40 characters, ASCII + basic "
    "punctuation only) describing the most notable naked-eye observation "
    "for that night from that location.\n\n"
    "Priority of events: eclipse > meteor-shower peak > ISS visible pass "
    "after dark > naked-eye planetary conjunction > bright planet visible "
    "at dusk > notable moon event > seasonal constellation.\n\n"
    "Examples: 'mars and jupiter close in taurus.' · 'lyrid meteors, few "
    "per hour after midnight.' · 'waxing moon sets at 02:14.' · 'orion "
    "setting in the west at dusk.' Do not add quotes, emoji, or markdown. "
    "Return only the line."
)
user_msg = (
    f"Date: {date}. Location: lat {lat}, lon {lon}. "
    f"Current moon phase: {phase}."
)

if provider == "claude":
    body = {
        "model": model,
        "max_tokens": 80,
        "system": [{"type": "text", "text": sys_prompt, "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": user_msg}],
    }
else:
    body = {"model": model, "prompt": sys_prompt + "\n\n" + user_msg, "stream": False}
print(json.dumps(body, ensure_ascii=False))
PY
}

extract_text() {
  local py_script
  py_script=$(cat <<'PY'
import json, os, sys
d = json.loads(sys.stdin.read())
provider = os.environ["PROVIDER"]
if provider == "claude":
    print(d["content"][0]["text"])
else:
    print(d["response"])
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
  printf '%s' "$payload" | extract_text "claude"
}

generate_ollama() {
  local host="${OLLAMA_HOST:-http://localhost:11434}"
  local body
  body=$(build_body "${MODEL:-llama3.2}" "ollama")
  local resp
  resp=$(curl -fsS "$host/api/generate" -d "$body") || return 1
  printf '%s' "$resp" | extract_text "ollama"
}

raw=""
case "$PROVIDER" in
  claude) raw=$(generate_claude || true) ;;
  ollama) raw=$(generate_ollama || true) ;;
  *)      raw="" ;;
esac

if [[ -n "$raw" ]]; then
  if validated=$(printf '%s' "$raw" | validate); then
    printf '%s' "$validated" > "$STATE_FILE"
    echo "wrote (llm): $validated"
    exit 0
  fi
fi

fb=$(moon_fallback)
printf '%s' "$fb" > "$STATE_FILE"
echo "wrote (fallback): $fb"

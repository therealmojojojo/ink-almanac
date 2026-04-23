#!/usr/bin/env bash
# Generate a ≤32-char Night-mode weather line and write it to
# /config/custom/inkplate/state/poetic_weather.txt.
# Usage: generate_poetic_weather_line.sh "<condition_summary>" "<temp_c>" "<wind>" "<bucket>"
#
# Provider/model comes from ha/config/poetic_weather_line.yaml. On any failure
# (API error, schema validation, charset violation, length violation), falls back
# to a random line from the operator-curated pool in night_fallback_lines.yaml.
#
# All external inputs (SUMMARY, TEMP_C, WIND, LLM response) travel via env vars
# or stdin; none are interpolated into a shell heredoc or JSON literal.
set -euo pipefail

SUMMARY="${1:-}"
TEMP_C="${2:-}"
WIND="${3:-}"
BUCKET="${4:-cloudy}"

BASE="/config/custom/inkplate"
CONFIG="$BASE/config/poetic_weather_line.yaml"
FALLBACK_FILE="$BASE/config/night_fallback_lines.yaml"
SECRETS_FILE="$BASE/secrets.yaml"
STATE_DIR="$BASE/state"
STATE_FILE="$STATE_DIR/poetic_weather.txt"
mkdir -p "$STATE_DIR"

# HA's `shell_command:` integration doesn't forward environment variables and
# can't inject !secret into the invocation string. If the key isn't already in
# the env (e.g. when running locally for testing), read it from the deployed
# project-scoped secrets.yaml.
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

pick_fallback() {
  FALLBACK_FILE="$FALLBACK_FILE" BUCKET="$BUCKET" python3 - <<'PY'
import os, random, yaml
from pathlib import Path
data = yaml.safe_load(Path(os.environ["FALLBACK_FILE"]).read_text()) or {}
bucket = os.environ.get("BUCKET", "cloudy")
lines = data.get(bucket) or data.get("cloudy") or ["Quiet night."]
print(random.choice(lines))
PY
}

# Reads candidate from stdin, echoes the cleaned line on success or exits 1.
validate() {
  local py_script
  py_script=$(cat <<'PY'
import re, sys
s = sys.stdin.read().strip()
allowed = re.compile(r"^[A-Za-zĂÂÎȘȚăâîșț0-9 ,.:;!\-'’\"]+$")
if len(s) == 0 or len(s) > 32 or not allowed.match(s):
    sys.exit(1)
sys.stdout.write(s)
PY
)
  python3 -c "$py_script"
}

# Read provider + model from config via yaml (no fragile awk on user-edited file).
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

# Build JSON with Python (stdlib) so we don't require jq, which isn't in the
# HA Core container where shell_command runs. Python's json.dumps handles
# Romanian diacritics, quotes, and backslashes correctly without shell escaping.
build_json_body() {
  SUMMARY="$SUMMARY" TEMP_C="$TEMP_C" WIND="$WIND" MODEL="$1" PROVIDER="$2" \
    python3 - <<'PY'
import json, os
summary = os.environ["SUMMARY"]
temp_c = os.environ["TEMP_C"]
wind = os.environ["WIND"]
model = os.environ["MODEL"]
provider = os.environ["PROVIDER"]
user_msg = f"Current: {summary}, {temp_c}°C, {wind}"
if provider == "claude":
    sys_prompt = (
        'Write one short evocative line about the night and current weather. '
        'Rules: ≤32 characters. ASCII plus Romanian diacritics only. '
        'No emoji, no markdown, no quotes. End with a period or no punctuation. '
        'Example: "Rain on the windows."'
    )
    body = {
        "model": model,
        "max_tokens": 60,
        "system": [{"type": "text", "text": sys_prompt, "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": user_msg}],
    }
else:
    prompt = (
        f"One short line (≤32 chars) evocative of night + weather. "
        f"ASCII+RO-diacritics only. No emoji. Weather: {summary}, {temp_c}°C, {wind}"
    )
    body = {"model": model, "prompt": prompt, "stream": False}
print(json.dumps(body, ensure_ascii=False))
PY
}

extract_text() {
  # Pass the script via -c so python's stdin stays attached to the pipe from
  # the caller; using `python3 -` + heredoc consumes stdin for the script and
  # leaves sys.stdin.read() empty.
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
  body=$(build_json_body "${MODEL:-claude-haiku-4-5-20251001}" "claude")

  # Capture response + HTTP status; avoid -f so we see 4xx/5xx payloads.
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
  body=$(build_json_body "${MODEL:-llama3.2}" "ollama")

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

fb=$(pick_fallback)
printf '%s' "$fb" > "$STATE_FILE"
echo "wrote (fallback): $fb"

#!/usr/bin/env bash
# Pick a random line from the Night-mode poetic-weather pool and write it to
# /config/custom/inkplate/state/poetic_weather.txt.
#
# Invocation (the shell_command in ha/integrations/shell_commands.yaml):
#   generate_poetic_weather_line.sh "<bucket>"
#
# Legacy invocations (4 positional args: summary, temp_c, wind, bucket) are
# still accepted — the first three are ignored. This keeps the script
# transition-safe if a stale automation calls it during a partial deploy.
#
# Pool file: /config/custom/inkplate/config/night_poetic_pool.yaml.
# Bucket-not-in-pool falls back to `cloudy`, then to the hardcoded
# "Quiet night." safety string. Picked line is enforced to match the
# strict ASCII subset and the ≤ 40-grapheme length budget; entries that
# fail either check are skipped, then we fall through to the safety
# string if all candidates fail.
#
# Replaces the earlier LLM-then-fallback script (which called Claude Haiku
# hourly). See `add-night-text-clock-partials` for context.
set -euo pipefail

# The bucket is the last positional arg so legacy 4-arg invocations
# (summary, temp_c, wind, bucket) keep working without changes to the
# shell_command spec during a partial deploy.
BUCKET="${@: -1}"
[[ -z "$BUCKET" ]] && BUCKET="cloudy"

BASE="/config/custom/inkplate"
POOL_FILE="$BASE/config/night_poetic_pool.yaml"
STATE_DIR="$BASE/state"
STATE_FILE="$STATE_DIR/poetic_weather.txt"
mkdir -p "$STATE_DIR"

LINE=$(POOL="$POOL_FILE" BUCKET="$BUCKET" python3 - <<'PY'
import os, random, re, sys
import yaml

try:
    pool = yaml.safe_load(open(os.environ["POOL"])) or {}
except FileNotFoundError:
    print("Quiet night.")
    sys.exit(0)

bucket = os.environ.get("BUCKET", "cloudy")
candidates = pool.get(bucket) or pool.get("cloudy") or []
random.shuffle(list(candidates))  # in-place shuffle of a fresh list copy

allowed = re.compile(r"^[A-Za-z0-9 ,.:;!\-'\"]+$")
for line in candidates:
    if not isinstance(line, str): continue
    if len(line) > 40 or not allowed.match(line): continue
    print(line)
    sys.exit(0)
print("Quiet night.")
PY
)

printf '%s' "$LINE" > "$STATE_FILE"
echo "wrote (pool): $LINE"

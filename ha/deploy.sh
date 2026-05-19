#!/usr/bin/env bash
# Deploy ha/ → HAOS VM over SSH (Advanced SSH & Web Terminal add-on).
# Intentionally strict: any failure aborts. No partial deploys.
set -euo pipefail

# --- Configuration (override via env) ---
HA_HOST="${HA_HOST:-homeassistant.local}"
HA_SSH_PORT="${HA_SSH_PORT:-2222}"
HA_USER="${HA_USER:-root}"
HA_SSH_KEY="${HA_SSH_KEY:-$HOME/.ssh/id_ed25519}"

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
HA_DIR="$REPO_DIR/ha"
REMOTE_BASE="/config/custom/inkplate"

# --- Pre-flight ---
if [[ ! -f "$HA_SSH_KEY" ]]; then
  echo "ERROR: SSH key not found at $HA_SSH_KEY" >&2
  echo "Generate one (ssh-keygen -t ed25519) and add its public half to the" >&2
  echo "HAOS 'Advanced SSH & Web Terminal' add-on under 'Authorized keys'." >&2
  exit 2
fi

SSH_OPTS=(-i "$HA_SSH_KEY" -p "$HA_SSH_PORT" -o StrictHostKeyChecking=accept-new)
SSH_TARGET="$HA_USER@$HA_HOST"

# Wrapper that rsync invokes as its transport, so key paths with spaces
# or extra options are passed as discrete argv entries rather than joined
# through IFS expansion.
SSH_WRAPPER="$(mktemp -t inkplate-ha-ssh.XXXXXX)"
trap 'rm -f "$SSH_WRAPPER"' EXIT
cat > "$SSH_WRAPPER" <<EOF
#!/usr/bin/env bash
exec ssh -i "$HA_SSH_KEY" -p "$HA_SSH_PORT" -o StrictHostKeyChecking=accept-new "\$@"
EOF
chmod +x "$SSH_WRAPPER"

echo "→ Verifying SSH connectivity to $SSH_TARGET:$HA_SSH_PORT"
if ! ssh "${SSH_OPTS[@]}" -o ConnectTimeout=5 "$SSH_TARGET" "true"; then
  echo "ERROR: SSH connection failed. Check:" >&2
  echo "  1. HAOS VM is running and reachable at $HA_HOST" >&2
  echo "  2. 'Advanced SSH & Web Terminal' add-on is started on port $HA_SSH_PORT" >&2
  echo "  3. Public key for $HA_SSH_KEY is in the add-on's Authorized keys list" >&2
  exit 3
fi

# --- Deploy ---
# The HA SSH add-on doesn't include rsync, so we stream a tarball over ssh and
# extract it on the VM. `--delete` semantics are reproduced by wiping the
# project subtree (not /config/secrets.yaml) on the remote before extracting.
#
# Secrets go to /config/custom/inkplate/secrets.yaml. HA's !secret tag walks
# upward from the YAML file being parsed, so every ha/ fragment resolves its
# !secret references against this file automatically. /config/secrets.yaml is
# never touched by this script.
echo "→ Preparing $REMOTE_BASE on the VM (preserving state/)"
# state/ holds LLM-generated lines and other runtime artifacts that the
# deployer must not wipe — the tar below excludes state/, but a plain
# `rm -rf $REMOTE_BASE` would delete it before the new tree is extracted.
# Wipe everything *except* state/ so the daemon-generated files survive a
# redeploy. (Using `find` avoids shell-glob ordering surprises.)
ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "mkdir -p $REMOTE_BASE/state && find $REMOTE_BASE -mindepth 1 -maxdepth 1 ! -name state -exec rm -rf {} +"

# --- Render templates ---
# Tracked YAML/scripts use ${VAR} placeholders for operator-specific values
# (LAN IPs, weather location names + entity-id slugs, repo path, operator
# username). Real values live in local-overrides.env (gitignored). We
# render into a temporary work-dir and tar from there, so the HA VM
# receives substituted values while the tracked tree stays generic.
OVERRIDES="$REPO_DIR/local-overrides.env"
if [[ ! -f "$OVERRIDES" ]]; then
  echo "ERROR: $OVERRIDES not found. Copy local-overrides.env.example and fill in." >&2
  exit 4
fi
# shellcheck disable=SC1090
set -a; source "$OVERRIDES"; set +a

# Variables we substitute (intentionally explicit — envsubst with no arg
# would expand every $VAR in the YAML, which collides with HA's own
# template syntax in some places).
SUBST_VARS='$RENDERER_HOST $HA_HOST $Z2M_HOST $PLACE_A_NAME $PLACE_A_SLUG $PLACE_B_NAME $PLACE_B_SLUG $INKPLATE_REPO $OPERATOR_USER'

WORK="$(mktemp -d -t inkplate-ha.XXXXXX)"
# shellcheck disable=SC2064
trap "rm -rf '$WORK' '$SSH_WRAPPER'" EXIT

# Mirror ha/ to the work dir, then envsubst every text fragment in place.
# Excludes match the tar excludes below.
(
  cd "$HA_DIR" && tar --exclude='secrets.yaml' --exclude='secrets.yaml.example' \
    --exclude='deploy.sh' --exclude='README.md' --exclude='.gitkeep' \
    --exclude='state' -cf - . | tar -C "$WORK" -xf -
)
find "$WORK" -type f \( -name '*.yaml' -o -name '*.yml' -o -name '*.sh' -o -name '*.md' -o -name '*.json' \) -print0 \
  | while IFS= read -r -d '' f; do
      tmp="$f.subst.$$"
      # Preserve the original mode across the envsubst rewrite. The `>`
      # creates $tmp with the default umask; `mv` then clobbers the
      # original's mode. Without this, all *.sh deployed to HA lose
      # their exec bit and `./script.sh` invocations from shell_commands
      # fail with return-code 126 — silently in HA's logs, except as a
      # one-line ERROR. Hit us across publish_today_pairing,
      # generate_poetic_weather_line, fetch_sonos_art, etc. for days.
      mode="$(stat -f %A "$f" 2>/dev/null || stat -c %a "$f")"
      envsubst "$SUBST_VARS" < "$f" > "$tmp" && mv "$tmp" "$f" && chmod "$mode" "$f"
    done

echo "→ Streaming rendered ha/ fragments → $REMOTE_BASE"
tar -C "$WORK" -cf - . | ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "tar -C $REMOTE_BASE -xf -"

if [[ -f "$HA_DIR/secrets.yaml" ]]; then
  echo "→ Streaming secrets.yaml → $REMOTE_BASE/secrets.yaml (project-scoped)"
  scp -i "$HA_SSH_KEY" -P "$HA_SSH_PORT" -o StrictHostKeyChecking=accept-new \
    "$HA_DIR/secrets.yaml" "$SSH_TARGET:$REMOTE_BASE/secrets.yaml" >/dev/null
else
  echo "WARN: $HA_DIR/secrets.yaml missing — skipping. Some sensors will fail to load."
fi

# --- Validate + restart ---
# `ha core reload` isn't a supervisor CLI verb; per-domain reloads exist but
# don't cover new entities introduced by package files. A validated restart is
# the reliable way to pick up this deploy in full.
echo "→ Validating config + restarting HA core"
ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "ha core check && ha core restart"

# --- Tail recent log ---
echo "→ Recent HA log (last 30 lines):"
ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "ha core logs | tail -n 30" || true

echo "✓ Deploy complete."

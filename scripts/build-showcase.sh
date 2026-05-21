#!/usr/bin/env bash
# Render the showcase variants used in README.md's "Faces" section.
#
# Output: renderer/test/__golden__/showcase/{summary,night,gallery-{text,landscape,portrait},nowplaying-{classical,rock}}.png
#
# Why this script exists separately from `npm test`: the canonical snapshot
# test exercises one fixture per face. The README needs multiple fixtures
# per face (gallery layouts, classical vs pop now-playing) and a real-day
# Summary render. This stand-alone harness:
#
#   • For Summary — curls the *prod* renderer on :8575 so the screenshot
#     reflects the live device's triplet (Dickinson + smart-pill etc.).
#     Run this when the live triplet is one you want to immortalise.
#   • For Gallery + Now-Playing — spins a *test* renderer on :8585 with a
#     temp staging dir so the prod renderer's inputs are never touched.
#
# The PD images and album-art thumbnails fetched here:
#   • Charles Marville — Rue de Constantine, Paris (1866). CC0 via Wikimedia.
#   • Dorothea Lange — Migrant Mother (FSA, 1936). PD via Wikimedia / LoC.
#   • Hiroshige — Moon Pine at Ueno (One Hundred Famous Views of Edo, 1857). PD.
#   • Górecki — Symphony No. 3 cover (1992 Nonesuch). Wikipedia fair-use.
#   • Bowie — "Heroes" cover (RCA, 1977). Wikipedia fair-use.
#
# Re-run whenever the gallery / now-playing / summary layouts change.

set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
STAGE="$(mktemp -d -t inkplate-showcase.XXXXXX)"
OUT="$REPO/renderer/test/__golden__/showcase"
PORT_TEST=8585
PORT_PROD=8575
PID_FILE="$STAGE/renderer.pid"

cleanup() {
  if [[ -f "$PID_FILE" ]]; then
    kill "$(cat "$PID_FILE")" 2>/dev/null || true
  fi
  rm -f "$REPO/renderer/inputs/showcase-"*.{jpg,png}
  rm -rf "$STAGE"
}
trap cleanup EXIT

mkdir -p "$OUT"

# Base fixtures (clock / device / weather / smart_pill) — unchanged.
cp "$REPO/renderer/test/fixtures/"{clock,device,weather,smart_pill}.json "$STAGE/"

# Fetch PD photos + album-cover thumbnails into renderer/inputs/ under
# non-colliding showcase-* names so the prod renderer's /inputs/<file>
# route can serve them without touching live HA-published files.
echo "Fetching showcase assets…"
curl -sf -o "$REPO/renderer/inputs/showcase-landscape.jpg" \
  "https://upload.wikimedia.org/wikipedia/commons/c/c1/Rue_de_Constantine%2C_Paris%2C_by_Charles_Marville.JPG"
curl -sf -o "$REPO/renderer/inputs/showcase-portrait.jpg" \
  "https://upload.wikimedia.org/wikipedia/commons/5/54/Lange-MigrantMother02.jpg"
curl -sf -o "$REPO/renderer/inputs/showcase-nocturne.jpg" \
  "https://upload.wikimedia.org/wikipedia/commons/f/fb/100_views_edo_089.jpg"
curl -sf -o "$REPO/renderer/inputs/showcase-art-classical.jpg" \
  "https://upload.wikimedia.org/wikipedia/en/8/86/Symphony_of_Sorrowful_Songs.jpg"
curl -sf -o "$REPO/renderer/inputs/showcase-art-rock.png" \
  "https://upload.wikimedia.org/wikipedia/en/7/7b/David_Bowie_-_Heroes.png"

# Per-variant pairing / sonos fixtures.
cat > "$STAGE/pairing-text.json" <<'JSON'
{"date":"2026-04-14","theme":"stillness","gallery":{"flavor":"text","text":{"form":"haiku","body":"an old silent pond\na frog leaps into water\nsplash, then silence","title":"Old pond","poet":"Bashō","dates":"1644–1694","language":"en"}},"night":{"fragment":"the night is long, the moon keeps watch"}}
JSON
cat > "$STAGE/pairing-landscape.json" <<'JSON'
{"date":"2026-04-14","theme":"city","gallery":{"flavor":"visual","visual":{"image_path":"/inputs/showcase-landscape.jpg","title":"Rue de Constantine","artist":"Marville","year":"1866","pixel_width":3812,"pixel_height":2828}}}
JSON
cat > "$STAGE/pairing-portrait.json" <<'JSON'
{"date":"2026-04-14","theme":"depression","gallery":{"flavor":"visual","visual":{"image_path":"/inputs/showcase-portrait.jpg","title":"Migrant Mother","artist":"Lange","year":"1936","pixel_width":6205,"pixel_height":8066}}}
JSON
cat > "$STAGE/pairing-night.json" <<'JSON'
{"date":"2026-04-14","theme":"stillness","gallery":{"flavor":"text","text":{"form":"haiku","body":"an old silent pond\na frog leaps into water\nsplash, then silence","title":"Old pond","poet":"Bashō","language":"en"}},"night":{"image_path":"/inputs/showcase-nocturne.jpg","title":"Moon Pine at Ueno","fragment":"HIROSHIGE · 1857"}}
JSON
cat > "$STAGE/sonos-classical.json" <<'JSON'
{"state":"playing","title":"Symphony No. 3","artist":"Henryk Górecki","album":"Symphony No. 3 (Symphony of Sorrowful Songs)","source":"spotify","art_url":"/inputs/showcase-art-classical.jpg","classical":true,"composer":"Henryk Górecki","work":"Symphony No. 3","movement":"I. Lento — Sostenuto tranquillo ma cantabile","performers":[{"name":"Dawn Upshaw","role":"Soprano"},{"name":"London Sinfonietta","role":"Orchestra"},{"name":"David Zinman","role":"Conductor"}],"first_release_year":"1992"}
JSON
cat > "$STAGE/sonos-rock.json" <<'JSON'
{"state":"playing","title":"Heroes","artist":"David Bowie","album":"\"Heroes\"","source":"spotify","art_url":"/inputs/showcase-art-rock.png","classical":false,"first_release_year":"1977"}
JSON
cp "$STAGE/sonos-classical.json" "$STAGE/sonos.json"  # default for gallery renders

# Boot the test renderer on $PORT_TEST, inputs pointed at the staging dir.
(
  cd "$REPO/renderer"
  RENDERER_PORT="$PORT_TEST" RENDERER_INPUTS_DIR="$STAGE" npm start \
    >"$STAGE/renderer.log" 2>&1 &
  echo $! > "$PID_FILE"
)
for _ in $(seq 1 60); do
  if [[ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT_TEST/healthz")" == "200" ]]; then
    break
  fi
  sleep 1
done

render() {
  local name="$1" face="$2" port="${3:-$PORT_TEST}"
  curl -sf -o "$OUT/$name.png" "http://127.0.0.1:$port/display/$face.png"
  printf '  %-26s %8d bytes\n' "$name.png" "$(wc -c < "$OUT/$name.png")"
}

echo "=== Summary (live, from prod renderer :$PORT_PROD) ==="
render "summary" summary "$PORT_PROD"

echo "=== Night ==="
cp "$STAGE/pairing-night.json" "$STAGE/pairing.json"
render "night" night

echo "=== Gallery variants ==="
for v in text landscape portrait; do
  cp "$STAGE/pairing-$v.json" "$STAGE/pairing.json"
  render "gallery-$v" gallery
done

echo "=== Now-Playing variants ==="
cp "$STAGE/sonos-classical.json" "$STAGE/sonos.json"
render "nowplaying-classical" now-playing
cp "$STAGE/sonos-rock.json" "$STAGE/sonos.json"
render "nowplaying-rock" now-playing

echo
echo "Done. Outputs:"
ls -la "$OUT"

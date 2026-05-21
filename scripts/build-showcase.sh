#!/usr/bin/env bash
# Render the showcase variants used in README.md's "Faces" section.
#
# Output: renderer/test/__golden__/showcase/{gallery-{text,landscape,square,portrait},nowplaying-{classical,rock},summary}.png
#
# Why this script exists separately from `npm test`: the canonical snapshot
# test exercises one fixture per face. The README needs multiple fixtures
# per face (4 gallery layouts, 2 now-playing flavors, a text-companion
# summary). Rather than fork the fixture set or expand the test surface,
# this is a stand-alone harness that spins up a *test* renderer on port
# 8585 (so it doesn't collide with the prod renderer on 8575) and drives
# it through a temp staging dir.
#
# Re-run whenever the gallery / now-playing / summary layouts change.

set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
STAGE="$(mktemp -d -t inkplate-showcase.XXXXXX)"
OUT="$REPO/renderer/test/__golden__/showcase"
PORT=8585
PID_FILE="$STAGE/renderer.pid"

cleanup() {
  if [[ -f "$PID_FILE" ]]; then
    kill "$(cat "$PID_FILE")" 2>/dev/null || true
  fi
  rm -f "$REPO/renderer/inputs/showcase-"*.jpg
  rm -rf "$STAGE"
}
trap cleanup EXIT

mkdir -p "$OUT"

# Stage base fixtures (clock / device / weather / smart_pill) — unchanged.
cp "$REPO/renderer/test/fixtures/"{clock,device,weather,smart_pill}.json "$STAGE/"

# Stage showcase images into renderer/inputs/ with non-colliding names so the
# prod renderer's /inputs/<file> route can serve them without clobbering any
# of the live HA-published files (clock.json, gallery.jpg, etc.).
cp "$REPO/corpus/images/whistler-rotherhithe.jpg"          "$REPO/renderer/inputs/showcase-landscape.jpg"
cp "$REPO/corpus/images/ma-yuan-scholar-by-waterfall.jpg"  "$REPO/renderer/inputs/showcase-square.jpg"
cp "$REPO/corpus/images/beardsley-peacock-skirt.jpg"       "$REPO/renderer/inputs/showcase-portrait.jpg"

# Write per-variant pairing / sonos fixtures into the staging dir.
cat > "$STAGE/pairing-text.json" <<'JSON'
{"date":"2026-04-14","theme":"stillness","gallery":{"flavor":"text","text":{"form":"haiku","body":"an old silent pond\na frog leaps into water\nsplash, then silence","title":"Old pond","poet":"Bashō","dates":"1644–1694","language":"en"}},"night":{"fragment":"the night is long, the moon keeps watch"}}
JSON
cat > "$STAGE/pairing-landscape.json" <<'JSON'
{"date":"2026-04-14","theme":"river","gallery":{"flavor":"visual","visual":{"image_path":"/inputs/showcase-landscape.jpg","title":"Rotherhithe","artist":"Whistler","year":"1860","pixel_width":3806,"pixel_height":2541}}}
JSON
cat > "$STAGE/pairing-square.json" <<'JSON'
{"date":"2026-04-14","theme":"stillness","gallery":{"flavor":"visual","visual":{"image_path":"/inputs/showcase-square.jpg","title":"Scholar by Waterfall","artist":"Ma Yuan","year":"ca. 1200","pixel_width":3407,"pixel_height":3000}}}
JSON
cat > "$STAGE/pairing-portrait.json" <<'JSON'
{"date":"2026-04-14","theme":"ornament","gallery":{"flavor":"visual","visual":{"image_path":"/inputs/showcase-portrait.jpg","title":"Peacock Skirt","artist":"Beardsley","year":"1893","pixel_width":1855,"pixel_height":2560}}}
JSON
cat > "$STAGE/pairing-summary.json" <<'JSON'
{"date":"2026-04-14","theme":"stillness","gallery":{"flavor":"visual","visual":{"image_path":"/inputs/showcase-landscape.jpg","title":"Rotherhithe","artist":"Whistler","year":"1860","pixel_width":3806,"pixel_height":2541},"companion":{"kind":"text","form":"haiku","body":"an old silent pond\na frog leaps into water\nsplash, then silence","poet":"Bashō","title":"Old pond","dates":"1644–1694","language":"en"}}}
JSON
cat > "$STAGE/sonos-classical.json" <<'JSON'
{"state":"playing","title":"Spiegel im Spiegel","artist":"Arvo Pärt","album":"Alina","source":"spotify","classical":true,"composer":"Arvo Pärt","work":"Spiegel im Spiegel","movement":"","performers":[{"name":"Vladimir Spivakov","role":"Violin"},{"name":"Sergej Bezrodny","role":"Piano"}],"first_release_year":"1999"}
JSON
cat > "$STAGE/sonos-rock.json" <<'JSON'
{"state":"playing","title":"Heroes","artist":"David Bowie","album":"\"Heroes\"","source":"spotify","classical":false,"first_release_year":"1977"}
JSON
# default sonos for the gallery / summary renders (idle, so no override leaks in)
cp "$STAGE/sonos-classical.json" "$STAGE/sonos.json"

# Boot the test renderer on $PORT, inputs pointed at the staging dir.
(
  cd "$REPO/renderer"
  RENDERER_PORT="$PORT" RENDERER_INPUTS_DIR="$STAGE" npm start \
    >"$STAGE/renderer.log" 2>&1 &
  echo $! > "$PID_FILE"
)

# Wait for it.
for _ in $(seq 1 60); do
  if [[ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/healthz")" == "200" ]]; then
    break
  fi
  sleep 1
done

render() {
  local name="$1" face="$2"
  curl -sf -o "$OUT/$name.png" "http://127.0.0.1:$PORT/display/$face.png"
  printf '  %-22s %8d bytes\n' "$name.png" "$(wc -c < "$OUT/$name.png")"
}

echo "=== Gallery variants ==="
for v in text landscape square portrait; do
  cp "$STAGE/pairing-$v.json" "$STAGE/pairing.json"
  render "gallery-$v" gallery
done

echo "=== Summary (text companion) ==="
cp "$STAGE/pairing-summary.json" "$STAGE/pairing.json"
render "summary" summary

echo "=== Now-Playing variants ==="
cp "$STAGE/sonos-classical.json" "$STAGE/sonos.json"
render "nowplaying-classical" now-playing
cp "$STAGE/sonos-rock.json" "$STAGE/sonos.json"
render "nowplaying-rock" now-playing

echo
echo "Done. Outputs:"
ls -la "$OUT"

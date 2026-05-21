#!/usr/bin/env bash
# Render the showcase variants used in README.md's "Faces" section.
#
# Output: renderer/test/__golden__/showcase/{summary,night,gallery-{text,landscape,portrait},nowplaying-{classical,rock}}.png
#
# Why this script exists separately from `npm test`: the canonical snapshot
# test exercises one fixture per face. The README needs multiple fixtures
# per face (gallery layouts, classical vs pop now-playing, a summary with a
# bound smart-pill demonstration). This stand-alone harness spins a *test*
# renderer on :8585 with a temp staging dir so the prod renderer on :8575
# (and the live device it serves) are never touched. The Summary fixture
# reads body + smart-pill from the operator's corpus sidecar at runtime
# (corpus/texts/marcus-aurelius-dye-of-thoughts.yaml) so the demo always
# shows the same content regardless of what today's published triplet is.
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
PID_FILE="$STAGE/renderer.pid"

cleanup() {
  # `npm start` spawns tsx as a grandchild that holds the port. Killing the
  # npm wrapper alone leaves the grandchild running. pkill -P kills the
  # whole subtree; the explicit lsof step is belt-and-braces in case the
  # renderer drifted from the wrapper's process tree.
  if [[ -f "$PID_FILE" ]]; then
    pkill -P "$(cat "$PID_FILE")" 2>/dev/null || true
    kill "$(cat "$PID_FILE")" 2>/dev/null || true
  fi
  local listener
  listener="$(lsof -ti :"$PORT_TEST" 2>/dev/null || true)"
  [[ -n "$listener" ]] && kill -9 $listener 2>/dev/null || true
  rm -f "$REPO/renderer/inputs/showcase-"*.{jpg,png}
  rm -rf "$STAGE"
}
trap cleanup EXIT

mkdir -p "$OUT"

# Base fixtures (clock / device / smart_pill) copied as-is; weather gets a
# nowcast block added so the Summary + Weather showcase faces demonstrate
# the immediate-forecast line (the test fixture omits it on purpose so the
# snapshot test exercises the absent-nowcast path).
cp "$REPO/renderer/test/fixtures/"{clock,device,smart_pill}.json "$STAGE/"
python3 - <<PY
import json, pathlib
src = pathlib.Path("$REPO/renderer/test/fixtures/weather.json")
w = json.loads(src.read_text())
nowcasts = [
  {"label": "CLEARING IN 21 MIN", "minutes_until_change": 21},
  {"label": "RAIN IN 40 MIN", "minutes_until_change": 40},
]
for i, loc in enumerate(w.get("locations", [])):
  if i < len(nowcasts):
    loc["nowcast"] = nowcasts[i]
pathlib.Path("$STAGE/weather.json").write_text(json.dumps(w, indent=2, ensure_ascii=False))
PY

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
  "https://upload.wikimedia.org/wikipedia/en/8/8e/Glenn_Gould_Goldberg_Variations_1981_cover.jpeg"
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
{"state":"playing","title":"Goldberg Variations","artist":"Glenn Gould","album":"Bach: The Goldberg Variations","source":"spotify","art_url":"/inputs/showcase-art-classical.jpg","classical":true,"composer":"Johann Sebastian Bach","work":"Goldberg Variations","movement":"Aria, BWV 988","performers":[{"name":"Glenn Gould","role":"Piano"}],"first_release_year":"1981"}
JSON
cat > "$STAGE/sonos-rock.json" <<'JSON'
{"state":"playing","title":"Heroes","artist":"David Bowie","album":"\"Heroes\"","source":"spotify","art_url":"/inputs/showcase-art-rock.png","classical":false,"first_release_year":"1977"}
JSON
cp "$STAGE/sonos-classical.json" "$STAGE/sonos.json"  # default for gallery renders

# Summary fixture — read the Marcus Aurelius "Dye of Thoughts" item from the
# operator's corpus to populate both the companion text and the smart pill.
# Doing it this way means we don't duplicate the operator's curator-written
# prose into the script; the body and the pill stay sourced from a single
# YAML sidecar. (Requires corpus/texts/marcus-aurelius-dye-of-thoughts.yaml
# to exist locally; the sidecars are gitignored so this script only works on
# the operator's machine, which is the design intent — the rendered PNGs
# are what ships in the repo.)
python3 - <<PY
import json, yaml, pathlib
src = pathlib.Path("$REPO/corpus/texts/marcus-aurelius-dye-of-thoughts.yaml")
d = yaml.safe_load(src.read_text())
body = (d.get("text_variants") or {}).get("en", "").rstrip("\n")
pill = ((d.get("smart_pill") or {}).get("body") or "").rstrip("\n")
pairing = {
  "date": "2026-04-14",
  "theme": d.get("themes", ["self-shaping"])[0],
  "gallery": {
    "flavor": "visual",
    "visual": {
      "image_path": "/inputs/showcase-landscape.jpg",
      "title": "Rue de Constantine", "artist": "Marville", "year": "1866",
      "pixel_width": 3812, "pixel_height": 2828,
    },
    "companion": {
      "kind": "text", "form": d.get("form", "aphorism"),
      "body": body, "poet": d.get("author", "Marcus Aurelius"),
      "title": d.get("title", ""), "language": "en",
    },
  },
}
pathlib.Path("$STAGE/pairing-summary.json").write_text(
  json.dumps(pairing, ensure_ascii=False, indent=2))
pathlib.Path("$STAGE/smart_pill.json").write_text(
  json.dumps({"body": pill}, ensure_ascii=False, indent=2))
PY

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

echo "=== Summary (test renderer, Marcus Aurelius fixture) ==="
cp "$STAGE/pairing-summary.json" "$STAGE/pairing.json"
render "summary" summary

echo "=== Weather ==="
render "weather" weather

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

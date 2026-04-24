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
    # Broad miscellany / science-curiosity / places
    ("kottke.org",       "https://feeds.kottke.org/main"),
    ("atlasobscura.com", "https://www.atlasobscura.com/feeds/latest"),
    ("aeon.co",          "https://aeon.co/feed.rss"),
    # Non-US, non-science voices — updated less often but balance the mix
    ("theguardian.com",  "https://www.theguardian.com/news/series/the-long-read/rss"),
    ("eurozine.com",     "https://www.eurozine.com/feed/"),
    ("psyche.co",        "https://psyche.co/feed/"),
]
PER_SOURCE_CAP = 6
TOTAL_CAP = 30
DESC_CAP = 500  # characters of description text forwarded to the LLM

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
        desc = ""
        # Prefer <content:encoded> > <description> > <summary> > <content>.
        # First-past-the-post across Atom and RSS 2.0 flavors; whichever
        # is first in the element order wins (consistently in practice).
        for c in item:
            tag = local(c.tag)
            if tag == "title" and title is None:
                title = clean(c.text or "")
            elif tag in ("encoded", "description", "summary", "content") and not desc:
                desc = clean(c.text or "")
        if not title:
            continue
        merged.append({
            "source": domain,
            "title": title,
            "desc":  desc[:DESC_CAP],
        })
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

# Each candidate is title + a short description pulled from the RSS feed.
# Feed both to the LLM so the micro-summary can draw from real content
# rather than riffing on the title alone.
numbered_parts = []
for i, c in enumerate(cands):
    block = f"{i+1}. [{c['source']}] {c['title']}"
    desc = (c.get("desc") or "").strip()
    if desc:
        block += f"\n   {desc}"
    numbered_parts.append(block)
numbered = "\n".join(numbered_parts)

sys_prompt = (
    "You are a curator for an ambient kitchen display in a home where two "
    "thoughtful adults cook, share meals, and have children in the room. "
    "Your job is to pick the 2 most rewarding items from the numbered "
    "candidates and, for each, write a substantive micro-essay of 4-7 "
    "lines.\n\n"
    "Editorial target — pick items that:\n"
    "- bring joy or wonder — a 'huh, I didn't know that' moment\n"
    "- invite conversation at the table — something one person reads out "
    "loud to the other and a kid can latch onto\n"
    "- raise the level — science, nature, how-things-work, history, "
    "places with stories, craft, curious facts; not hot takes, not trend "
    "pieces\n"
    "- reward a 15-second read with something that lingers\n\n"
    "Tone — not too intellectual, not dumbed down:\n"
    "- Concrete over abstract. Prefer animals, places, discoveries, "
    "objects, how-things-work explanations over pure meditation or "
    "academic framing.\n"
    "- Plain, warm English. Short words where possible. No jargon. A "
    "bright eight-year-old should be able to follow; an adult should "
    "still learn something.\n"
    "- Avoid 'generations-fear-the-next'-style abstract philosophical "
    "musing. Avoid 'essay voice.' Aim for the register of a museum wall "
    "label written by someone who loves their subject.\n\n"
    "Hard exclusions:\n"
    "- No politics, no breaking news, no celebrity gossip.\n"
    "- EXCLUDE items describing harm to children, death tolls, graphic "
    "violence, medical decline, war, or anything bleak.\n"
    "- No clickbait, no outrage, no moralising.\n\n"
    "Mix rules:\n"
    "- Prefer variety across the two picks: ideally one nature/science/"
    "curiosity item and one ideas/place/history item, or one US-origin "
    "and one non-US. Don't pick two items from the same source unless the "
    "other feeds have nothing worth showing.\n\n"
    "Writing rules:\n"
    "- Each micro-essay is 240-380 characters, 2-4 sentences. Lead with "
    "the hook; include at least one concrete detail; end cleanly. No "
    "clickbait ellipses. No source names or bylines in the text.\n"
    "- Draw content from the provided description. Do not invent facts; "
    "if the description is thin, stay general rather than fabricating.\n"
    "- Plain ASCII plus common punctuation only. No code fences. No "
    "preamble. No trailing commentary.\n\n"
    "Output must be exactly this JSON shape:\n"
    "{\"items\":[{\"body\":\"...\"},{\"body\":\"...\"}]}"
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
if not isinstance(items, list) or len(items) != 2:
    print(f"validate: items not a 2-list: {items!r}", file=sys.stderr); sys.exit(1)

out = []
for it in items:
    if not isinstance(it, dict):
        sys.exit(1)
    # Accept either `body` (new schema) or `title` (old schema) for
    # forward/backward compat while rolling this out.
    b = str(it.get("body") or it.get("title") or "").strip()
    if not b or len(b) > 440:
        # Zone is 60 × 8 = 480 chars; validator cap at 440 so typical
        # LLM output (240-380 chars target, ~400 with overshoot) passes.
        print(f"validate: budget fail len={len(b)} body={b!r}", file=sys.stderr); sys.exit(1)
    out.append({"body": b})

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

# --- Fallback: 2 most-recent items with usable descriptions --------------
# Used when the LLM is unavailable. No editorial filter — take the first
# two candidates that have at least a short description and emit each
# description trimmed at a sentence or word boundary.
fallback=$(CANDIDATES="$candidates" python3 - <<'PY'
import json, os
cands = json.loads(os.environ["CANDIDATES"])

def compose(p, target=340, hard=400):
    title = (p.get("title") or "").strip().rstrip("…").rstrip(".")
    desc = (p.get("desc") or "").strip()
    body = desc if len(desc) >= 80 else (title or "")
    if len(body) <= target:
        return body
    cut = body[:hard]
    dot = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    if dot >= target * 0.6:
        return cut[:dot+1]
    sp = cut.rfind(" ")
    if sp >= target * 0.6:
        return cut[:sp].rstrip(".,;: -") + "…"
    return cut.rstrip(".,;: -") + "…"

picks = [c for c in cands if len((c.get("desc") or "").strip()) >= 80][:2]
if not picks:
    picks = cands[:2]
out = [{"body": compose(p)} for p in picks]
print(json.dumps({"count": len(out), "items": out}, ensure_ascii=False))
PY
)
printf '%s' "$fallback" > "$STATE_FILE"
echo "wrote (fallback): $fallback"

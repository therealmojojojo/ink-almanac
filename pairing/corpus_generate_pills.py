"""Generate `smart_pill.body` for corpus text sidecars via Opus.

Defaults to whole-piece-focus (B) prompts; falls back to word-focus (A) only
for Japanese haiku/tanka, where the source-language root reliably carries
weight that translation loses. Operator can pin a per-text mode via the
sidecar field `pill_mode: A | B`.

Usage:
  # generate for explicit ids
  python corpus_generate_pills.py basho-old-pond eliot-hollow-men-i

  # fill in everything that lacks a smart_pill.body
  python corpus_generate_pills.py --all-missing

  # regenerate (Opus retighten of existing Haiku-authored pills)
  python corpus_generate_pills.py --regenerate basho-old-pond ...

  # dry run (no API call, no file write — just print what would happen)
  python corpus_generate_pills.py --dry-run --all-missing

Cost (Opus 4.7 at $15/$75 per M tok, with prompt caching on the system block):
  ~$0.012 per text. Full corpus regen (~500 texts) ≈ $6.
"""
from __future__ import annotations
import argparse, datetime, json, os, re, sys, time
from pathlib import Path
import yaml
import anthropic

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus"
TEXT_DIRS = ("texts", "personal_library")
SECRETS = ROOT / "ha" / "secrets.yaml"

# Opus 4.7 first; fall back to older Opus tags if the API rejects.
MODELS = ["claude-opus-4-7", "claude-opus-4-5", "claude-opus-4-1-20250805"]
# Body-length window. The hard cap is the renderer's actual char capacity at
# the chosen face geometry (28u Plex Sans / lh 1.1 / pad 1 / pill_grow_u +60u
# = 35 cpl × 13 rows = 455 chars). The earlier 440 was an artificial safety
# margin that flagged items the renderer would have displayed cleanly.
TARGET_MIN, TARGET_MAX = 380, 440  # what we ask Opus for
HARD_CAP = 455                     # what the renderer actually accommodates
PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "smart_pill.md"


# --- Prompts -------------------------------------------------------------

PROMPT_A = """\
You write a Smart pill: a single deep-dive entry on the text the reader sees
on the left of the same panel. The pill should make re-reading the text
richer — a well-read friend leaning over to point at one specific thing.

YOU ARE WORKING IN WORD-FOCUS MODE. Your job is to pick ONE word from the
text whose etymology, polysemy, or original-language sense is non-obvious to
a curious adult reader, and unpack it.

Word choice rules:
- Pick ONE word that appears in the text (or, for translations from
  classical sources, the source-language root word — *paideia* for
  Aristotle's "educated mind," *kareno* for Bashō's "withered fields,"
  *vitium* for Syrus's "fault").
- Prefer words that translation flattens or common usage has worn smooth.

Structure:
1. The word in asterisks, language/part-of-speech in parentheses, em-dash,
   then the working sense: "*Paideia* (Greek, n.) — what Aristotle means
   by educated."
2. Etymology and/or original-language nuance — what the word literally
   meant; what its parts mean; what English translation loses or shifts.
3. How the word works in *this specific passage* — why this writer reaches
   for it; what the line means once you carry the full weight back.
4. End on a fact or image, not a moral.
"""

PROMPT_B = """\
You write a Smart pill: a single deep-dive entry on the text the reader sees
on the left of the same panel. The pill should make re-reading the text
richer.

YOU ARE WORKING IN WHOLE-PIECE MODE. Your job is to surface the structural
move — what the piece is doing as a whole — rather than dwelling on a
single word. Best for pieces whose force comes from form: line breaks,
image juxtaposition, sound, withholding, repetition.

Structure:
1. The piece's date and immediate context in one tight sentence — what
   it was doing in its moment. (Optional: skip if you don't have specific
   defensible context.)
2. The structural move — what the piece is doing formally: where it
   pivots, what it withholds, how line breaks or image-collision load the
   meaning.
3. What changes on a re-read once you carry that move back into the lines.
   The reader should see the piece differently after this sentence.
4. End on a fact or image, not a moral.

Open with the date sentence (if confident) OR with the structural move
(if not). Do not put the word in asterisks — that's the word-focus mode's
convention; whole-piece runs as continuous prose.
"""

GUARDRAILS = """\
CONFABULATION GUARDRAILS — read carefully:

The only specific verifiable facts you may state are those listed in
ESTABLISHED FACTS. Beyond that, you must generalize or stay silent:

- Specific journal names, publication venues, named persons beyond the
  author, dated political events, "in response to": almost never defensible
  from a 4-line excerpt. Avoid.
- Year claims must match ESTABLISHED FACTS or use a non-specific range
  ("the 1920s", "in his late period", "between editions"). Never invent
  a specific year.
- Etymology: state only what you'd defend in a comparative-linguistics
  seminar. If a root would feel suspicious to a classicist, omit the
  etymology and write about the word's working sense instead. Better no
  etymology than invented etymology.
- "What the poet was responding to" / "after [event]" / "for [journal]":
  confabulation magnets. Use only when documented by mainstream
  scholarship for this specific text.

When in doubt: less specificity, more attention to the words on the page."""

VOICE_AND_OUTPUT = f"""\
Voice: plain, warm, confident English; museum wall label by someone who loves
their subject. Concrete over abstract. No jargon, no essay voice, no
showing-off.

Layout constraint: target {TARGET_MIN}-{TARGET_MAX} chars. A {HARD_CAP}-char hard cap
is enforced. End on a fact or image, not a moral. No "reminds us that," no
"a lesson in," no "we can learn," no closing reflection.

Exclusions: no politics, no harm, no sermon. The text is the subject.

Output exactly this JSON. The body MUST escape any internal double quotes
as \\".  Do not wrap the JSON in code fences. Nothing else.
{{"items":[{{"body":"..."}}]}}"""


def build_system(mode: str, with_guard: bool = True) -> str:
    base = PROMPT_A if mode == "A" else PROMPT_B
    parts = [base]
    if with_guard:
        parts.append(GUARDRAILS)
    parts.append(VOICE_AND_OUTPUT)
    return "\n\n".join(parts)


def resolve_guard(mode: str, guard_arg: str) -> bool:
    """Per-mode guardrail policy:
       - auto (default): both modes guarded.
         (Empirical: B without guardrails reliably overshoots the cap on
         items where the structural reading wants room. The targeted
         tighten-experiment showed guard ON brings 0/10 worst-overshoot
         cases back under 455. Guard's primary value here is length
         discipline, not confabulation suppression — but it does both.)
       - always: same as auto.
       - never:  neither mode guarded (debug only).
    """
    if guard_arg == "never":  return False
    return True  # auto and always


# --- Mode routing --------------------------------------------------------

def pick_mode(doc: dict) -> str:
    """Sidecar override → auto rule → default B."""
    pinned = doc.get("pill_mode")
    if pinned in ("A", "B"):
        return pinned
    form = doc.get("form", "")
    variants = doc.get("text_variants") or {}
    has_non_en = any(k != "en" for k in variants)
    if form in ("haiku", "tanka") and has_non_en:
        return "A"
    return "B"


# --- Sidecar I/O ---------------------------------------------------------

def find_sidecar(text_id: str) -> Path | None:
    for sub in TEXT_DIRS:
        p = CORPUS / sub / f"{text_id}.yaml"
        if p.exists():
            return p
    return None


def render_user(doc: dict) -> str:
    facts = [
        f"  Title:       {doc.get('title','')}",
        f"  Author:      {doc.get('author','')}",
        f"  Year:        {doc.get('year','')}",
        f"  Form:        {doc.get('form','')}",
    ]
    variants = doc.get("text_variants") or {}
    body_en = (variants.get("en") or "").strip()
    if not body_en:
        # fall back to whatever variant exists (some Ro-only items)
        body_en = next(iter(variants.values()), "").strip()
    out = "ESTABLISHED FACTS (do NOT invent beyond these):\n" + "\n".join(facts) + "\n\n"
    out += "TEXT:\n\n" + body_en + "\n"
    for lang, body in variants.items():
        if lang == "en" or not body:
            continue
        out += f"\nOriginal-language version ({lang}):\n{body.strip()}\n"
    out += f"\nWrite the Smart pill. {TARGET_MIN}-{TARGET_MAX} characters."
    return out


# --- LLM call with robust JSON extraction --------------------------------

def extract_body(raw: str) -> str | None:
    """Tolerant extraction. Try strict json first; on failure, search for
    `"body": "..."` directly with permissive regex; finally return None."""
    raw = raw.strip()
    # strip markdown fences if present
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.M)
    i, j = raw.find("{"), raw.rfind("}")
    if i >= 0 and j > i:
        candidate = raw[i:j+1]
        try:
            data = json.loads(candidate)
            return data["items"][0]["body"].strip()
        except Exception:
            pass
        # second try: tolerate unescaped internal quotes inside body
        m = re.search(r'"body"\s*:\s*"(.+)"\s*\}', candidate, re.DOTALL)
        if m:
            body = m.group(1)
            # Trailing apparatus often leaves a closing "]}; cap at last
            # period that's followed by quote-bracket tokens.
            return body.replace('\\"', '"').replace("\\n", "\n").strip()
    return None


def call_opus(client: anthropic.Anthropic, system: str, user: str,
              models: list[str] = MODELS, max_attempts: int = 2) -> dict:
    """Returns {body, model, in_tok, out_tok, raw, attempts, ok}."""
    raw = ""
    last_err = None
    for model in models:
        for attempt in range(max_attempts):
            try:
                resp = client.messages.create(
                    model=model,
                    max_tokens=900,
                    system=[{"type": "text", "text": system,
                             "cache_control": {"type": "ephemeral"}}],
                    messages=[{"role": "user", "content": user}],
                )
                raw = resp.content[0].text.strip()
                body = extract_body(raw)
                if body:
                    return {
                        "ok": True, "body": body, "model": model,
                        "in_tok": resp.usage.input_tokens,
                        "out_tok": resp.usage.output_tokens,
                        "raw": raw, "attempts": attempt + 1,
                    }
                last_err = "could not extract body from response"
            except anthropic.NotFoundError as e:
                last_err = e
                break  # try next model
            except Exception as e:
                last_err = e
                time.sleep(1.5)  # transient; retry once
    return {"ok": False, "body": "", "model": models[0], "in_tok": 0,
            "out_tok": 0, "raw": raw, "attempts": 0, "error": str(last_err)}


# --- Confabulation post-checks (advisory) --------------------------------

YEAR_RE = re.compile(r"\b(1[0-9]{3}|20[0-2][0-9])\b")
TELL_PHRASES = (
    "in response to", "in the wake of", "after the [", "for the [",
)


def post_check(body: str, doc: dict) -> list[str]:
    flags = []
    sidecar_year = str(doc.get("year") or "")
    sidecar_year_int = None
    m = re.search(r"\d{4}", sidecar_year)
    if m: sidecar_year_int = int(m.group())
    for y in YEAR_RE.findall(body):
        if sidecar_year_int and abs(int(y) - sidecar_year_int) > 30:
            flags.append(f"year-drift: pill cites {y}, sidecar year {sidecar_year}")
    lower = body.lower()
    for phrase in TELL_PHRASES:
        if phrase in lower:
            flags.append(f"hallucination-tell: '{phrase}'")
    if len(body) > HARD_CAP:
        flags.append(f"over-cap: {len(body)} > {HARD_CAP}")
    if len(body) < 200:
        flags.append(f"under-min: {len(body)} < 200 (likely truncated)")
    return flags


# --- Main ----------------------------------------------------------------

def load_api_key() -> str:
    env = os.environ.get("ANTHROPIC_API_KEY")
    if env: return env
    if SECRETS.exists():
        return yaml.safe_load(SECRETS.read_text()).get("anthropic_api_key") or ""
    return ""


def iter_all_text_yamls():
    for sub in TEXT_DIRS:
        for p in sorted((CORPUS / sub).glob("*.yaml")):
            if p.name.startswith("EXAMPLE"):
                continue
            yield p


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("ids", nargs="*", help="text ids to generate pills for")
    ap.add_argument("--all-missing", action="store_true",
                    help="generate pills for every sidecar that lacks one")
    ap.add_argument("--all", action="store_true",
                    help="target every text sidecar (combine with --regenerate "
                         "to overwrite existing pills)")
    ap.add_argument("--regenerate", action="store_true",
                    help="overwrite an existing smart_pill.body")
    ap.add_argument("--dry-run", action="store_true",
                    help="print what would happen; no API calls, no writes")
    ap.add_argument("--mode", choices=("auto", "A", "B"), default="auto",
                    help="override mode routing (default: auto per pick_mode)")
    ap.add_argument("--guard", choices=("auto", "always", "never"), default="auto",
                    help="confabulation guardrail policy. auto: A=on, B=off "
                         "(default). always: both modes guarded. never: "
                         "neither.")
    args = ap.parse_args()

    # Resolve target sidecars
    targets: list[Path] = []
    if args.all:
        for p in iter_all_text_yamls():
            d = yaml.safe_load(p.read_text()) or {}
            if not d.get("text_variants"):
                continue
            targets.append(p)
    elif args.all_missing:
        for p in iter_all_text_yamls():
            d = yaml.safe_load(p.read_text()) or {}
            if not d.get("text_variants"):
                continue  # not a text sidecar
            sp = d.get("smart_pill") or {}
            if sp.get("body"):
                continue
            targets.append(p)
    else:
        for tid in args.ids:
            p = find_sidecar(tid)
            if not p:
                print(f"  [warn] sidecar not found: {tid}", file=sys.stderr)
                continue
            targets.append(p)

    if not targets:
        print("Nothing to do.", file=sys.stderr)
        return 0

    print(f"Targets: {len(targets)} sidecars", file=sys.stderr)
    if args.dry_run:
        n_a = n_b = n_skip = 0
        for p in targets:
            d = yaml.safe_load(p.read_text()) or {}
            mode = args.mode if args.mode != "auto" else pick_mode(d)
            guard_on = resolve_guard(mode, args.guard)
            existing = (d.get("smart_pill") or {}).get("body")
            if existing and not args.regenerate:
                n_skip += 1
                continue
            print(f"  [{mode} guard={'on' if guard_on else 'off'}] {p.relative_to(CORPUS)}", file=sys.stderr)
            if mode == "A": n_a += 1
            else: n_b += 1
        print(f"\nWould generate: A={n_a}, B={n_b}, skipped (has body, no --regenerate)={n_skip}",
              file=sys.stderr)
        # Cost estimate (Opus 4.7: ~$0.012 per call after caching)
        n = n_a + n_b
        print(f"Approx cost: ${n*0.012:.2f}", file=sys.stderr)
        return 0

    key = load_api_key()
    if not key:
        print("ANTHROPIC_API_KEY not set and ha/secrets.yaml has no key.", file=sys.stderr)
        return 2
    client = anthropic.Anthropic(api_key=key)

    n_ok = n_fail = 0
    total_in = total_out = 0
    flagged: list[tuple[str, list[str]]] = []
    for p in targets:
        d = yaml.safe_load(p.read_text()) or {}
        text_id = d.get("id") or p.stem
        existing = (d.get("smart_pill") or {}).get("body")
        if existing and not args.regenerate:
            print(f"  [skip] {text_id} (has body; use --regenerate to overwrite)",
                  file=sys.stderr)
            continue
        mode = args.mode if args.mode != "auto" else pick_mode(d)
        guard_on = resolve_guard(mode, args.guard)
        system = build_system(mode, with_guard=guard_on)
        user = render_user(d)
        result = call_opus(client, system, user)
        if not result["ok"]:
            print(f"  [fail] {text_id}: {result.get('error','?')}", file=sys.stderr)
            n_fail += 1
            continue
        body = result["body"]
        flags = post_check(body, d)
        # Update sidecar
        d["smart_pill"] = {
            "body": body,
            "generated_at": datetime.date.today().isoformat(),
            "model": result["model"],
            "mode": mode,
        }
        # Preserve existing sources if any
        old_sources = (yaml.safe_load(p.read_text()) or {}).get("smart_pill", {}).get("sources")
        if old_sources:
            d["smart_pill"]["sources"] = old_sources
        if flags:
            d["smart_pill"]["review_flags"] = flags
            flagged.append((text_id, flags))
        # Write back, preserving non-pill fields' order as much as possible.
        # PyYAML default-flow-style is fine for this corpus.
        p.write_text(yaml.safe_dump(d, sort_keys=False, allow_unicode=True, width=100))
        total_in += result["in_tok"]
        total_out += result["out_tok"]
        n_ok += 1
        marker = "⚑" if flags else "·"
        print(f"  [{mode} {marker}] {text_id}  {len(body)}c  ({result['model']})",
              file=sys.stderr)

    print(f"\nGenerated: {n_ok}  Failed: {n_fail}", file=sys.stderr)
    print(f"Tokens: in={total_in} out={total_out}  approx ${total_in*15/1e6 + total_out*75/1e6:.2f}",
          file=sys.stderr)
    if flagged:
        print(f"\n{len(flagged)} flagged for operator review:", file=sys.stderr)
        for tid, fs in flagged[:20]:
            print(f"  {tid}: {'; '.join(fs)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

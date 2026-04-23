"""corpus review — in-browser triplet review tool.

Walks every triplet in `corpus/_triplets/`, renders its Summary / Weather /
Gallery / Night faces via the local renderer, shows the previews in a browser, and captures
an accept / reject-content / reject-layout verdict with an optional comment per
triplet. Verdicts are written back to the triplet sidecar as:

    triplet_verdict: keep | reject-content | reject-layout
    triplet_verdict_reason: <string>
    triplet_verdict_reviewed_at: YYYY-MM-DD

Assumes the renderer is running locally (default http://localhost:8575). Writes
the three renderer inputs (`pairing.json`, `gallery.jpg`, `nocturne.jpg`) per
triplet as the operator advances.

Usage:
    # In one terminal:
    cd renderer && npm run dev
    # In another:
    corpus review [--port 8081] [--only-unreviewed] [--start <triplet-id>]

Then open http://localhost:8081 .
"""
from __future__ import annotations
import argparse, datetime as dt, hashlib, http.server, json, os, random, shutil, socketserver, subprocess, sys, threading, urllib.error, urllib.parse, urllib.request, webbrowser
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    sys.exit("corpus review requires PyYAML: pip install pyyaml")

REPO = Path(__file__).resolve().parent.parent
CORPUS = REPO / "corpus"
TRIPLETS_DIR = CORPUS / "_triplets"
RENDERER_INPUTS = REPO / "renderer" / "inputs"
RENDERER_DEFAULT = os.environ.get("RENDERER_URL", "http://localhost:8575")
HA_SECRETS = REPO / "ha" / "secrets.yaml"

# --- Sim constants (device simulator for the /sim view) ---------------------
# Kept in sync with ha/automations/* and sonos_button_full_control's action
# list — the simulator must emit exactly what the automations expect or it
# won't exercise the same code paths a real device would.
SIM_SCHEDULE_FACE_HELPER = "input_text.inkplate_scheduled_face"
SIM_OVERRIDE_HELPER = "input_text.inkplate_active_override"
SIM_CLOCK_PUBLISHER = "automation.inkplate_publish_clock"
SIM_SONOS_ENTITY = "media_player.kitchen_sonos"
SIM_DAYLIST = "spotify:playlist:37i9dQZF1FbFSZUOQvgqEC"
SIM_SURPRISE_LIST = [
    "spotify:playlist:37i9dQZF1FbFSZUOQvgqEC",
    "spotify:playlist:37i9dQZF1E37hFUP4OBNpF",
    "spotify:playlist:37i9dQZF1E38irIBambFuG",
    "spotify:playlist:37i9dQZF1E39Isle6mfvkW",
    "spotify:playlist:37i9dQZF1E38pKzzJoZSI3",
    "spotify:playlist:37i9dQZF1E359ADH6iQjFr",
    "spotify:playlist:37i9dQZF1E376un9GUDQSy",
    "spotify:playlist:37i9dQZEVXcJgoeiSNCReh",
]

SCHEMA_TEXT_FORMS = {
    "haiku", "tanka", "sonnet", "free-verse", "stanzaic",
    "fragment", "aphorism", "prose-poem", "quote",
}
IMG_EXTS = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp")
VALID_VERDICTS = {"keep", "reject-content", "reject-layout", "skip"}


def load_yaml(p: Path) -> dict:
    return yaml.safe_load(p.read_text()) or {}


def load_items() -> dict[str, dict]:
    items: dict[str, dict] = {}
    for folder in ("images", "texts", "nocturne",
                   "personal_library", "personal_library/nocturne"):
        d = CORPUS / folder
        if not d.is_dir():
            continue
        for p in d.glob("*.yaml"):
            if p.stem.startswith("EXAMPLE"):
                continue
            try:
                doc = load_yaml(p)
            except yaml.YAMLError:
                continue
            if not isinstance(doc, dict) or not doc.get("id"):
                continue
            doc["_path"] = str(p)
            doc["_folder"] = folder
            # find companion binary (for images)
            for ext in IMG_EXTS:
                bp = p.with_suffix(ext)
                if bp.exists():
                    doc["_binary"] = str(bp)
                    break
            items[doc["id"]] = doc
    return items


def triplet_list(only_unreviewed: bool = False, start: str | None = None) -> list[dict]:
    out = []
    for p in sorted(TRIPLETS_DIR.glob("*.yaml")):
        try:
            d = load_yaml(p)
        except yaml.YAMLError:
            continue
        if not isinstance(d, dict) or not d.get("id"):
            continue
        d["_path"] = str(p)
        out.append(d)
    if only_unreviewed:
        out = [t for t in out if not t.get("triplet_verdict")]
    if start:
        for i, t in enumerate(out):
            if t["id"] == start:
                out = out[i:]
                break
    return out


def prepare_renderer_inputs(triplet: dict, items: dict[str, dict]) -> dict:
    """Write renderer/inputs/pairing.json + copy gallery.jpg / nocturne.jpg.
    Returns the pairing dict written, for the UI to display."""
    anchor = items.get(triplet.get("anchor") or "")
    summary = items.get(triplet.get("summary") or "")
    gallery = items.get(triplet.get("gallery") or "")
    nocturne = items.get(triplet.get("aligned_nocturne") or "")

    flavor_full = triplet.get("flavor", "visual-day")
    render_flavor = "visual" if flavor_full == "visual-day" else "text"

    # Always render as if scheduled for today — otherwise the night face's
    # weekday (derived from pairing.date) drifts from the summary face's
    # weekday (from clock.date, which is today).
    pairing: dict[str, Any] = {
        "date": dt.date.today().isoformat(),
        "theme": (triplet.get("themes") or ["—"])[0],
        "gallery": {
            "flavor": render_flavor,
        },
    }

    # Companion — the Summary face delight zone, opposite modality from the hero.
    # Corresponds to the triplet's `summary` slot.
    if summary:
        is_summary_image = "text" not in summary and "text_variants" not in summary
        if is_summary_image and summary.get("_binary"):
            shutil.copy2(summary["_binary"], RENDERER_INPUTS / "companion.jpg")
            companion: dict[str, Any] = {
                "kind": "visual",
                "image_path": "/inputs/companion.jpg",
                "artist": summary.get("artist") or summary.get("author") or "—",
            }
            if summary.get("title"):
                companion["title"] = summary["title"]
            sy = summary.get("year")
            if sy is not None:
                companion["year"] = str(sy)
            pairing["gallery"]["companion"] = companion
        elif not is_summary_image:
            form = summary.get("form") or "fragment"
            if form not in SCHEMA_TEXT_FORMS:
                form = "fragment"
            tv = summary.get("text_variants") or {}
            langs = summary.get("language") or []
            lang_pref = "ro" if "ro" in langs else (langs[0] if langs else "en")
            body = ""
            if isinstance(tv, dict) and tv:
                body = tv.get(lang_pref) or next(iter(tv.values()))
            elif summary.get("text"):
                body = summary["text"]
            companion_text: dict[str, Any] = {
                "kind": "text",
                "form": form,
                "body": body or "(no text body)",
                "poet": summary.get("author") or "—",
                "language": "ro" if lang_pref == "ro" else "en",
            }
            if summary.get("title"):
                companion_text["title"] = summary["title"]
            # Anthology side-by-side on Summary delight for haiku/tanka:
            # pass the Japanese original so the renderer can show both.
            if form in ("haiku", "tanka") and isinstance(tv, dict):
                ja_body = tv.get("ja")
                if ja_body and lang_pref != "ja":
                    companion_text["body_ja"] = ja_body
            pairing["gallery"]["companion"] = companion_text

    # Gallery slot
    if render_flavor == "visual" and gallery and gallery.get("_binary"):
        shutil.copy2(gallery["_binary"], RENDERER_INPUTS / "gallery.jpg")
        visual: dict[str, Any] = {
            "image_path": "/inputs/gallery.jpg",
            "title": gallery.get("title") or gallery["id"],
            "artist": gallery.get("artist") or gallery.get("author") or "",
        }
        year = gallery.get("year")
        if year is not None:
            visual["year"] = str(year)
        if gallery.get("display_title"):
            visual["display_title"] = gallery["display_title"]
        if gallery.get("display_attribution"):
            visual["display_attribution"] = gallery["display_attribution"]
        if gallery.get("pixel_width") and gallery.get("pixel_height"):
            visual["pixel_width"] = int(gallery["pixel_width"])
            visual["pixel_height"] = int(gallery["pixel_height"])
        pairing["gallery"]["visual"] = visual
    elif render_flavor == "text" and gallery:
        form = gallery.get("form") or "fragment"
        if form not in SCHEMA_TEXT_FORMS:
            form = "fragment"
        body = ""
        tv = gallery.get("text_variants") or {}
        langs = gallery.get("language") or []
        lang_pref = "ro" if "ro" in langs else (langs[0] if langs else "en")
        if isinstance(tv, dict) and tv:
            body = tv.get(lang_pref) or next(iter(tv.values()))
        elif gallery.get("text"):
            body = gallery["text"]
        language = "ro" if lang_pref == "ro" else "en"
        pairing["gallery"]["text"] = {
            "form": form,
            "body": body or "(no text body)",
            "poet": gallery.get("author") or "",
            "language": language,
        }
        if gallery.get("title"):
            pairing["gallery"]["text"]["title"] = gallery["title"]
        # Anthology mode: when a haiku/tanka carries both a translation and
        # the Japanese original, stage `body_ja` so the renderer can place
        # the original above the translation.
        if form in ("haiku", "tanka") and isinstance(tv, dict):
            ja_body = tv.get("ja")
            if ja_body and lang_pref != "ja":
                pairing["gallery"]["text"]["body_ja"] = ja_body

    # Night slot. Attribution is short-form "ARTIST · YEAR" to fit the
    # 40-char nocturne_attrib zone budget. The nocturne's title is
    # deliberately dropped at this budget — the spec's example scenarios
    # identify nocturnes by artist alone ("Brassaï nocturne").
    # Pick the night image: triplet's aligned_nocturne if set, else sample
    # deterministically from the general nocturne pool keyed on triplet id
    # (same fallback the runtime pairing pipeline applies on dates when the
    # active triplet doesn't declare one — see openspec/changes/
    # add-pairing-pipeline/specs/pairing-pipeline/spec.md). Sampling by
    # id-hash makes each triplet's preview reproducible across sessions.
    night_item = nocturne if (nocturne and nocturne.get("_binary")) else None
    if night_item is None:
        # Nocturne eligibility mirrors pairing/corpus_build_triplets.py: an image
        # is nocturne-eligible if portrait/square AND carries the
        # `night-and-lamplight` theme (no dedicated nocturne folder).
        def _portrait_or_square(it: dict) -> bool:
            pw, ph = it.get("pixel_width"), it.get("pixel_height")
            return bool(pw and ph and int(ph) >= int(pw))
        def _is_image(it: dict) -> bool:
            return not ("text" in it or "text_variants" in it)
        pool = [
            it for it in items.values()
            if it.get("_binary")
            and _is_image(it)
            and "night-and-lamplight" in (it.get("themes") or [])
            and _portrait_or_square(it)
        ]
        if pool:
            pool.sort(key=lambda it: it["id"])
            tid = triplet.get("id", "")
            idx = int(hashlib.sha1(tid.encode("utf-8")).hexdigest(), 16) % len(pool)
            night_item = pool[idx]

    if night_item and night_item.get("_binary"):
        shutil.copy2(night_item["_binary"], RENDERER_INPUTS / "nocturne.jpg")
        artist = (night_item.get("artist") or night_item.get("author") or "").upper()
        year = night_item.get("year")
        parts = []
        if artist: parts.append(artist)
        if year is not None: parts.append(str(year))
        pairing["night"] = {
            "image_path": "/inputs/nocturne.jpg",
            "title": night_item.get("title") or "",
            "fragment": " · ".join(parts) if parts else "—",
        }
    else:
        pairing["night"] = {}

    (RENDERER_INPUTS / "pairing.json").write_text(
        json.dumps(pairing, indent=2, ensure_ascii=False) + "\n")
    return pairing


def record_verdict(triplet_path: Path, verdict: str, reason: str) -> None:
    doc = load_yaml(triplet_path)
    if verdict == "skip":
        doc.pop("triplet_verdict", None)
        doc.pop("triplet_verdict_reason", None)
        doc.pop("triplet_verdict_reviewed_at", None)
    else:
        doc["triplet_verdict"] = "keep" if verdict == "keep" else verdict
        if reason:
            doc["triplet_verdict_reason"] = reason
        else:
            doc.pop("triplet_verdict_reason", None)
        doc["triplet_verdict_reviewed_at"] = dt.date.today().isoformat()
    triplet_path.write_text(
        yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, default_flow_style=False))


def renderer_alive(base: str) -> bool:
    try:
        with urllib.request.urlopen(base + "/healthz", timeout=1) as r:
            return r.status == 200
    except Exception:
        return False


# ---------------------------------------------------------------------------
# HTTP server
# ---------------------------------------------------------------------------

class ReviewServer(http.server.BaseHTTPRequestHandler):
    # class-level state (initialised in main())
    triplets: list[dict] = []
    items: dict[str, dict] = {}
    renderer_url: str = RENDERER_DEFAULT
    state: dict = {"idx": 0}
    lock = threading.Lock()
    # Sim state — HA credentials are loaded once at server start from
    # ha/secrets.yaml; pinned_hour is set by the /sim/time endpoint and
    # cleared by /sim/clock-unpin. If creds are absent, the /sim routes
    # return a helpful error instead of rendering.
    ha_url: str = ""
    ha_token: str = ""
    pinned_hour: str | None = None

    def log_message(self, fmt, *args):  # quieter
        if self.path.startswith("/api/"):
            sys.stderr.write("%s - %s\n" % (self.command, self.path))

    # --- routing -----------------------------------------------------------

    def do_GET(self):
        p = urllib.parse.urlparse(self.path)
        if p.path in ("/", "/index.html"):
            # Bake empty URL so the client loads /display/* same-origin and we
            # proxy to the renderer below. Keeps the tool usable behind a
            # single tunnel hostname (no second cloudflared ingress needed).
            return self._html(INDEX_HTML.replace("__RENDERER_URL__", ""))
        if p.path.startswith("/display/"):
            return self._proxy_to_renderer(p.path, p.query)
        if p.path == "/api/state":
            return self._json(self._state_payload())
        if p.path.startswith("/api/goto/"):
            idx = int(p.path.rsplit("/", 1)[1])
            with self.lock:
                if 0 <= idx < len(self.triplets):
                    self.state["idx"] = idx
                    self._prepare_current()
                    return self._json(self._state_payload())
            return self._json({"error": "index out of range"}, 400)
        if p.path.startswith("/api/goto-id/"):
            tid = urllib.parse.unquote(p.path[len("/api/goto-id/"):])
            with self.lock:
                for i, t in enumerate(self.triplets):
                    if t.get("id") == tid:
                        self.state["idx"] = i
                        self._prepare_current()
                        return self._json(self._state_payload())
            return self._json({"error": f"unknown triplet id {tid!r}"}, 404)
        # Device simulator endpoints
        if p.path == "/sim":
            return self._sim_index()
        if p.path == "/sim/state":
            return self._sim_state_get()
        return self._json({"error": "not found"}, 404)

    def do_POST(self):
        p = urllib.parse.urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        try:
            data = json.loads(body.decode("utf-8")) if body else {}
        except json.JSONDecodeError:
            return self._json({"error": "bad json"}, 400)

        if p.path == "/api/verdict":
            verdict = data.get("verdict", "")
            reason = (data.get("reason") or "").strip()
            if verdict not in VALID_VERDICTS:
                return self._json({"error": f"bad verdict; expected one of {sorted(VALID_VERDICTS)}"}, 400)
            with self.lock:
                cur = self.triplets[self.state["idx"]]
                record_verdict(Path(cur["_path"]), verdict, reason)
                # refresh in-memory record
                self.triplets[self.state["idx"]] = {**load_yaml(Path(cur["_path"])), "_path": cur["_path"]}
                # advance
                if self.state["idx"] + 1 < len(self.triplets):
                    self.state["idx"] += 1
                    self._prepare_current()
            return self._json(self._state_payload())

        if p.path == "/api/prev":
            with self.lock:
                if self.state["idx"] > 0:
                    self.state["idx"] -= 1
                    self._prepare_current()
            return self._json(self._state_payload())

        if p.path == "/api/next":
            with self.lock:
                if self.state["idx"] + 1 < len(self.triplets):
                    self.state["idx"] += 1
                    self._prepare_current()
            return self._json(self._state_payload())

        if p.path == "/sim/time":
            return self._sim_time(data)
        if p.path == "/sim/clock-unpin":
            return self._sim_clock_unpin()
        if p.path == "/sim/tap":
            return self._sim_tap(data)
        if p.path == "/sim/sonos":
            return self._sim_sonos(data)

        return self._json({"error": "not found"}, 404)

    # --- simulator ---------------------------------------------------------
    # Device-side simulator. Emits the same events a real device would produce
    # so existing HA automations (schedule, gesture_override, sonos_button_full_control,
    # now_playing_override) fire on their normal code paths. We shell out to
    # `curl` for every HA call because Node/Python network stacks can't reach
    # the HA VM from this Mac (EHOSTUNREACH); curl works because the OS route
    # is fine — the block is application-layer.

    def _sim_ha_call(self, method: str, api_path: str, body=None):
        if not (self.ha_url and self.ha_token):
            raise RuntimeError("HA credentials not loaded")
        args = [
            "curl", "-s",
            "-o", "-",
            "-w", "\n__HTTP_STATUS__%{http_code}",
            "-X", method,
            "-H", f"Authorization: Bearer {self.ha_token}",
            "-H", "Content-Type: application/json",
            "--max-time", "8",
            self.ha_url.rstrip("/") + api_path,
        ]
        if body is not None:
            args += ["-d", json.dumps(body)]
        r = subprocess.run(args, capture_output=True, text=True, timeout=12)
        out = r.stdout
        sep = "\n__HTTP_STATUS__"
        idx = out.rfind(sep)
        if idx < 0:
            raise RuntimeError(f"curl bad output: {r.stderr.strip() or out[:200]}")
        text = out[:idx]
        try:
            status = int(out[idx + len(sep):].strip())
        except ValueError:
            status = 0
        return status, text

    def _sim_ha_service(self, domain: str, service: str, data: dict):
        status, text = self._sim_ha_call("POST", f"/api/services/{domain}/{service}", data)
        if not (200 <= status < 300):
            raise RuntimeError(f"{domain}.{service} failed: {status} {text[:200]}")

    def _sim_ha_publish(self, topic: str, payload: str, retain: bool):
        self._sim_ha_service("mqtt", "publish",
                             {"topic": topic, "payload": payload, "retain": retain, "qos": 0})

    def _sim_ha_state(self, entity_id: str):
        status, text = self._sim_ha_call("GET", f"/api/states/{entity_id}")
        if not (200 <= status < 300):
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    def _sim_post_fake_clock(self, hhmm: str):
        """POST a fake clock to the renderer's /inputs/clock via localhost so the
        next face render uses this time. Shape matches publish_inputs.yaml."""
        now = dt.datetime.now()
        weekday = now.strftime("%a")
        month_day = now.strftime("%b %-d") if sys.platform != "win32" else now.strftime("%b %d").lstrip("0")
        body = json.dumps({"time": hhmm, "date": f"{weekday}, {month_day}"}).encode("utf-8")
        req = urllib.request.Request(
            self.renderer_url.rstrip("/") + "/inputs/clock",
            data=body, method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(req, timeout=5).read()
        except Exception as e:
            # Non-fatal — the simulator can still exercise the MQTT paths
            # even if the fake clock doesn't land.
            sys.stderr.write(f"sim: post fake clock failed: {e}\n")

    def _sim_index(self):
        if not (self.ha_url and self.ha_token):
            return self._html(
                "<h1>Simulator unavailable</h1>"
                "<p>Could not read <code>ha_base_url</code> and "
                "<code>ha_long_lived_token</code> from <code>ha/secrets.yaml</code>.</p>"
            )
        return self._html(SIM_HTML)

    def _sim_state_get(self):
        try:
            override = self._sim_ha_state(SIM_OVERRIDE_HELPER)
            scheduled = self._sim_ha_state(SIM_SCHEDULE_FACE_HELPER)
            prior = self._sim_ha_state("input_text.inkplate_prior_override")
            battery = self._sim_ha_state("sensor.inkplate_device_battery")
            condition = self._sim_ha_state("sensor.${PLACE_A_SLUG}_condition")
            temp = self._sim_ha_state("sensor.${PLACE_A_SLUG}_temperature_c")
            nowcast = self._sim_ha_state("sensor.${PLACE_A_SLUG}_nowcast_label")
            poetic = self._sim_ha_state("sensor.inkplate_poetic_weather_line")
            sonos = self._sim_ha_state(SIM_SONOS_ENTITY)

            o = (override or {}).get("state", "unknown")
            s = (scheduled or {}).get("state", "summary")
            # Reconstruct what the retained active_mode would be. (HA has no
            # REST endpoint that exposes retained-topic payloads directly, so
            # we follow the same precedence cascade documented in
            # ha/docs/architecture.md.)
            if o == "weather_peek":
                active = "weather"
            elif o == "summary_gallery_toggle":
                active = "gallery" if s == "summary" else ("summary" if s == "gallery" else s)
            elif o == "now_playing":
                active = "now-playing"
            else:
                active = s
            return self._json({
                "activeMode": active,
                "override": o,
                "scheduled": s,
                "prior": (prior or {}).get("state", ""),
                "battery": (battery or {}).get("state", ""),
                "condition": (condition or {}).get("state", ""),
                "temp": (temp or {}).get("state", ""),
                "nowcast": (nowcast or {}).get("state", ""),
                "poetic": (poetic or {}).get("state", ""),
                "sonos": (sonos or {}).get("state", ""),
                "sonosTitle": ((sonos or {}).get("attributes") or {}).get("media_title", ""),
                "sonosArtist": ((sonos or {}).get("attributes") or {}).get("media_artist", ""),
                "clockPinned": self.pinned_hour,
                "haNow": dt.datetime.utcnow().isoformat() + "Z",
            })
        except Exception as e:
            return self._json({"error": str(e)}, 502)

    def _sim_time(self, data):
        hour = (data or {}).get("hour", "")
        face_by_hour = {"07:00": "summary", "13:00": "gallery", "23:00": "night"}
        if hour not in face_by_hour:
            return self._json({"error": "hour must be 07:00, 13:00, or 23:00"}, 400)
        face = face_by_hour[hour]
        try:
            # 1. Disable the real clock publisher (so it doesn't overwrite our fake time).
            self._sim_ha_service("automation", "turn_off", {"entity_id": SIM_CLOCK_PUBLISHER})
            # Record pinned hour before posting fake clock — makes state poll honest even
            # if the clock POST is slow.
            type(self).pinned_hour = hour
            # 2. Post a fake clock.json to the renderer so it renders at this time.
            self._sim_post_fake_clock(hour)
            # 3. Update the scheduled_face helper (what schedule.yaml would do).
            self._sim_ha_service("input_text", "set_value",
                                 {"entity_id": SIM_SCHEDULE_FACE_HELPER, "value": face})
            # 4. Publish retained active_mode + wake, but only when the override is
            #    `schedule` — match schedule.yaml's guard so we don't preempt an
            #    active weather_peek / toggle / now_playing.
            override = self._sim_ha_state(SIM_OVERRIDE_HELPER)
            wake_published = (override or {}).get("state") == "schedule"
            if wake_published:
                self._sim_ha_publish("inkplate/command/active_mode", face, True)
                self._sim_ha_publish("inkplate/command/wake", "", False)
            return self._json({"ok": True, "hour": hour, "face": face,
                               "wakePublished": wake_published})
        except Exception as e:
            return self._json({"error": str(e)}, 502)

    def _sim_clock_unpin(self):
        try:
            type(self).pinned_hour = None
            self._sim_ha_service("automation", "turn_on", {"entity_id": SIM_CLOCK_PUBLISHER})
            # Force an immediate publish so real time returns without waiting for
            # the next minute-tick.
            self._sim_ha_service("automation", "trigger",
                                 {"entity_id": "automation.inkplate_publish_clock"})
            return self._json({"ok": True})
        except Exception as e:
            return self._json({"error": str(e)}, 502)

    def _sim_tap(self, data):
        kind = (data or {}).get("kind", "")
        if kind not in ("single", "double"):
            return self._json({"error": "kind must be single or double"}, 400)
        try:
            # Same payload the real device publishes post-IMU wake.
            self._sim_ha_publish("inkplate/state/gesture",
                                 json.dumps({"kind": kind}), False)
            return self._json({"ok": True, "kind": kind})
        except Exception as e:
            return self._json({"error": str(e)}, 502)

    def _sim_sonos(self, data):
        action = (data or {}).get("action", "")
        try:
            if action == "play_daylist":
                self._sim_ha_service("media_player", "volume_set",
                                     {"entity_id": SIM_SONOS_ENTITY, "volume_level": 0.0})
                self._sim_ha_service("media_player", "play_media",
                                     {"entity_id": SIM_SONOS_ENTITY,
                                      "media_content_type": "playlist",
                                      "media_content_id": SIM_DAYLIST})
                return self._json({"ok": True, "action": action, "playlist": SIM_DAYLIST})
            if action == "play_surprise":
                pick = random.choice(SIM_SURPRISE_LIST)
                self._sim_ha_service("media_player", "volume_set",
                                     {"entity_id": SIM_SONOS_ENTITY, "volume_level": 0.0})
                self._sim_ha_service("media_player", "play_media",
                                     {"entity_id": SIM_SONOS_ENTITY,
                                      "media_content_type": "playlist",
                                      "media_content_id": pick})
                return self._json({"ok": True, "action": action, "playlist": pick})
            if action == "pause":
                self._sim_ha_service("media_player", "media_pause",
                                     {"entity_id": SIM_SONOS_ENTITY})
                return self._json({"ok": True, "action": action})
            if action == "next":
                # Same production path a real Sonos-button long-hold would
                # trigger; the publish_sonos automation picks up the new track
                # via the media_content_id change and refreshes the face.
                self._sim_ha_service("media_player", "media_next_track",
                                     {"entity_id": SIM_SONOS_ENTITY})
                return self._json({"ok": True, "action": action})
            return self._json({"error": "action must be play_daylist, play_surprise, pause, or next"}, 400)
        except Exception as e:
            return self._json({"error": str(e)}, 502)

    # --- helpers -----------------------------------------------------------

    def _prepare_current(self):
        cur = self.triplets[self.state["idx"]]
        prepare_renderer_inputs(cur, self.items)

    def _state_payload(self) -> dict:
        cur = self.triplets[self.state["idx"]]
        items = self.items
        refs = {slot: cur.get(slot) for slot in ("anchor","summary","gallery","aligned_nocturne")}
        item_previews = {}
        for slot, iid in refs.items():
            if iid and iid in items:
                it = items[iid]
                item_previews[slot] = {
                    "id": iid,
                    "title": it.get("title") or iid,
                    "author": it.get("artist") or it.get("author") or "",
                    "form": it.get("form"),
                    "folder": it.get("_folder"),
                }
            else:
                item_previews[slot] = {"id": iid, "missing": True} if iid else None
        # counts across pool
        verdicts = {"keep":0, "reject-content":0, "reject-layout":0, "unreviewed":0}
        for t in self.triplets:
            v = t.get("triplet_verdict")
            verdicts[v if v in verdicts else "unreviewed"] += 1
        return {
            "idx": self.state["idx"],
            "total": len(self.triplets),
            "triplet": {
                "id": cur.get("id"),
                "flavor": cur.get("flavor"),
                "themes": cur.get("themes") or [],
                "note": cur.get("note") or "",
                "verdict": cur.get("triplet_verdict"),
                "verdict_reason": cur.get("triplet_verdict_reason") or "",
                "verdict_reviewed_at": cur.get("triplet_verdict_reviewed_at") or "",
            },
            "items": item_previews,
            "counts": verdicts,
            "cachebust": dt.datetime.now().strftime("%H%M%S%f"),
        }

    def _proxy_to_renderer(self, path: str, query: str):
        url = self.renderer_url.rstrip("/") + path
        if query:
            url += "?" + query
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                body = r.read()
                ctype = r.headers.get("Content-Type", "application/octet-stream")
                status = r.status
        except urllib.error.HTTPError as e:
            body = e.read() if hasattr(e, "read") else b""
            ctype = e.headers.get("Content-Type", "text/plain") if e.headers else "text/plain"
            status = e.code
        except Exception as e:
            body = f"renderer proxy error: {e}\n".encode("utf-8")
            ctype = "text/plain"
            status = 502
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _html(self, s: str):
        body = s.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>corpus review</title>
<style>
  :root { color-scheme: light; --fg: #222; --muted: #666; --accept: #2a8f2a; --reject: #b33; --warn: #c80; --bg: #fafafa; --card: #fff; }
  body { margin: 0; font: 14px/1.4 -apple-system, system-ui, sans-serif; color: var(--fg); background: var(--bg); }
  header { position: sticky; top: 0; background: #111; color: #eee; padding: 8px 16px; display: flex; gap: 14px; align-items: center; z-index: 10; }
  header .id { font-weight: 600; font-family: ui-monospace, monospace; }
  header .progress { color: #aaa; font-size: 13px; }
  header .counts span { margin-right: 8px; font-size: 12px; }
  header .counts .k { color: #8c8; }
  header .counts .rc { color: #e88; }
  header .counts .rl { color: #ec8; }
  header .counts .u { color: #aaa; }
  header input.goto { background: #222; color: #eee; border: 1px solid #444; border-radius: 3px; padding: 3px 6px; width: 130px; font: 12px ui-monospace, monospace; }
  header input.goto::placeholder { color: #777; }
  main { padding: 12px 16px 160px; max-width: 2400px; margin: 0 auto; }
  .meta { color: var(--muted); font-size: 13px; margin: 6px 0 12px; }
  .meta b { color: var(--fg); }
  .grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 14px; margin-bottom: 14px; }
  @media (max-width: 1100px) { .grid { grid-template-columns: 1fr; } }
  figure { margin: 0; background: var(--card); border: 1px solid #ddd; border-radius: 6px; padding: 10px; }
  figure h3 { margin: 0 0 6px; font-size: 13px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; }
  .frame { width: 100%; aspect-ratio: 1200 / 825; background: #eee; overflow: hidden; border: 1px solid #ccc; }
  .frame img { width: 100%; height: 100%; object-fit: contain; image-rendering: pixelated; display: block; background: #fff; }
  .slots { font-size: 12px; color: var(--muted); margin-top: 6px; line-height: 1.5; }
  .slots code { background: #f0f0f0; padding: 1px 4px; border-radius: 2px; }
  footer { position: fixed; bottom: 0; left: 0; right: 0; background: #111; color: #eee; padding: 12px 16px; display: flex; gap: 10px; align-items: center; box-shadow: 0 -2px 10px rgba(0,0,0,0.15); z-index: 10; }
  textarea { flex: 1; min-height: 38px; padding: 6px 10px; border-radius: 4px; border: 1px solid #444; background: #222; color: #eee; font: 13px/1.4 ui-sans-serif, system-ui; resize: vertical; }
  button { padding: 8px 14px; border-radius: 4px; border: 0; font-size: 13px; font-weight: 600; cursor: pointer; color: #fff; white-space: nowrap; }
  button.accept { background: var(--accept); }
  button.rc { background: var(--reject); }
  button.rl { background: var(--warn); }
  button.nav { background: #444; color: #ccc; font-weight: 500; }
  button.skip { background: #666; }
  .status { font-size: 12px; color: #aaa; padding: 0 10px; }
  .current-verdict { font-size: 12px; padding: 2px 8px; border-radius: 3px; font-weight: 600; }
  .current-verdict.keep { background: var(--accept); color: #fff; }
  .current-verdict.reject-content { background: var(--reject); color: #fff; }
  .current-verdict.reject-layout { background: var(--warn); color: #fff; }
  kbd { background: #333; padding: 1px 5px; border-radius: 3px; font-size: 11px; color: #ccc; }
</style>
</head>
<body>
<header>
  <div class="id" id="tid">—</div>
  <div class="progress" id="progress">— / —</div>
  <div class="counts" id="counts"></div>
  <input class="goto" id="goto" type="text" placeholder="go to # or id…" title="Enter index (1-based) or triplet id, then Enter">
  <div style="flex:1"></div>
  <span id="current-verdict"></span>
</header>
<main>
  <div class="meta" id="meta"></div>
  <div class="grid">
    <figure><h3>Summary</h3><div class="frame"><img id="img-summary" alt="summary"></div></figure>
    <figure><h3>Weather</h3><div class="frame"><img id="img-weather" alt="weather"></div></figure>
    <figure><h3>Gallery</h3><div class="frame"><img id="img-gallery" alt="gallery"></div></figure>
    <figure><h3>Night</h3><div class="frame"><img id="img-night" alt="night"></div></figure>
  </div>
  <div class="slots" id="slots"></div>
</main>
<footer>
  <button class="nav" onclick="nav('prev')" title="Previous (←, or swipe right)">← prev</button>
  <button class="nav" onclick="nav('next')" title="Next (→, or swipe left)">next →</button>
  <span class="status" id="status"></span>
</footer>
<script>
const RENDERER = "__RENDERER_URL__";
let state = null;

async function loadState() {
  const hashId = decodeURIComponent(location.hash.replace(/^#/, ''));
  let r;
  if (hashId) {
    r = await fetch('/api/goto-id/' + encodeURIComponent(hashId));
    if (!r.ok) r = await fetch('/api/state');
  } else {
    r = await fetch('/api/state');
  }
  state = await r.json();
  render();
}

function syncHash() {
  if (!state || !state.triplet) return;
  const id = state.triplet.id || '';
  const desired = '#' + encodeURIComponent(id);
  if (location.hash !== desired) {
    history.replaceState(null, '', location.pathname + location.search + desired);
  }
}

window.addEventListener('hashchange', () => {
  const hashId = decodeURIComponent(location.hash.replace(/^#/, ''));
  if (!hashId || (state && state.triplet && state.triplet.id === hashId)) return;
  fetch('/api/goto-id/' + encodeURIComponent(hashId))
    .then(r => r.ok ? r.json() : null)
    .then(s => { if (s) { state = s; render(); } });
});

function render() {
  if (!state) return;
  const t = state.triplet;
  document.getElementById('tid').textContent = t.id;
  document.getElementById('progress').textContent = `${state.idx + 1} / ${state.total}`;
  const c = state.counts;
  document.getElementById('counts').innerHTML =
    `<span class="k">✓ ${c.keep}</span><span class="rc">✗c ${c['reject-content']}</span>` +
    `<span class="rl">✗l ${c['reject-layout']}</span><span class="u">? ${c.unreviewed}</span>`;
  const v = t.verdict;
  const cv = document.getElementById('current-verdict');
  if (v) {
    cv.className = 'current-verdict ' + v;
    cv.textContent = v + (t.verdict_reviewed_at ? ' · ' + t.verdict_reviewed_at : '');
  } else { cv.className = ''; cv.textContent = ''; }
  document.getElementById('meta').innerHTML =
    `<b>flavor:</b> ${t.flavor} &nbsp; <b>themes:</b> ${(t.themes || []).join(', ') || '—'}<br>` +
    `<b>note:</b> ${t.note || '—'}`;
  const it = state.items;
  const slot = (n) => {
    const x = it[n];
    if (!x) return `<b>${n}:</b> <em>(none)</em>`;
    if (x.missing) return `<b>${n}:</b> <em>missing id <code>${x.id}</code></em>`;
    const author = x.author ? ' · ' + x.author : '';
    const form = x.form ? ' · ' + x.form : '';
    return `<b>${n}:</b> <code>${x.id}</code> · ${x.title}${author}${form} <em>(${x.folder})</em>`;
  };
  document.getElementById('slots').innerHTML =
    `<div>${slot('anchor')}</div><div>${slot('summary')}</div>` +
    `<div>${slot('gallery')}</div><div>${slot('aligned_nocturne')}</div>`;
  const bust = state.cachebust;
  document.getElementById('img-summary').src = RENDERER + '/display/summary.png?t=' + bust;
  document.getElementById('img-weather').src = RENDERER + '/display/weather.png?t=' + bust;
  document.getElementById('img-gallery').src = RENDERER + '/display/gallery.png?t=' + bust;
  document.getElementById('img-night').src = RENDERER + '/display/night.png?t=' + bust;
  document.getElementById('status').textContent = '';
  syncHash();
}

async function vote(verdict) {
  document.getElementById('status').textContent = 'saving…';
  const r = await fetch('/api/verdict', {
    method: 'POST', headers: {'content-type': 'application/json'},
    body: JSON.stringify({verdict, reason: ''}),
  });
  state = await r.json();
  render();
}

async function nav(direction) {
  const r = await fetch('/api/' + direction, {method: 'POST'});
  state = await r.json();
  render();
}

async function gotoQuery(q) {
  q = (q || '').trim();
  if (!q) return;
  const asNum = /^[0-9]+$/.test(q) ? parseInt(q, 10) - 1 : null;
  let r;
  if (asNum !== null) r = await fetch('/api/goto/' + asNum);
  else r = await fetch('/api/goto-id/' + encodeURIComponent(q));
  if (!r.ok) { document.getElementById('status').textContent = 'not found'; return; }
  state = await r.json();
  render();
  document.getElementById('goto').value = '';
}
document.getElementById('goto').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') { gotoQuery(e.target.value); e.preventDefault(); }
});

document.addEventListener('keydown', (e) => {
  if (e.target.tagName === 'TEXTAREA') return;
  if (e.key === 'a' || e.key === 'ArrowUp') { vote('keep'); e.preventDefault(); }
  else if (e.key === 'c') vote('reject-content');
  else if (e.key === 'l') vote('reject-layout');
  else if (e.key === 's') vote('skip');
  else if (e.key === 'ArrowLeft') nav('prev');
  else if (e.key === 'ArrowRight') nav('next');
});

// Swipe navigation — works on mobile Safari, Chrome, Firefox, and desktop
// (Pointer Events API). Horizontal motion > 60px, more horizontal than
// vertical, under 800ms → prev/next. Swipes starting on interactive
// elements (textarea, buttons, inputs, images) are ignored so tapping
// and typing still work.
(function attachSwipe() {
  const SWIPE_MIN_DX = 60;
  const SWIPE_MAX_DT = 800;
  const IGNORE_TAGS = ['TEXTAREA', 'INPUT', 'BUTTON', 'SELECT', 'A'];
  const tracks = new Map();
  function isInteractive(el) {
    while (el && el !== document.body) {
      if (IGNORE_TAGS.indexOf(el.tagName) >= 0) return true;
      el = el.parentElement;
    }
    return false;
  }
  window.addEventListener('pointerdown', (e) => {
    if (e.pointerType === 'mouse' && e.button !== 0) return;
    if (isInteractive(e.target)) return;
    tracks.set(e.pointerId, {x: e.clientX, y: e.clientY, t: Date.now()});
  }, true);
  window.addEventListener('pointerup', (e) => {
    const s = tracks.get(e.pointerId);
    tracks.delete(e.pointerId);
    if (!s) return;
    const dx = e.clientX - s.x;
    const dy = e.clientY - s.y;
    const dt = Date.now() - s.t;
    if (dt > SWIPE_MAX_DT) return;
    if (Math.abs(dx) < SWIPE_MIN_DX) return;
    if (Math.abs(dy) > Math.abs(dx)) return;
    if (dx < 0) nav('next'); else nav('prev');
  }, true);
  window.addEventListener('pointercancel', (e) => {
    tracks.delete(e.pointerId);
  }, true);
  // Fallback for any UA that lacks Pointer Events (very old Safari).
  if (!('onpointerdown' in window)) {
    let sx=0, sy=0, st=0, on=false;
    document.addEventListener('touchstart', (e) => {
      if (isInteractive(e.target) || e.touches.length !== 1) { on = false; return; }
      const t = e.touches[0];
      sx = t.clientX; sy = t.clientY; st = Date.now(); on = true;
    }, {passive: true});
    document.addEventListener('touchend', (e) => {
      if (!on) return; on = false;
      const t = e.changedTouches[0];
      const dx = t.clientX - sx, dy = t.clientY - sy, dt = Date.now() - st;
      if (dt > SWIPE_MAX_DT) return;
      if (Math.abs(dx) < SWIPE_MIN_DX) return;
      if (Math.abs(dy) > Math.abs(dx)) return;
      if (dx < 0) nav('next'); else nav('prev');
    }, {passive: true});
  }
})();

loadState();
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(prog="corpus review",
        description="In-browser triplet review tool. "
                    "Requires the renderer to be running locally.")
    ap.add_argument("--port", type=int, default=8081, help="Review server port (default 8081)")
    ap.add_argument("--renderer", default=RENDERER_DEFAULT, help=f"Renderer base URL (default {RENDERER_DEFAULT})")
    ap.add_argument("--only-unreviewed", action="store_true", help="Skip triplets that already have a triplet_verdict")
    ap.add_argument("--start", help="Start from this triplet id")
    ap.add_argument("--no-browser", action="store_true", help="Don't auto-open a browser")
    args = ap.parse_args()

    if not renderer_alive(args.renderer):
        sys.stderr.write(
            f"ERROR: renderer not reachable at {args.renderer}\n"
            f"Start it in another terminal: cd renderer && npm run dev\n")
        return 2

    RENDERER_INPUTS.mkdir(parents=True, exist_ok=True)

    print(f"loading corpus items...")
    items = load_items()
    print(f"  {len(items)} items")

    triplets = triplet_list(only_unreviewed=args.only_unreviewed, start=args.start)
    if not triplets:
        print("no triplets to review")
        return 0
    print(f"  {len(triplets)} triplets to review")

    ReviewServer.triplets = triplets
    ReviewServer.items = items
    ReviewServer.renderer_url = args.renderer

    # Load HA credentials for the /sim simulator endpoints. If the secrets
    # file is absent or keys missing, /sim routes will return a clear error
    # page; the rest of the review tool works unaffected.
    if HA_SECRETS.exists():
        try:
            s = yaml.safe_load(HA_SECRETS.read_text()) or {}
            url = (s.get("ha_base_url") or "").strip()
            tok = (s.get("ha_long_lived_token") or "").strip()
            if url and tok:
                ReviewServer.ha_url = url
                ReviewServer.ha_token = tok
                print(f"  sim: HA credentials loaded ({url})")
            else:
                print("  sim: ha/secrets.yaml missing ha_base_url or ha_long_lived_token")
        except Exception as e:
            print(f"  sim: failed to read ha/secrets.yaml: {e}")
    else:
        print(f"  sim: {HA_SECRETS} not present — /sim will be disabled")

    # seed renderer inputs with the first triplet
    prepare_renderer_inputs(triplets[0], items)

    class _TCPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
        allow_reuse_address = True
        daemon_threads = True

    with _TCPServer(("127.0.0.1", args.port), ReviewServer) as httpd:
        url = f"http://127.0.0.1:{args.port}/"
        print(f"\nreview UI at {url}")
        print(f"renderer at  {args.renderer}")
        print(f"press Ctrl+C to stop\n")
        if not args.no_browser:
            try: webbrowser.open(url)
            except Exception: pass
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")
    return 0


SIM_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Device simulator — Inkplate</title>
  <style>
    :root { color-scheme: light; }
    * { box-sizing: border-box; }
    body { margin: 0; font: 13px/1.45 -apple-system, system-ui, sans-serif; background: #111; color: #ddd; }
    header { padding: 14px 18px; background: #0a0a0a; border-bottom: 1px solid #222; display: flex; justify-content: space-between; align-items: center; }
    header h1 { font-size: 14px; font-weight: 500; margin: 0; }
    header .pinned { color: #ffb86c; font-weight: 600; font-size: 12px; }
    header .muted { color: #888; font-size: 12px; }
    header a { color: #6aa7d8; text-decoration: none; font-size: 12px; }
    header a:hover { text-decoration: underline; }
    main { display: grid; grid-template-columns: minmax(0, 1fr) 340px; gap: 18px; padding: 18px; align-items: start; }
    .face-panel { background: #000; border: 1px solid #222; border-radius: 4px; overflow: hidden; aspect-ratio: 1200 / 825; display: flex; align-items: center; justify-content: center; position: relative; }
    .face-panel img { max-width: 100%; max-height: 100%; display: block; }
    .face-panel .loading { position: absolute; top: 8px; right: 8px; color: #666; font-size: 11px; }
    aside { display: flex; flex-direction: column; gap: 14px; }
    section { background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 4px; padding: 12px; }
    section h2 { margin: 0 0 8px; font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; color: #888; font-weight: 600; }
    button { display: block; width: 100%; margin: 4px 0; padding: 8px 10px; font: inherit; background: #2a2a2a; color: #eee; border: 1px solid #3a3a3a; border-radius: 3px; cursor: pointer; text-align: left; }
    button:hover { background: #333; border-color: #555; }
    button:active { background: #444; }
    button:disabled { opacity: 0.5; cursor: wait; }
    button.danger { background: #3a2020; border-color: #5a2020; }
    button.accent { background: #204030; border-color: #2a6040; }
    .state { display: grid; grid-template-columns: auto 1fr; gap: 2px 10px; font-size: 12px; margin-top: 4px; }
    .state dt { color: #888; }
    .state dd { color: #ddd; margin: 0; word-break: break-word; }
    .log { margin: 0 18px 18px; padding: 10px; background: #0a0a0a; border: 1px solid #222; border-radius: 4px; color: #888; font: 11px/1.4 ui-monospace, SFMono-Regular, monospace; max-height: 220px; overflow-y: auto; white-space: pre-wrap; }
    .log .ok { color: #a0d080; }
    .log .err { color: #d08080; }
  </style>
</head>
<body>
  <header>
    <h1>Device simulator — Inkplate</h1>
    <div>
      <a href="/">← review tool</a>
      &nbsp; <span id="pin-indicator"></span>
      &nbsp; <span id="ha-now" class="muted"></span>
    </div>
  </header>
  <main>
    <div class="face-panel">
      <img id="face" alt="current face">
      <span id="loading" class="loading"></span>
    </div>
    <aside>
      <section>
        <h2>Current state (HA)</h2>
        <dl class="state" id="state-dl"></dl>
      </section>
      <section>
        <h2>Time of day</h2>
        <button data-hour="07:00">07:00 &nbsp;→ Morning (Summary)</button>
        <button data-hour="13:00">13:00 &nbsp;→ Daytime (Gallery)</button>
        <button data-hour="23:00">23:00 &nbsp;→ Night</button>
        <button id="unpin" class="danger" style="display:none">Unpin — resume real time</button>
      </section>
      <section>
        <h2>Tap (device → HA)</h2>
        <button data-tap="single">Single tap &nbsp;→ Weather peek (5 min)</button>
        <button data-tap="double">Double tap &nbsp;→ Summary / Gallery toggle</button>
      </section>
      <section>
        <h2>Sonos (HA → Sonos)</h2>
        <button data-sonos="play_daylist" class="accent">Play daylist &nbsp;→ activates Now-Playing</button>
        <button data-sonos="play_surprise">Swap to random playlist &nbsp;→ face re-renders</button>
        <button data-sonos="next">Next track &nbsp;→ face re-renders with new art</button>
        <button data-sonos="pause" class="danger">Pause &nbsp;→ Now-Playing exits after linger</button>
      </section>
    </aside>
  </main>
  <pre class="log" id="log"></pre>

<script>
const $ = (id) => document.getElementById(id);
const log = (msg, cls = '') => {
  const el = $('log');
  const ts = new Date().toLocaleTimeString();
  el.innerHTML += '<span class="' + cls + '">' + ts + '  ' + msg + '</span>\n';
  el.scrollTop = el.scrollHeight;
};

async function postJSON(url, body) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || ('HTTP ' + res.status));
  return data;
}

let lastMode = '';

async function refreshState() {
  try {
    const res = await fetch('/sim/state');
    const s = await res.json();
    if (s.error) { log('state: ' + s.error, 'err'); return; }

    const dl = $('state-dl');
    const rows = [
      ['active mode', s.activeMode],
      ['override', s.override],
      ['scheduled', s.scheduled],
      ['prior', s.prior || '—'],
      ['condition', s.condition || '—'],
      ['temp', s.temp ? s.temp + '°C' : '—'],
      ['nowcast', s.nowcast || '—'],
      ['poetic', s.poetic || '—'],
      ['sonos', s.sonos + (s.sonosTitle ? ' · ' + s.sonosTitle : '')],
      ['battery', s.battery ? s.battery + '%' : '—'],
    ];
    dl.innerHTML = rows.map(([k, v]) =>
      '<dt>' + k + '</dt><dd>' + (v == null ? '' : String(v)) + '</dd>'
    ).join('');

    if (s.activeMode && s.activeMode !== lastMode) {
      lastMode = s.activeMode;
      reloadFace();
    }

    if (s.clockPinned) {
      $('pin-indicator').innerHTML = '<span class="pinned">⏸ clock pinned at ' + s.clockPinned + '</span>';
      $('unpin').style.display = '';
    } else {
      $('pin-indicator').textContent = '';
      $('unpin').style.display = 'none';
    }
    $('ha-now').textContent = 'HA now: ' + new Date(s.haNow).toLocaleTimeString();
  } catch (err) {
    log('state poll failed: ' + err.message, 'err');
  }
}

function reloadFace() {
  const mode = lastMode || 'summary';
  $('loading').textContent = 'loading ' + mode + '…';
  const img = $('face');
  img.onload = () => { $('loading').textContent = ''; };
  img.onerror = () => { $('loading').textContent = 'load failed'; };
  img.src = '/display/' + mode + '.png?ts=' + Date.now();
}

function busy(btn, fn) {
  return async (...args) => {
    btn.disabled = true;
    try { await fn(...args); }
    finally { btn.disabled = false; }
  };
}

document.querySelectorAll('[data-hour]').forEach((btn) => {
  btn.addEventListener('click', busy(btn, async () => {
    const hour = btn.getAttribute('data-hour');
    try {
      const r = await postJSON('/sim/time', { hour });
      log('time ' + hour + ' → ' + r.face + (r.wakePublished ? ' (wake pulse sent)' : ' (override active, no wake)'), 'ok');
      await new Promise((r) => setTimeout(r, 900));
      await refreshState();
      reloadFace();
    } catch (err) { log('time button failed: ' + err.message, 'err'); }
  }));
});

$('unpin').addEventListener('click', async () => {
  try {
    await postJSON('/sim/clock-unpin', {});
    log('clock unpinned — real time resumed', 'ok');
    await new Promise((r) => setTimeout(r, 400));
    await refreshState();
    reloadFace();
  } catch (err) { log('unpin failed: ' + err.message, 'err'); }
});

document.querySelectorAll('[data-tap]').forEach((btn) => {
  btn.addEventListener('click', busy(btn, async () => {
    const kind = btn.getAttribute('data-tap');
    try {
      await postJSON('/sim/tap', { kind });
      log('tap ' + kind + ' → HA gesture handler', 'ok');
      await new Promise((r) => setTimeout(r, 2500));
      await refreshState();
      reloadFace();
    } catch (err) { log('tap failed: ' + err.message, 'err'); }
  }));
});

document.querySelectorAll('[data-sonos]').forEach((btn) => {
  btn.addEventListener('click', busy(btn, async () => {
    const action = btn.getAttribute('data-sonos');
    try {
      const r = await postJSON('/sim/sonos', { action });
      const tail = r.playlist ? ' (' + r.playlist.split(':').pop() + ')' : '';
      log('sonos ' + action + tail, 'ok');
      // Sonos takes a few seconds to report the new track.
      await new Promise((r) => setTimeout(r, 2000));
      await refreshState();
      reloadFace();
      await new Promise((r) => setTimeout(r, 4000));
      await refreshState();
      reloadFace();
    } catch (err) { log('sonos failed: ' + err.message, 'err'); }
  }));
});

refreshState();
setInterval(refreshState, 4000);
log('simulator ready', 'ok');
</script>
</body>
</html>"""


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Generate the Stars-cell statement for the Weather face.

Sourced from real ephemerides (Skyfield + DE421) plus Launch Library 2
upcoming launches and Spaceflight Now / NASASpaceflight RSS feeds. The
combined fact-block is handed to Claude Haiku for phrasing only; the
model cannot invent events because it has none to invent.

Output: a single short statement written to the state file (default
/config/custom/inkplate/state/astro_event.txt). The renderer reads
this through `sensor.astro_event_tonight` and renders it in the Stars
cell at a font size chosen by `weather.ts:pickStarsTier`.

Fallback chain:
  1. Haiku rephrase of the fact-block (warm, varied)
  2. Deterministic Skyfield phrase (highest-altitude visible planet)
  3. Empty string (renderer falls back to "no event tonight")

Usage:
  generate_astro_event.py [--lat 44.4268] [--lon 26.1025]
                          [--date 2026-04-30] [--tz-offset 3]
                          [--state-file PATH] [--ephem PATH]
                          [--fact-block PATH]   # bypass live fetches
                          [--print-facts]       # dump fact-block, no API
                          [--dry-run]           # don't write state file

The --fact-block flag lets a smoke test inject a fabricated scenario
(e.g. Artemis IV launching tomorrow + quiet sky) so we can validate
salience ranking without waiting for a real launch day.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import re
import ssl
import sys
import urllib.request
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

DEFAULT_LAT = 44.4268
DEFAULT_LON = 26.1025
DEFAULT_TZ_OFFSET_HOURS = 3  # EEST
DEFAULT_STATE_FILE = Path("/config/custom/inkplate/state/astro_event.txt")
DEFAULT_EPHEM = Path("/config/custom/inkplate/data/de421.bsp")
USER_AGENT = "inkplate-stars/1.0"

LL2_URL = "https://ll.thespacedevs.com/2.2.0/launch/upcoming/?limit=10"
SFN_RSS = "https://spaceflightnow.com/feed/"
NSF_RSS = "https://www.nasaspaceflight.com/feed/"
HAIKU_MODEL = "claude-haiku-4-5-20251001"
HAIKU_MAX_TOKENS = 200
HAIKU_URL = "https://api.anthropic.com/v1/messages"


# ---------------------------------------------------------------------------
# Skyfield sky computation
# ---------------------------------------------------------------------------

def compute_sky_tonight(
    lat: float, lon: float, date_utc: dt.datetime, tz_offset_hours: int,
    ephem_path: Path,
) -> dict[str, Any]:
    """Return tonight's sky facts for the given lat/lon, computed from
    DE421. Tonight = sunset on `date_utc` to next sunrise."""
    from skyfield import almanac
    from skyfield.api import Loader, N, E, wgs84

    load = Loader(str(ephem_path.parent))
    eph = load(ephem_path.name)
    ts = load.timescale()

    earth = eph["earth"]
    moon = eph["moon"]
    place = wgs84.latlon(lat * N, lon * E)
    observer = earth + place

    def fmt_local(t) -> str:
        d = t.utc_datetime() + dt.timedelta(hours=tz_offset_hours)
        return d.strftime("%H:%M")

    t0 = ts.utc(date_utc.year, date_utc.month, date_utc.day, 0)
    t1 = ts.utc(date_utc.year, date_utc.month, date_utc.day + 2, 0)

    # Sunset / sunrise
    f_sun = almanac.sunrise_sunset(eph, place)
    times, events = almanac.find_discrete(t0, t1, f_sun)
    sunset = next_sunrise = None
    for t, e in zip(times, events):
        local = t.utc_datetime() + dt.timedelta(hours=tz_offset_hours)
        if e == 0 and local.date() == date_utc.date() and sunset is None:
            sunset = t
        if e == 1 and sunset is not None and next_sunrise is None:
            next_sunrise = t
    if sunset is None or next_sunrise is None:
        return {"date": date_utc.strftime("%Y-%m-%d"), "error": "no sunset/sunrise"}

    # Twilight transitions during the night
    f_twi = almanac.dark_twilight_day(eph, place)
    twi_times, twi_events = almanac.find_discrete(sunset, next_sunrise, f_twi)
    twilight = {}
    twi_label = {0: "astronomical_night_starts",
                 1: "astronomical_twilight_morning",
                 2: "civil_twilight_morning"}
    for t, e in zip(twi_times, twi_events):
        if e in twi_label:
            twilight[twi_label[e]] = fmt_local(t)

    # Moon phase + illumination
    phase_angle = almanac.moon_phase(eph, ts.utc(
        date_utc.year, date_utc.month, date_utc.day, 21
    )).degrees
    if phase_angle < 22.5 or phase_angle >= 337.5:
        phase = "new moon"
    elif phase_angle < 67.5: phase = "waxing crescent"
    elif phase_angle < 112.5: phase = "first quarter"
    elif phase_angle < 157.5: phase = "waxing gibbous"
    elif phase_angle < 202.5: phase = "full moon"
    elif phase_angle < 247.5: phase = "waning gibbous"
    elif phase_angle < 292.5: phase = "last quarter"
    else: phase = "waning crescent"
    illum = (1 - math.cos(math.radians(phase_angle))) / 2 * 100

    # Moon rise/set tonight
    f_moon = almanac.risings_and_settings(eph, moon, place)
    m_times, m_events = almanac.find_discrete(sunset, next_sunrise, f_moon)
    moon_rise = moon_set = None
    for t, e in zip(m_times, m_events):
        if e == 1 and moon_rise is None: moon_rise = fmt_local(t)
        if e == 0 and moon_set is None:  moon_set  = fmt_local(t)

    moon_alt_at_sunset = observer.at(sunset).observe(moon).apparent().altaz()[0].degrees
    if moon_rise and not moon_set:
        up_during = "rises during night"
    elif moon_set and not moon_rise:
        up_during = "sets during night"
    elif moon_rise and moon_set:
        up_during = "partial"
    elif moon_alt_at_sunset > 0:
        up_during = "all night"
    else:
        up_during = "not visible"

    # Planets — sample every 15 min through the window, look for alt > 5°
    samples = []
    cur = sunset
    while cur.utc_datetime() < next_sunrise.utc_datetime():
        samples.append(cur)
        cur = ts.utc((cur.utc_datetime() + dt.timedelta(minutes=15))
                     .replace(tzinfo=dt.timezone.utc))

    planet_keys = {
        "Mercury": "mercury",
        "Venus": "venus",
        "Mars": "mars",
        "Jupiter": "jupiter barycenter",
        "Saturn": "saturn barycenter",
    }
    cardinals = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    def cardinal_of(deg: float) -> str:
        idx = int(((deg + 22.5) % 360) // 45)
        return cardinals[idx]

    planets_out = []
    for pname, pkey in planet_keys.items():
        try:
            planet = eph[pkey]
        except KeyError:
            continue
        max_alt = -90.0
        max_t = None
        max_az = 0.0
        first_up = last_up = None
        for s in samples:
            alt, az, _ = observer.at(s).observe(planet).apparent().altaz()
            if alt.degrees > 5:
                if first_up is None: first_up = s
                last_up = s
            if alt.degrees > max_alt:
                max_alt = alt.degrees
                max_t = s
                max_az = az.degrees
        if first_up is None:
            planets_out.append({
                "name": pname, "visible": False,
                "max_alt_deg": round(max_alt, 1),
            })
            continue
        planets_out.append({
            "name": pname, "visible": True,
            "window_local": f"{fmt_local(first_up)}-{fmt_local(last_up)}",
            "peak_alt_deg": round(max_alt, 1),
            "peak_at": fmt_local(max_t),
            "direction_at_peak": cardinal_of(max_az),
        })

    # Conjunctions (< 5° separation, both above horizon)
    bodies = [("Moon", moon)]
    for pname, pkey in planet_keys.items():
        try: bodies.append((pname, eph[pkey]))
        except KeyError: pass
    conjunctions = []
    for i in range(len(bodies)):
        for j in range(i + 1, len(bodies)):
            n1, b1 = bodies[i]
            n2, b2 = bodies[j]
            min_sep = 999.0
            min_t = None
            for s in samples:
                p1 = observer.at(s).observe(b1).apparent()
                p2 = observer.at(s).observe(b2).apparent()
                sep = p1.separation_from(p2).degrees
                if sep < min_sep:
                    min_sep = sep
                    min_t = s
            if min_sep < 5 and min_t is not None:
                a1 = observer.at(min_t).observe(b1).apparent().altaz()[0].degrees
                a2 = observer.at(min_t).observe(b2).apparent().altaz()[0].degrees
                if a1 > 0 and a2 > 0:
                    conjunctions.append({
                        "pair": f"{n1} & {n2}",
                        "separation_deg": round(min_sep, 1),
                        "at_local": fmt_local(min_t),
                    })

    # Active meteor showers (IMO calendar; conservative annual table).
    # Format: (name, start_md, peak_md, end_md, ZHR)
    showers = [
        ("Quadrantids",   "12-28", "01-04", "01-12", 110),
        ("Lyrids",        "04-14", "04-22", "04-30",  18),
        ("eta-Aquariids", "04-19", "05-06", "05-28",  50),
        ("delta-Aquariids","07-12","07-30", "08-23",  25),
        ("Perseids",      "07-17", "08-12", "08-24", 100),
        ("Orionids",      "10-02", "10-21", "11-07",  20),
        ("Leonids",       "11-06", "11-17", "11-30",  15),
        ("Geminids",      "12-04", "12-14", "12-17", 150),
    ]
    md = date_utc.strftime("%m-%d")
    active_showers = []
    for name, start, peak, end, zhr in showers:
        in_range = (start <= md <= end) if start <= end else (md >= start or md <= end)
        if in_range:
            try:
                peak_dt = dt.datetime.strptime(f"{date_utc.year}-{peak}", "%Y-%m-%d").date()
                days_to_peak = (peak_dt - date_utc.date()).days
            except ValueError:
                days_to_peak = None
            active_showers.append({
                "name": name,
                "active": f"{start} to {end}",
                "peak_date": f"{date_utc.year}-{peak}",
                "zhr": zhr,
                "days_to_peak": days_to_peak,
            })

    return {
        "date": date_utc.strftime("%Y-%m-%d"),
        "location": f"({lat:.2f}N, {lon:.2f}E)",
        "tz_offset_hours": tz_offset_hours,
        "sun": {"set": fmt_local(sunset), "rise_next": fmt_local(next_sunrise)},
        "twilight": twilight,
        "moon": {
            "phase": phase,
            "illumination_pct": round(illum),
            "rise": moon_rise,
            "set": moon_set,
            "up_during_window": up_during,
        },
        "planets": planets_out,
        "close_approaches_under_5deg": conjunctions,
        "active_meteor_showers": active_showers,
    }


# ---------------------------------------------------------------------------
# Live fetches — Launch Library 2 + RSS
# ---------------------------------------------------------------------------

def _fetch_json(url: str, timeout: int = 8) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as r:
        return json.load(r)


def _fetch_rss_titles(url: str, n: int = 8, timeout: int = 8) -> list[dict[str, str]]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as r:
        doc = ET.fromstring(r.read())
    out = []
    for it in doc.findall(".//item")[:n]:
        out.append({
            "title": (it.findtext("title") or "").strip(),
            "pub":   (it.findtext("pubDate") or "").strip(),
        })
    return out


def fetch_upcoming_launches() -> list[dict[str, Any]]:
    try:
        data = _fetch_json(LL2_URL)
    except Exception as exc:
        print(f"[warn] LL2 fetch failed: {exc}", file=sys.stderr)
        return []
    out = []
    for x in data.get("results", []):
        out.append({
            "net_utc": x.get("net"),
            "name": x.get("name"),
            "provider": (x.get("launch_service_provider") or {}).get("name"),
            "pad": (x.get("pad") or {}).get("name"),
            "country": (x.get("pad") or {}).get("country_code"),
            "status": (x.get("status") or {}).get("abbrev"),
            "mission_type": (x.get("mission") or {}).get("type"),
            "mission_desc": ((x.get("mission") or {}).get("description") or "")[:160],
        })
    return out


def fetch_recent_news() -> dict[str, list[dict[str, str]]]:
    out = {"spaceflight_now": [], "nasaspaceflight": []}
    try: out["spaceflight_now"] = _fetch_rss_titles(SFN_RSS)
    except Exception as exc: print(f"[warn] SFN fetch failed: {exc}", file=sys.stderr)
    try: out["nasaspaceflight"] = _fetch_rss_titles(NSF_RSS)
    except Exception as exc: print(f"[warn] NSF fetch failed: {exc}", file=sys.stderr)
    return out


# ---------------------------------------------------------------------------
# Haiku phrasing
# ---------------------------------------------------------------------------

PROMPT = """\
You write the "Stars" cell of a small e-ink kitchen panel for a single
reader: a stargazer who loves astronomy and space science. The panel has
a separate Moon cell already, so do NOT mention the moon in your output
(you may use moonlight as a reason to suppress faint targets, but never
name the moon).

Below is the full raw data available to you for this 24-hour window:
  - sky_tonight: what is computed to be visible at the panel's location
  - upcoming_launches_next_10: scheduled rocket launches
  - recent_space_news: latest headlines from two industry feeds

Pick the ONE thing this reader would most want to know right now and
write it as a single short statement. Rank by genuine interest to an
astronomy/space-science nerd, not by recency or novelty for its own sake:
  - Routine launches (Starlink, generic comm-sat) are noise; skip them
    unless nothing else is interesting.
  - Crewed flights, lunar/Mars/deep-space missions, novel vehicles
    (Starship, New Glenn first flights, reusable firsts), science-payload
    launches, and rare planetary events outrank routine ops.
  - A genuinely good sky tonight (planet high and bright, conjunction,
    meteor peak under dark skies) outranks a story about something
    happening on the other side of the world a week from now.
  - If a story is more than ~7 days old, it is not "news" anymore.

Output strict JSON only, nothing else, no markdown fence, no commentary:
  {"text": "..."}

Hard constraints:
  - text: <= 70 characters total, plain prose, no emoji
  - never start with "Tonight" (cell is implicitly tonight)
  - if a launch is the headline, prefer naming the vehicle/mission over
    the operator ("Falcon Heavy returns" beats "SpaceX launch")
  - if the sky is the headline, prefer compass + timing over generic
    ("Jupiter high in SW until 01:00" beats "Jupiter is bright")
  - one statement may carry more than one beat if connected naturally
    with a comma or em dash ("Jupiter bright in SW, Venus low in W")

Data:
"""


def call_haiku(api_key: str, facts: dict[str, Any]) -> str | None:
    body = {
        "model": HAIKU_MODEL,
        "max_tokens": HAIKU_MAX_TOKENS,
        "messages": [
            {"role": "user", "content": PROMPT + json.dumps(facts, ensure_ascii=False)}
        ],
    }
    req = urllib.request.Request(
        HAIKU_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15, context=ssl.create_default_context()) as r:
            resp = json.load(r)
    except Exception as exc:
        print(f"[warn] Haiku call failed: {exc}", file=sys.stderr)
        return None
    try:
        raw = resp["content"][0]["text"]
    except (KeyError, IndexError):
        print(f"[warn] Haiku response missing content: {resp}", file=sys.stderr)
        return None
    return parse_haiku_text(raw)


def parse_haiku_text(raw: str) -> str | None:
    """Strip markdown fence, parse JSON, return the text field. Returns
    None on any parse failure so the caller can fall back."""
    cleaned = raw.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, re.S)
    if fence:
        cleaned = fence.group(1).strip()
    try:
        obj = json.loads(cleaned)
    except json.JSONDecodeError:
        # Sometimes the model adds prose after the JSON; try to find the
        # first {...} block and parse that.
        m = re.search(r"\{.*?\}", cleaned, re.S)
        if not m:
            return None
        try:
            obj = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    text = obj.get("text") if isinstance(obj, dict) else None
    if not isinstance(text, str) or not text.strip():
        return None
    return text.strip()


# ---------------------------------------------------------------------------
# Deterministic fallback (Skyfield-derived phrase, no LLM)
# ---------------------------------------------------------------------------

def deterministic_phrase(sky: dict[str, Any]) -> str:
    """Return a short statement derived purely from the sky fact-block.
    Picks the highest-altitude visible planet; if none, returns ''. Does
    not mention the moon (Moon cell handles that)."""
    visible = [p for p in sky.get("planets", []) if p.get("visible")]
    if not visible:
        return ""
    visible.sort(key=lambda p: p.get("peak_alt_deg", 0), reverse=True)
    top = visible[0]
    name = top["name"]
    direction = top.get("direction_at_peak", "")
    window = top.get("window_local", "")
    end = window.split("-")[-1] if "-" in window else ""
    if direction and end:
        return f"{name} high in {direction} until {end}"
    if direction:
        return f"{name} visible in {direction}"
    return f"{name} visible tonight"


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

def load_api_key(secrets_path: Path) -> str | None:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key: return key
    if not secrets_path.exists(): return None
    try:
        import yaml
        data = yaml.safe_load(secrets_path.read_text()) or {}
        v = data.get("anthropic_api_key")
        return v if v and v != "REPLACE_ME" else None
    except Exception:
        # No yaml lib — fall back to a one-line grep.
        for line in secrets_path.read_text().splitlines():
            if line.startswith("anthropic_api_key:"):
                return line.split(":", 1)[1].strip()
        return None


def build_fact_block(args) -> dict[str, Any]:
    if args.fact_block:
        return json.loads(Path(args.fact_block).read_text())
    date_utc = dt.datetime.fromisoformat(args.date) if args.date else \
               dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc)
    if date_utc.tzinfo is None:
        date_utc = date_utc.replace(tzinfo=dt.timezone.utc)

    sky = compute_sky_tonight(args.lat, args.lon, date_utc, args.tz_offset, args.ephem)
    return {
        "today_utc": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%MZ"),
        "sky_tonight": sky,
        "upcoming_launches_next_10": fetch_upcoming_launches(),
        "recent_space_news": fetch_recent_news(),
    }


def main():
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("--lat", type=float, default=DEFAULT_LAT)
    p.add_argument("--lon", type=float, default=DEFAULT_LON)
    p.add_argument("--date", help="UTC date (YYYY-MM-DD); default today UTC")
    p.add_argument("--tz-offset", type=int, default=DEFAULT_TZ_OFFSET_HOURS,
                   dest="tz_offset", help="Hours from UTC for the panel's local time")
    p.add_argument("--state-file", type=Path, default=DEFAULT_STATE_FILE)
    p.add_argument("--ephem", type=Path, default=DEFAULT_EPHEM,
                   help="Path to the DE421 ephemeris file")
    p.add_argument("--secrets", type=Path,
                   default=Path("/config/custom/inkplate/secrets.yaml"))
    p.add_argument("--fact-block", help="Path to a JSON fact-block (skips live fetches)")
    p.add_argument("--print-facts", action="store_true",
                   help="Print the fact-block and exit; do not call Haiku.")
    p.add_argument("--dry-run", action="store_true",
                   help="Don't write the state file; just print the result.")
    args = p.parse_args()

    facts = build_fact_block(args)

    if args.print_facts:
        json.dump(facts, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
        return 0

    api_key = load_api_key(args.secrets)
    statement = None
    if api_key:
        statement = call_haiku(api_key, facts)
    else:
        print("[warn] no anthropic_api_key; skipping Haiku, using fallback",
              file=sys.stderr)

    if not statement:
        statement = deterministic_phrase(facts.get("sky_tonight", {}))
        if statement:
            print(f"[info] fell back to deterministic phrase", file=sys.stderr)

    if statement is None:
        statement = ""

    print(statement)
    if not args.dry_run:
        args.state_file.parent.mkdir(parents=True, exist_ok=True)
        args.state_file.write_text(statement + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())

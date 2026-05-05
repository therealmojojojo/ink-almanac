#!/usr/bin/env python3
"""Validate ``ha/config/wake_schedule.yaml`` and emit the rendered JSON the
device firmware expects on the ``inkplate/command/schedule`` MQTT topic,
along with its FNV-32 hash for HA-side dashboard comparison.

This is the HA-side counterpart of ``firmware/src/wake.cpp::parseSchedule``.
The two MUST stay in lockstep on the rejection rules — anything the firmware
rejects, this script must reject too, so a typo fails loud at deploy time
rather than silently at the device's next Full wake. See
``openspec/changes/add-pushable-wake-schedule/specs/device-firmware/spec.md``
for the rule list.

Output (success): a single JSON object on stdout, exit 0:
    {"hash": "<8 hex digits>", "payload": "<canonical schedule JSON>"}

The wrapping object lets HA's command_line sensor extract the hash as the
sensor state (8 chars, well under HA's 255-char state limit) and expose
the full payload as a `payload` json attribute. The publish automation
reads the attribute and publishes verbatim — keeping the bytes that HA
sends and the bytes the firmware hashes byte-identical, so the device's
schedule_hash and the validator's hash always match.

Output (failure): rejection reason on stderr, exit 1. The HA caller sees
empty stdout (sensor state goes `unknown`); the deploy automation then
raises a persistent_notification.

Invocation: ``python3 validate_wake_schedule.py [<yaml_path>]``. Default
path is ``/config/custom/inkplate/config/wake_schedule.yaml`` so the HA-side
command_line sensor can call it with no args.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml  # PyYAML — bundled with the HA python env

DEFAULT_YAML = Path("/config/custom/inkplate/config/wake_schedule.yaml")
CANONICAL_NAMES = ("night", "morning", "midday", "evening")
MAX_FULL = 720
MIN_FULL = 1


def fail(msg: str) -> "NoReturn":  # type: ignore[misc]
    print(f"validate_wake_schedule: {msg}", file=sys.stderr)
    sys.exit(1)


def parse_hhmm(s: object) -> int:
    if not isinstance(s, str) or len(s) != 5 or s[2] != ":":
        fail(f"start must be HH:MM, got {s!r}")
    try:
        h = int(s[0:2])
        m = int(s[3:5])
    except ValueError:
        fail(f"start has non-numeric digits: {s!r}")
    if not (0 <= h <= 23 and 0 <= m <= 59):
        fail(f"start out of range: {s!r}")
    return h * 60 + m


def require_int(d: dict, key: str, ctx: str) -> int:
    v = d.get(key)
    if not isinstance(v, int) or isinstance(v, bool):
        fail(f"{ctx}.{key} must be a non-negative integer, got {v!r}")
    if v < 0:
        fail(f"{ctx}.{key} must be >= 0, got {v}")
    return v


def main(argv: list[str]) -> int:
    yaml_path = Path(argv[1]) if len(argv) >= 2 else DEFAULT_YAML
    if not yaml_path.exists():
        fail(f"file not found: {yaml_path}")
    try:
        doc = yaml.safe_load(yaml_path.read_text())
    except yaml.YAMLError as e:
        fail(f"YAML parse error: {e}")
    if not isinstance(doc, dict):
        fail("top-level YAML is not a mapping")

    if doc.get("version") != 1:
        fail(f"version must be 1, got {doc.get('version')!r}")

    raw_tiers = doc.get("tiers")
    if not isinstance(raw_tiers, dict):
        fail("tiers must be a mapping of name -> tier dict")
    if set(raw_tiers.keys()) != set(CANONICAL_NAMES):
        fail(
            "tiers must contain exactly: " + ", ".join(CANONICAL_NAMES)
            + f"; got {sorted(raw_tiers.keys())}"
        )

    rendered = []
    starts: dict[int, str] = {}
    for name in CANONICAL_NAMES:
        t = raw_tiers[name]
        if not isinstance(t, dict):
            fail(f"tier {name!r} must be a mapping")
        ctx = f"tiers.{name}"

        start_min = parse_hhmm(t.get("start"))
        full_min = require_int(t, "full_min", ctx)
        poll_min = require_int(t, "poll_min", ctx)
        partial_min = require_int(t, "partial_min", ctx)

        if not (MIN_FULL <= full_min <= MAX_FULL):
            fail(f"{ctx}.full_min must be in [{MIN_FULL},{MAX_FULL}], got {full_min}")
        if poll_min > 0 and poll_min >= full_min:
            fail(f"{ctx}.poll_min must be < full_min ({full_min}), got {poll_min}")
        if partial_min > full_min:
            fail(f"{ctx}.partial_min must be <= full_min ({full_min}), got {partial_min}")
        if poll_min > 0 and (full_min % poll_min) != 0:
            fail(f"{ctx}: full_min ({full_min}) must be divisible by poll_min ({poll_min})")
        if partial_min > 0 and (full_min % partial_min) != 0:
            fail(
                f"{ctx}: full_min ({full_min}) must be divisible by partial_min ({partial_min})"
            )
        if (start_min % full_min) != 0:
            fail(
                f"{ctx}: start ({t.get('start')!r}) must align to full_min ({full_min}); "
                f"{start_min} %% {full_min} = {start_min % full_min}"
            )
        if start_min in starts:
            fail(f"{ctx}.start collides with {starts[start_min]!r} ({t.get('start')!r})")
        starts[start_min] = name

        rendered.append(
            {
                "name": name,
                "start": t["start"],
                "full_min": full_min,
                "poll_min": poll_min,
                "partial_min": partial_min,
            }
        )

    # Order tiers by start_min in the emitted JSON. The firmware sorts
    # internally so order is advisory, but a stable order makes the
    # FNV-32 hash stable across deploys.
    rendered.sort(key=lambda x: parse_hhmm(x["start"]))

    out = {"version": 1, "tiers": rendered}
    # `separators=(",", ":")` produces compact JSON whose byte-identical
    # output is what the FNV-32 hash is computed over on both sides. Any
    # change in formatting changes the hash, but the parser tolerates it
    # — the device just dedup-misses and re-applies the same operational
    # schedule.
    payload = json.dumps(out, separators=(",", ":"))

    # FNV-1a, 32-bit, over the UTF-8 bytes of the payload. Identical
    # algorithm to firmware/src/wake.cpp::fnv32 — must produce the same
    # value bit-for-bit so HA-side and device-side hashes match.
    h = 2166136261
    for byte in payload.encode("utf-8"):
        h ^= byte
        h = (h * 16777619) & 0xFFFFFFFF

    sys.stdout.write(json.dumps({"hash": f"{h:08x}", "payload": payload}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

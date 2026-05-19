#!/usr/bin/env python3
"""Pick today's triplet by sequence rotation and write the renderer inputs.

Run daily before the morning Summary face is requested (HA fires this at
06:00 via shell_command.publish_today_pairing). Idempotent: running it
multiple times in the same day produces the same output.

Rotation: triplets are walked in `sequence` order. Day 1 → first triplet,
day 2 → second, … day N+1 → wraps back to first. The "epoch" — which day
counts as day 1 — is recorded in pairing/_state/triplet_epoch.json on
first run (today's date). To re-anchor (e.g., after regenerating the pool
and wanting to restart from sequence 1), delete or hand-edit that file.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from pairing_inputs import (
    load_items,
    load_triplets_sorted,
    prepare_renderer_inputs,
    REPO,
)

STATE_DIR = REPO / "pairing" / "_state"
EPOCH_FILE = STATE_DIR / "triplet_epoch.json"


def get_or_init_epoch(today: dt.date) -> dt.date:
    """Return the date treated as 'day 1' of the rotation. Writes a state
    file on first call so subsequent calls are stable across days/reboots."""
    if EPOCH_FILE.exists():
        try:
            data = json.loads(EPOCH_FILE.read_text())
            return dt.date.fromisoformat(data["date"])
        except (json.JSONDecodeError, KeyError, ValueError):
            pass
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    EPOCH_FILE.write_text(
        json.dumps({"date": today.isoformat(),
                    "note": "triplet rotation day-1 anchor; delete to re-anchor"},
                   indent=2) + "\n"
    )
    return today


def pick_todays_triplet(today: dt.date, triplets: list[dict]) -> dict:
    epoch = get_or_init_epoch(today)
    days_since = (today - epoch).days
    if not triplets:
        sys.exit("publish_today: no triplets in corpus/_triplets/")
    idx = days_since % len(triplets)
    return triplets[idx]


def main() -> int:
    ap = argparse.ArgumentParser(description="Publish today's triplet to renderer inputs.")
    ap.add_argument("--date", help="ISO date override (default: today). Useful for testing.")
    ap.add_argument("--id", help="Force a specific triplet id, ignoring rotation.")
    ap.add_argument("--dry-run", action="store_true", help="Print what would be written; don't touch files.")
    args = ap.parse_args()

    today = dt.date.fromisoformat(args.date) if args.date else dt.date.today()
    triplets = load_triplets_sorted()
    items = load_items()

    if args.id:
        match = [t for t in triplets if t["id"] == args.id]
        if not match:
            sys.exit(f"publish_today: triplet id '{args.id}' not found")
        triplet = match[0]
        choice = "--id forced"
    else:
        triplet = pick_todays_triplet(today, triplets)
        epoch = get_or_init_epoch(today)
        days = (today - epoch).days
        choice = f"day {days+1} of {len(triplets)}-triplet rotation (epoch {epoch.isoformat()})"

    print(f"publish_today {today.isoformat()}: {triplet['id']}  ({choice})")
    print(f"  anchor:  {triplet.get('anchor')}")
    print(f"  summary: {triplet.get('summary')}")
    print(f"  gallery: {triplet.get('gallery')}")
    print(f"  flavor:  {triplet.get('flavor')}")

    if args.dry_run:
        print("(dry-run; no files written)")
        return 0

    pairing = prepare_renderer_inputs(triplet, items)
    print(f"  wrote: renderer/inputs/{{pairing,smart_pill}}.json + companion/gallery/nocturne.jpg")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

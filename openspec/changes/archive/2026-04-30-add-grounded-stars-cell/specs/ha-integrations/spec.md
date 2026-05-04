# Spec delta — ha-integrations (Astro data)

## MODIFIED Requirements

### Requirement: Astro data

HA SHALL expose:

- Sunrise and sunset times for the operator's local location (via
  `sun.sun` or equivalent)
- Daylight duration (derived)
- Current moon phase (via the built-in `moon` sensor)
- Next full moon date (derived by a template sensor)
- A grounded short statement for the Stars cell, refreshed daily, that
  summarises tonight's most interesting astronomical or space-science
  fact for a stargazer reader. This statement SHALL be sourced from:
  - **Skyfield** + the DE421 ephemeris file installed on the operator
    VM, computing tonight's planet visibility windows, peak altitudes
    and cardinal directions, close approaches, and active meteor
    showers for the panel's lat/lon
  - **Launch Library 2** (`ll.thespacedevs.com`) — upcoming launches
  - **Spaceflight Now** and **NASASpaceflight** RSS feeds — narrative
    space-news headlines from the last ~7 days

  The fact-block is passed verbatim to Claude Haiku, which acts only
  as a phrasing layer. The resulting statement is written to
  `/config/custom/inkplate/state/astro_event.txt`. The model SHALL be
  instructed to skip routine launches (Starlink, generic comm-sat) as
  noise, prioritise crewed/lunar/Mars/novel-vehicle/science-payload
  events and rare planetary events, and never mention the moon (the
  Moon cell handles that).

The daily refresh SHALL run at 07:00 local time so the cell is correct
from breakfast onward for the *upcoming* night.

The publisher SHALL implement a freshness guard: when
`astro_event.txt` mtime is older than 30 hours, the command-line
sensor returns the empty string, and the renderer falls back to the
"no event tonight" treatment. Stale text SHALL NOT be surfaced.

#### Scenario: Weather face astro footer renders

- **WHEN** Weather is rendered
- **THEN** the astro footer receives sunrise, sunset, moon-phase SVG
  hint, next-full-moon date, and tonight's Stars statement (if any)
  from HA

#### Scenario: Stars cell after a successful morning run

- **WHEN** `generate_astro_event.py` runs at 07:00 with live Skyfield,
  LL2, and RSS responses
- **THEN** `astro_event.txt` contains a single short statement that
  refers only to objects/events present in the input fact-block; the
  statement does not mention the moon

#### Scenario: Stars cell when LLM output is unparseable

- **WHEN** Haiku returns text that cannot be parsed as the expected
  JSON shape
- **THEN** the helper writes a deterministic Skyfield-derived phrase
  (highest-altitude visible planet with its compass direction and
  visibility window) instead of the raw model output

#### Scenario: Stars cell when the cron does not run

- **WHEN** `astro_event.txt` mtime is 36 hours old (yesterday's run
  succeeded but today's failed silently)
- **THEN** `sensor.astro_event_tonight` reports an empty string and
  the renderer surfaces the literal "no event tonight" text rather
  than yesterday's stale statement

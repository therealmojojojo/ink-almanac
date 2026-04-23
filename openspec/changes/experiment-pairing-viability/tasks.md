## 1. Prerequisites

- [ ] 1.1 Verify `build-seed-corpus` has reached its v1 milestone (300+300 items, ≥15 per theme per side)
- [ ] 1.2 Verify `add-rendering-pipeline` and `add-dashboard-faces` are applied so real renders can be used in the review PDF

## 2. Generation script

- [ ] 2.1 Implement `pairing/src/inkplate/experiment/generate.py` that produces 30 days of pairings:
  - Shuffle the 33 themes; take 30 for the experiment
  - For each day, deliberately assign flavor (visual-day or text-day) per the current plan
  - Run tag-based retrieval: theme filter, exclude items used earlier in the 30-day horizon
  - Random-pick hero; mood/register intersection with hero (≥2 shared tags); random-pick companion
  - Write `day-N.json` capturing hero_id, companion_id, flavor, theme
- [ ] 2.2 (Optional, strongly recommended) Support variants: run the algorithm multiple times with different mood-intersection thresholds or with/without companion filtering, so the review can compare them side-by-side

## 3. Review-panel rendering

- [ ] 3.1 Generate per-day Gallery + Summary PNGs using the real renderer (pointing it at the experiment's day-N.json files and stub inputs for weather/climate/HN)
- [ ] 3.2 Downscale to review-panel size suitable for a PDF page

## 4. PDF assembly

- [ ] 4.1 Implement PDF generation using a Python library (`reportlab` or similar) or a Markdown→PDF pipeline
- [ ] 4.2 Cover page with corpus snapshot statistics
- [ ] 4.3 30 pairing pages (one per day), two-panel
- [ ] 4.4 Feedback form at the back (printable / annotatable)
- [ ] 4.5 Summary statistics page at the end

## 5. Review session

- [ ] 5.1 Schedule the session with the wife
- [ ] 5.2 Walk through each day; mark working/unclear/not-working; capture patterns
- [ ] 5.3 Aggregate the feedback form; note clear patterns and clear outliers

## 6. Verdict

- [ ] 6.1 Write `verdict.md` capturing the decision (GO / MODIFY / DROP), rationale, evidence, implications
- [ ] 6.2 If MODIFY, document the specific modification(s) and whether a second experimental run is planned
- [ ] 6.3 Commit `verdict.md`

## 7. Archival

- [ ] 7.1 Archive this change (`/opsx:archive experiment-pairing-viability`) with the verdict in place
- [ ] 7.2 If DROP, propose withdrawal or significant scope reduction of `add-pairing-pipeline`
- [ ] 7.3 If MODIFY, amend `add-pairing-pipeline`'s specs before it applies
- [ ] 7.4 If GO, proceed to `add-pairing-pipeline` implementation as specified

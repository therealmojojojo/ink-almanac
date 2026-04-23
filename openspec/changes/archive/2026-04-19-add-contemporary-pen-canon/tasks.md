# Tasks

## 1. Shortlist — 20 creators across 4 streams

- [x] 1.1 Author `lists/top-contemporary-pen.yaml`: manga (7), Western comic-strip / cartoon (6), XKCD (1), caricature + contemporary ink (6)
- [ ] 1.2 Operator review + approval of the shortlist

## 2. Stage-2 per-creator works lists

- [x] 2.1 Author `lists/works-xkcd.yaml` with ~15 most-referenced xkcd strips
- [ ] 2.2 Author `lists/works-manga.yaml`: per-mangaka ~6–10 iconic panels/covers
- [ ] 2.3 Author `lists/works-comic-strips.yaml`: Watterson, Schulz, Larson, Adams (Dilbert), plus Hergé/Uderzo panels if we go European
- [ ] 2.4 Author `lists/works-caricature.yaml`: Hirschfeld, Searle, Sempé, Blake, Shrigley, Steadman
- [ ] 2.5 Author `lists/works-contemporary-drawing.yaml`: Spiegelman Maus pages, Satrapi Persepolis, Pettibon

## 3. Fetchers

- [x] 3.1 XKCD source adapter — `pairing/fetch_xkcd.py`. JSON API, no key, PNG direct. Writes `corpus/personal_library/xkcd-<n>.{yaml,png}` and appends manifest entries.
- [ ] 3.2 Extend `pairing/corpus_api_fetch.py` to accept the xkcd source for a `works-xkcd.yaml`-shaped input (so the orchestrator calls a unified interface).

## 4. Fetch runs

- [x] 4.1 Run `fetch_xkcd.py` against `works-xkcd.yaml` — commit ~15 strips.
- [ ] 4.2 Run comic-strip fetch via Commons-primary (Watterson, Schulz, Larson, Adams, Hergé).
- [ ] 4.3 Run manga fetch via Commons-primary for panel scans; publisher / foundation sites as fallback.
- [ ] 4.4 Run caricature fetch (Commons + foundation sites).
- [ ] 4.5 Run contemporary-drawing fetch (Commons + gallery sites).

## 5. Rebalance `add-bw-graphic-arts-canon`

- [ ] 5.1 Cap old-master etching creators (Rembrandt, Piranesi, Meryon, Daumier, Whistler, Goya, Redon tonal noirs) at 2–3 "most-contrasted" items each; drop the rest from the working canon. Those sidecars stay on disk as `panel_verdict: flag` for later revisit.
- [ ] 5.2 Re-run the contact sheet so operator can confirm the trimmed old-master set reads well.

## 6. Spec updates

- [ ] 6.1 Add "Pen-first non-photograph spine" requirement to `specs/corpus-seed/spec.md` (delta): target ≥ 60% of non-photograph images to be pen-and-ink / woodcut / screentone / sumi-e / ligne-claire; tonal-print capped.
- [ ] 6.2 `openspec validate add-contemporary-pen-canon` passes.

## 7. Archive

- [ ] 7.1 Target: ≥ 120 new items across streams 1–4 at final audit.
- [ ] 7.2 Merge `specs/corpus-seed` delta into `openspec/specs/corpus-seed/spec.md`.

## 1. Validator

- [x] 1.1 `pairing/corpus_validate.py` rejects a triplet whose summary slot resolves to a text whose body exceeds the `delight_text` zone budget (4 lines / 24 chars per line)
- [x] 1.2 Budget constants (`SUMMARY_DELIGHT_MAX_LINES`, `SUMMARY_DELIGHT_MAX_CHARS`) added at module top with a comment pointing at `renderer/src/zones.ts`
- [x] 1.3 Error message reports the slot id, observed line count, observed max line length, and the budget

## 2. Pool audit

- [x] 2.1 Count text-summary overflow in the current pool — **114** fresh rejections; **117** validator errors total (superset including already-rejected triplets)
- [x] 2.2 Auto-reject the 114 with `triplet_verdict: reject-layout` and a machine-parseable reason

## 3. Spec

- [x] 3.1 Add "Summary text fits delight_text zone" requirement to the `corpus-triplets` spec delta
- [x] 3.2 `openspec validate require-summary-text-fits-zone` passes

## 4. Out of scope

- Rebuilding the 114 rejected triplets (separate authoring pass — either a 2–4 line summary-text substitute, or a flavor flip to an image summary).
- Generalizing the rule to other zones (no other face has an analogous tight text budget exposed through an authoring-time slot). If new zones arrive with analogous budgets, a "slot fits zone" generalization change can subsume both this and `require-slot-orientation`.

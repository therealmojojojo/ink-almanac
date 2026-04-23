## 1. Validator

- [x] 1.1 `pairing/corpus_validate.py` rejects a triplet whose `summary` image slot is portrait (`pixel_height > pixel_width`)
- [x] 1.2 `pairing/corpus_validate.py` rejects a triplet whose `aligned_nocturne` image slot is landscape (`pixel_width > pixel_height`)
- [x] 1.3 `corpus validate` lists the offending slot, id, and dimensions in the error message (format: `<path>: <slot> slot -> '<id>' is portrait|landscape (WxH); <slot> requires ...`)

## 2. Pool audit

- [x] 2.1 Count triplets violating each rule — summary-portrait: **94**; aligned_nocturne-landscape: **9**
- [x] 2.2 Counts recorded above; rebuild is a separate follow-up change

## 3. Spec

- [x] 3.1 Add "Image slot orientation" requirement to the `corpus-triplets` spec delta in this change
- [x] 3.2 `openspec validate require-slot-orientation` passes

## 4. Out of scope

- Rebuilding the 94 (or more) offending triplets is tracked separately — this change only ratifies and enforces the rule.
- No renderer-side changes: the rule is an authoring-time constraint, enforced at validation.

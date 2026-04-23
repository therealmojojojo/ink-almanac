# corpus/_taxonomy/

Controlled vocabularies referenced by every corpus sidecar. Authoritative spec: `openspec/specs/corpus-taxonomy/spec.md`.

## Files

| File | Dimension | Fixed size at seed |
|---|---|---|
| `themes.yaml` | Subject / register / orientation themes | 33 entries |
| `mood.yaml` | Felt quality of the work | starting set, closed |
| `register.yaml` | Voice / rhetorical stance | starting set, closed |
| `form.yaml` | Text-form or image-form, disjoint groups | closed |
| `validation.md` | Human-readable catalogue of validator rules | — |

Each file is a YAML mapping. Keys are canonical kebab-case, lowercase tag identifiers; values are objects with at least `label` (human-readable) and `description` (one-sentence gloss). Sidecars reference the **keys**; the validator rejects references to labels.

## Amendment procedure

The `mood` and `register` vocabularies are closed at the seed — adding or deprecating terms goes through this flow. `themes` and `form` change only via an accompanying spec change.

### When to add a term

Add a term only when:
1. At least three existing or planned items genuinely need it, **and**
2. Those items cannot be tagged adequately with the existing vocabulary without losing a distinction the pairing pipeline actually uses.

A term that applies to one item is a description, not a tag. A term that duplicates an existing term with a different flavour dilutes the signal.

### How to add a term

1. Open a change proposal under `openspec/changes/<change-name>/` that:
   - Names the term, its `label`, and its `description`.
   - Lists every existing sidecar the new term will be back-applied to.
   - Flags that this amends `corpus/_taxonomy/<file>.yaml`.
2. In the same change, edit the taxonomy file. Add the entry with:

   ```yaml
   new-term:
     label: "Human-readable label"
     description: "One-sentence gloss."
     added_in: <change-name>
   ```

3. In the same change, re-tag every affected sidecar. The validator must pass at HEAD.
4. Archive the change only after the seed batch finishes without further amendments (see `corpus-taxonomy` spec "Vocabulary stability gate").

### When to deprecate a term

Deprecate (never delete) a term when a superseding term is added or when the term proves unused/redundant. A deprecated term:

1. Stays in the YAML file so historical references still validate locally if needed, but is marked:

   ```yaml
   old-term:
     label: "..."
     description: "..."
     deprecated: true
     replaced_by: new-term
     deprecated_in: <change-name>
   ```

2. Requires migration of every existing sidecar referencing it to `replaced_by` in the same change.
3. Is not proposed by ingestion tools once marked `deprecated: true`.

### Do not

- Do not add a term from a sidecar. Ingestion halts on unknown tags; that halt is the trigger for an amendment proposal, not for editing the sidecar around it.
- Do not delete a term outright. Deprecate + migrate.
- Do not re-use a deprecated key for a new meaning.

## Vocabulary stability gate

`build-seed-corpus` cannot archive until two consecutive ingestion batches complete without amending `mood.yaml` or `register.yaml`. Amendments reset the counter. See `openspec/specs/corpus-taxonomy/spec.md` "Vocabulary stability gate".

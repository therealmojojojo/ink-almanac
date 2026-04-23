# Retired canonical lists

This file records canonical lists that were authored during Phase 1 but retired before execution (or re-executed against a new rubric). Retirement is not deletion: the files stay on disk, marked `status: retired`, so the curatorial reasoning is auditable.

## 2026-04-17 — native-B&W pivot

Hardware evidence showed that color-origin works reproduce poorly on the 3-bit greyscale Inkplate 10 panel. Iso-luminant hues collapse and saturation-carried register is lost. The corpus pivoted to prefer native-B&W media (etching, engraving, wood-engraving, drawing, ink-wash, silverpoint, monochrome lithograph, B&W photography) and to refuse `panel_fidelity: color-dependent` items at ingestion.

The `corpus-schema` spec added `panel_fidelity` as a required image-item field with three values (`native`, `robust`, `color-dependent`); `corpus-triplets` added a rule that any image slot in a triplet must be `native` or `robust`.

### Retired

- **`modern-painting-canon.yaml`** — majority color-dependent (Matisse paintings, Hopper, Warhol color, Klee *Senecio*, Iancu Tzara, Schiele *physalis*). Five survivors — the drawings and blotted-line works — re-home under `drawing-canon.yaml` when that list is authored.

### Demoted (not retired, but rubric changed)

- **`ukiyo-e-canon.yaml`** — color woodblock; items need individual `panel_fidelity` review. Expected outcome: tonally strong snow and night scenes (Hiroshige *Asakusa Snow*, Hiroshige nocturnes) remain as `robust`; pure-hue pieces (Hokusai *Red Fuji*, *Great Wave* — Prussian-blue-dependent) are re-classified `color-dependent` and dropped. The ink-only *Hokusai Manga* sketchbooks become candidates for a new native-B&W category.

### New lists to author against the pivot

Ordered by expected curatorial weight. Each will be proposed via `corpus propose-list` with `panel_fidelity` pre-populated per entry:

1. `drawing-canon.yaml` — Dürer drawings, Schiele drawings, Modigliani drawings, Matisse *Blue Nude* cutouts, Warhol blotted-line, Klee *Twittering Machine*, Saul Steinberg, Edward Gorey, Beardsley, Redon charcoal, Kollwitz.
2. `etching-engraving-canon.yaml` — Rembrandt etchings, Goya *Caprichos* / *Desastres* / *Tauromaquia* / *Disparates*, Dürer engravings (*Melencolia I*, *Knight Death and the Devil*, *St. Jerome*), Callot *Misères de la guerre*, Blake illuminated prints.
3. `sumi-e-canon.yaml` — Sesshū, Hasegawa Tōhaku *Pine Trees screen*, Mu Qi *Six Persimmons*, Bada Shanren, Ike no Taiga, Qi Baishi ink birds.
4. `wood-engraving-canon.yaml` — Lynd Ward wordless novels, Leonard Baskin, Paul Landacre, Eric Gill (new `form: wood-engraving` vocab entry).
5. `kollwitz-daumier-litho.yaml` — Käthe Kollwitz self-portraits and *Weavers' Cycle*, Daumier legal-theatre lithographs, Toulouse-Lautrec sketch work, Goya *Bulls of Bordeaux*.
6. `bw-photography-expansion.yaml` — extend beyond current HCB/Kertész/Doisneau/Brassaï/Maier/Koudelka/Atget set to: Weston, Strand, Sudek, Sieff, Salgado, Ansel Adams, Lange, Walker Evans, Robert Frank, Arbus, Lartigue, August Sander.
7. `hokusai-manga-sketchbooks.yaml` — pure ink-line sketch pages, distinct from the color prints in `ukiyo-e-canon`.

### Existing on-disk items to back-fill

The 50 images already fetched before this pivot need `panel_fidelity` back-filled in their sidecars. Expected distribution:

- **`native`** (~35): all Cajal, Haeckel, Piranesi, Atget, Abdullah Frères/Bonfils albumen, HCB, Doisneau, Kertész, Vivian Maier, Koudelka, Cassandre posters (graphic), Whistler *Nocturne in Blue & Gold* (tonally strong), Schiele drawings, Modigliani drawing, Klee *Twittering Machine*, Warhol blotted-line.
- **`robust`** (~6–8): Hiroshige snow/night scenes, Utamaro *Three Beauties* (tonal structure strong), Friedrich *Wanderer* (tonally strong painting), Bonfils Acropolis.
- **`color-dependent`** (drop): Hokusai *Red Fuji*, Hokusai *Great Wave* (Prussian-blue composition), Hokusai *Thunderstorm* (color-carried), Klee *Senecio*, Schiele *physalis*, Hopper *Nighthawks*, Hopper *Morning Sun*, Iancu *Tzara*.

The drop list should be re-fetched as replacements from the new native-B&W lists.

/**
 * Hand-curated overrides for display_title where the mechanical pass
 * produced an awkward truncation. Run after curate-image-captions.
 *
 * Usage:
 *   tsx src/tools/recurate-image-captions.ts --fix
 */
import fs from 'node:fs/promises';
import path from 'node:path';

const CORPUS = path.resolve(process.cwd(), '../corpus');

type Override = { rel: string; display_title: string };

// All replacements verified ≤ 20 chars (grapheme clusters).
const OVERRIDES: Override[] = [
  { rel: 'images/abdullah-freres-hagia-sophia.yaml',          display_title: 'Hagia Sophia' },
  { rel: 'images/cajal-purkinje-cells.yaml',                   display_title: 'Purkinje Neuron' },
  { rel: 'images/cajal-pyramidal-cortex.yaml',                 display_title: 'Pyramidal Neurons' },
  { rel: 'images/daumier-third-class-carriage.yaml',           display_title: 'Third-Class Carriage' },
  { rel: 'images/durer-knight-death-devil.yaml',               display_title: 'Knight & Death' },
  { rel: 'images/durer-st-jerome-in-study.yaml',               display_title: 'Saint Jerome' },
  { rel: 'images/friedrich-wanderer-mist.yaml',                display_title: 'Wanderer in Fog' },
  { rel: 'images/goya-bulls-bordeaux-plaza-partida.yaml',      display_title: 'Bullfight, Bordeaux' },
  { rel: 'images/goya-desastres-grande-hazana-muertos.yaml',   display_title: 'Grande hazaña!' },
  { rel: 'images/goya-giant-tauromaquia.yaml',                 display_title: 'La Tauromaquia' },
  { rel: 'images/hine-powerhouse-mechanic.yaml',               display_title: 'Powerhouse Mechanic' },
  { rel: 'images/hiroshige-asakusa-snow.yaml',                 display_title: 'Asakusa Ricefields' },
  { rel: 'images/hiroshige-shin-ohashi-shower.yaml',           display_title: 'Sudden Shower, Atake' },
  { rel: 'images/hokusai-ejiri-wind.yaml',                     display_title: 'Ejiri, Suruga' },
  { rel: 'images/hokusai-manga-birds-flight.yaml',             display_title: 'Birds in Flight' },
  { rel: 'images/ike-no-taiga-true-view-mt-asama.yaml',        display_title: 'View of Mt. Asama' },
  { rel: 'images/klee-twittering-machine.yaml',                display_title: 'Twittering Machine' },
  { rel: 'images/kollwitz-mother-dead-child.yaml',             display_title: 'Woman, Dead Child' },
  { rel: 'images/liang-kai-sixth-patriarch.yaml',              display_title: 'Sixth Patriarch' },
  { rel: 'images/ma-yuan-scholar-by-waterfall.yaml',           display_title: 'Scholar & Waterfall' },
  { rel: 'images/piranesi-pantheon-interior.yaml',             display_title: 'The Pantheon' },
  { rel: 'images/piranesi-vedute-di-roma-colosseum.yaml',      display_title: 'The Colosseum' },
  { rel: 'images/redon-pilgrim-of-the-sublunary-world.yaml',   display_title: 'The Pilgrim' },
  { rel: 'images/rembrandt-hundred-guilder-print.yaml',        display_title: 'Healing the Sick' },
  { rel: 'images/rembrandt-self-portrait-etching-1639.yaml',   display_title: 'Self-Portrait, 1639' },
  { rel: 'images/rothstein-dust-bowl-father-sons.yaml',        display_title: 'Dust Storm, Cimarron' },
  { rel: 'images/schiele-seated-woman-bent-knee.yaml',         display_title: 'Seated Woman' },
  { rel: 'images/sesshu-autumn-winter-landscape.yaml',         display_title: 'Autumn & Winter' },
  { rel: 'images/utamaro-three-beauties.yaml',                 display_title: 'Three Beauties' },
  { rel: 'images/xia-gui-pure-and-remote-view.yaml',           display_title: 'Pure & Remote View' },

  { rel: 'nocturne/atget-coin-rue-cardinal-lemoine.yaml',      display_title: 'Sainte-Geneviève' },
  { rel: 'nocturne/friedrich-man-woman-contemplating-moon.yaml', display_title: 'Contemplating Moon' },
  { rel: 'nocturne/grimshaw-liverpool-quay-moonlight.yaml',    display_title: 'Liverpool Quay' },
  { rel: 'nocturne/grimshaw-reflections-thames.yaml',          display_title: 'Reflections, Thames' },
  { rel: 'nocturne/hiroshige-bikuni-bridge-snow.yaml',         display_title: 'Bikunibashi Bridge' },
  { rel: 'nocturne/hiroshige-fox-fires-oji.yaml',              display_title: 'Fox Fires, Ōji' },
  { rel: 'nocturne/hiroshige-kinryuzan-night-snow.yaml',       display_title: 'Kinryūzan in Snow' },
  { rel: 'nocturne/hiroshige-saruwakamachi-night.yaml',        display_title: 'Saruwaka-machi Night' },
  { rel: 'nocturne/hiroshige-takanawa-autumn-moon.yaml',       display_title: 'Takanawa Moon' },
  { rel: 'nocturne/kiyochika-imado-night.yaml',                display_title: 'The Ariakerō, Imado' },
  { rel: 'nocturne/kiyochika-ryogoku-moonlight.yaml',          display_title: 'Fireworks, Ryōgoku' },
  { rel: 'nocturne/whistler-nocturne-blue-gold.yaml',          display_title: 'Nocturne: Blue/Gold' },
  { rel: 'nocturne/whistler-nocturne-falling-rocket.yaml',     display_title: 'Falling Rocket' },

  { rel: 'personal_library/abbott-nyc-changing.yaml',          display_title: 'Changing New York' },
  { rel: 'personal_library/doisneau-baiser-hotel-ville.yaml',  display_title: 'Le Baiser, 1950' },
  { rel: 'personal_library/hcb-behind-gare-saint-lazare.yaml', display_title: 'Gare St-Lazare' },
  { rel: 'personal_library/hcb-sunday-marne.yaml',             display_title: 'Sunday on the Marne' },
  { rel: 'personal_library/warhol-blotted-line-portrait.yaml', display_title: 'Blotted Line' },
];

const TITLE_CAP = 20;
for (const o of OVERRIDES) {
  const len = [...o.display_title].length;
  if (len > TITLE_CAP) {
    console.error(`OVER CAP: ${o.rel} → "${o.display_title}" (${len} chars)`);
    process.exit(1);
  }
}

const FIX = process.argv.includes('--fix');
let updated = 0;
for (const o of OVERRIDES) {
  const filepath = path.join(CORPUS, o.rel);
  const raw = await fs.readFile(filepath, 'utf8');
  const re = /^display_title:.*$/m;
  if (!re.test(raw)) {
    console.error(`SKIP (no display_title to replace): ${o.rel}`);
    continue;
  }
  const replaced = raw.replace(re, `display_title: "${o.display_title.replace(/"/g, '\\"')}"`);
  console.log(`  ${o.rel.padEnd(60)} → "${o.display_title}" (${[...o.display_title].length})`);
  if (FIX) {
    await fs.writeFile(filepath, replaced);
    updated++;
  }
}

if (FIX) console.log(`\n[recurate] updated ${updated} files`);
else console.log(`\n(Run with --fix to apply.)`);

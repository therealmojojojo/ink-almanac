/**
 * Unit tests for the classical-vs-pop gate in `renderer/src/enrichment/classify.ts`.
 *
 * Regression coverage for the misclassification observed in cache on
 * 2026-05-10: every recent rock/folk track came back `classical: true`
 * because (a) any MB work-rel composer was treated as a classical signal and
 * (b) MB artist type "Group" was lumped in with Orchestra/Choir. Plus
 * Spotify's stock " - Remastered 2021" / " - Live" suffixes leaked into the
 * work title.
 */
import { describe, expect, it } from 'vitest';
import { cleanSpotifyTitle, isClassical, roleFor } from '../src/enrichment/classify.js';
import type { MbArtistRef, MbRecording } from '../src/enrichment/musicbrainz.js';

const ref = (over: Partial<MbArtistRef>): MbArtistRef => ({ id: 'x', name: 'x', ...over });

describe('cleanSpotifyTitle — hyphen form (track titles)', () => {
  it('strips " - Remastered YYYY"', () => {
    expect(cleanSpotifyTitle('House With No Door - Remastered 2021')).toBe('House With No Door');
  });
  it('strips " - YYYY Remaster"', () => {
    expect(cleanSpotifyTitle('Heroes - 2017 Remaster')).toBe('Heroes');
  });
  it('strips " - YYYY Remaster" (Red Right Hand regression)', () => {
    expect(cleanSpotifyTitle('Red Right Hand - 2021 Remaster')).toBe('Red Right Hand');
  });
  it('strips " - Live"', () => {
    expect(cleanSpotifyTitle('II. Allegro molto - Live')).toBe('II. Allegro molto');
  });
  it('strips " - Live at <venue>"', () => {
    expect(cleanSpotifyTitle('Pale Blue Eyes - Live at Max\'s Kansas City')).toBe('Pale Blue Eyes');
  });
  it('strips " - Mono Version"', () => {
    expect(cleanSpotifyTitle('Eleanor Rigby - Mono Version')).toBe('Eleanor Rigby');
  });
  it('strips stacked suffixes', () => {
    expect(cleanSpotifyTitle('Track - Remastered 2021 - Live')).toBe('Track');
  });
  it('leaves legitimate hyphenated titles alone', () => {
    expect(cleanSpotifyTitle('Comfortably Numb - Pulse')).toBe('Comfortably Numb - Pulse');
    expect(cleanSpotifyTitle('Symphony No. 5 in C Minor')).toBe('Symphony No. 5 in C Minor');
  });
});

describe('cleanSpotifyTitle — parenthetical form (album names)', () => {
  it('strips "(YYYY - Remaster)" (The Boatman\'s Call regression)', () => {
    expect(cleanSpotifyTitle("The Boatman's Call (2011 - Remaster)")).toBe("The Boatman's Call");
  });
  it('strips "(Remastered)"', () => {
    expect(cleanSpotifyTitle('Abbey Road (Remastered)')).toBe('Abbey Road');
  });
  it('strips "(YYYY Remaster)"', () => {
    expect(cleanSpotifyTitle('Abbey Road (2009 Remaster)')).toBe('Abbey Road');
  });
  it('strips "(Remastered Version)"', () => {
    expect(cleanSpotifyTitle('Dark Side of the Moon (Remastered Version)')).toBe('Dark Side of the Moon');
  });
  it('strips "(Deluxe Edition)"', () => {
    expect(cleanSpotifyTitle('OK Computer (Deluxe Edition)')).toBe('OK Computer');
  });
  it('strips "(Anniversary Edition)"', () => {
    expect(cleanSpotifyTitle("Sgt. Pepper's (Anniversary Edition)")).toBe("Sgt. Pepper's");
  });
  it('leaves legitimate parentheticals alone', () => {
    expect(cleanSpotifyTitle('Symphony No. 9 (Choral)')).toBe('Symphony No. 9 (Choral)');
    expect(cleanSpotifyTitle('Pet Sounds (Original)')).toBe('Pet Sounds (Original)');
  });
});

describe('isClassical — regression cases (rock/folk must NOT classify as classical)', () => {
  it('Nick Drake — Place To Be (composer present, no work type, non-classical title)', () => {
    expect(isClassical({
      mbWorkType: 'Song',
      mbWorkComposer: 'Nick Drake',
      spotifyArtists: [{ name: 'Nick Drake' }],
      spotifyTitle: 'Place To Be',
    })).toBe(false);
  });

  it('David Bowie — Rock ’n’ Roll Suicide (composer present, work typed Song)', () => {
    expect(isClassical({
      mbWorkType: 'Song',
      mbWorkComposer: 'David Bowie',
      spotifyArtists: [{ name: 'David Bowie' }],
      spotifyTitle: 'Rock ’n’ Roll Suicide',
    })).toBe(false);
  });

  it('Velvet Underground — Pale Blue Eyes (composer present + Group artist type)', () => {
    const recording: MbRecording = {
      id: 'r1',
      title: 'Pale Blue Eyes',
      'artist-credit': [{ name: 'The Velvet Underground', artist: ref({ name: 'The Velvet Underground', type: 'Group' }) }],
    };
    expect(isClassical({
      mbWorkType: 'Song',
      mbWorkComposer: 'Lou Reed',
      recording,
      spotifyArtists: [{ name: 'The Velvet Underground' }],
      spotifyTitle: 'Pale Blue Eyes',
    })).toBe(false);
  });

  it('Van der Graaf Generator — House With No Door (Group, untyped work, plain title)', () => {
    const recording: MbRecording = {
      id: 'r2',
      title: 'House With No Door',
      'artist-credit': [{ name: 'Van der Graaf Generator', artist: ref({ name: 'Van der Graaf Generator', type: 'Group' }) }],
    };
    expect(isClassical({
      recording,
      spotifyArtists: [{ name: 'Van der Graaf Generator' }],
      spotifyTitle: 'House With No Door',
    })).toBe(false);
  });
});

describe('isClassical — true classical must still classify as classical', () => {
  it('Shostakovich String Quartet w/ Emerson Quartet (typed work + composer)', () => {
    const recording: MbRecording = {
      id: 'r3',
      title: 'String Quartet No. 8 in C Minor, Op. 110: II. Allegro molto',
      'artist-credit': [{ name: 'Emerson String Quartet', artist: ref({ name: 'Emerson String Quartet', type: 'Group' }) }],
    };
    expect(isClassical({
      mbWorkType: 'Quartet',
      mbWorkComposer: 'Dmitri Shostakovich',
      recording,
      spotifyArtists: [{ name: 'Dmitri Shostakovich' }, { name: 'Emerson String Quartet' }],
      spotifyTitle: 'String Quartet No. 8 in C Minor, Op. 110: II. Allegro molto',
    })).toBe(true);
  });

  it('Untyped MB work but unmistakably classical title (Satie Gnossienne)', () => {
    expect(isClassical({
      mbWorkType: null,
      mbWorkComposer: 'Erik Satie',
      spotifyArtists: [{ name: 'Erik Satie' }, { name: 'Pascal Rogé' }],
      spotifyTitle: 'Gnossienne No. 1',
    })).toBe(true);
  });

  it('Pianist disambiguation alone fires the classical gate', () => {
    const recording: MbRecording = {
      id: 'r4',
      title: 'Nocturne',
      'artist-credit': [{ name: 'Some Pianist', artist: ref({ name: 'Some Pianist', type: 'Person', disambiguation: 'pianist' }) }],
    };
    expect(isClassical({ recording, spotifyTitle: 'Nocturne' })).toBe(true);
  });

  it('Orchestra ensemble fires the classical gate', () => {
    const recording: MbRecording = {
      id: 'r5',
      title: 'Symphony No. 9',
      'artist-credit': [{ name: 'Berlin Phil', artist: ref({ name: 'Berlin Phil', type: 'Orchestra' }) }],
    };
    expect(isClassical({ recording, spotifyTitle: 'Symphony No. 9' })).toBe(true);
  });

  it('Two Spotify artists + classical title shape (no MB recording)', () => {
    expect(isClassical({
      spotifyArtists: [{ name: 'Chopin' }, { name: 'Some Performer' }],
      spotifyTitle: 'Nocturne in B-Flat Minor, Op. 9 No. 1',
    })).toBe(true);
  });
});

describe('roleFor — Group is no longer a special-cased ensemble', () => {
  it('Orchestra returns empty (ensemble baked into name)', () => {
    expect(roleFor(ref({ type: 'Orchestra' }))).toBe('');
  });
  it('Choir returns empty (ensemble baked into name)', () => {
    expect(roleFor(ref({ type: 'Choir' }))).toBe('');
  });
  it('Group with no instrument disambiguation returns empty (no role to display)', () => {
    expect(roleFor(ref({ type: 'Group' }))).toBe('');
  });
  it('Group with cellist disambiguation returns Cello (very rare but possible)', () => {
    expect(roleFor(ref({ type: 'Group', disambiguation: 'cellist quartet' }))).toBe('Cello');
  });
});

describe('roleFor — conductor vs instrument disambiguation', () => {
  // Regression: Barenboim performing solo Liszt was tagged "Cond." because
  // his disambiguation reads "pianist and conductor" and the conductor
  // regex used to win. On a recording with no ensemble in the credits,
  // the instrument should win.
  const barenboim = ref({ type: 'Person', disambiguation: 'pianist and conductor', name: 'Daniel Barenboim' });
  const karajan = ref({ type: 'Person', disambiguation: 'Austrian conductor', name: 'Herbert von Karajan' });

  it('"pianist and conductor" on a soloist recording → Piano', () => {
    expect(roleFor(barenboim, /* hasEnsemble */ false)).toBe('Piano');
  });

  it('"pianist and conductor" on a recording with an orchestra → Cond.', () => {
    expect(roleFor(barenboim, /* hasEnsemble */ true)).toBe('Cond.');
  });

  it('Pure conductor disambiguation → Cond. regardless of ensemble flag', () => {
    expect(roleFor(karajan, /* hasEnsemble */ false)).toBe('Cond.');
    expect(roleFor(karajan, /* hasEnsemble */ true)).toBe('Cond.');
  });

  it('"violinist and conductor" on a soloist recording → Violin', () => {
    const oistrakh = ref({ type: 'Person', disambiguation: 'Soviet violinist and conductor' });
    expect(roleFor(oistrakh, false)).toBe('Violin');
  });

  it('Defaults to no-ensemble when called without the flag (back-compat)', () => {
    expect(roleFor(barenboim)).toBe('Piano');
  });
});

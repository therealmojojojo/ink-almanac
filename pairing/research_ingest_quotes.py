"""Ingest the 43 hand-curated famous-quotes entries as proper corpus sidecars.

Source: openspec/changes/expand-summary-pool/lists/famous-quotes-curated.json
Target: corpus/texts/ (public_domain) or corpus/personal_library/ (in copyright)

Each entry gets a full sidecar: id, title, author, year, rights_tier, source,
source_url, citation (PL only), form, language, text_variants, themes, mood,
register, added, smart_pill { body, generated_at, model }.

Smart pills are hand-authored, ≤440 chars, no formulaic openers (no 'Published
in YYYY', 'From X's', etc.). Each pill leads with the *move* — the technical
or poetic device that makes the line work.

After running:
  corpus validate          # confirm structural pass
  python pairing/corpus_analyze.py    # confirm tier predictions
"""
from __future__ import annotations

import json, re, sys
from datetime import date
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "openspec/changes/expand-summary-pool/lists/famous-quotes-curated.json"
TODAY = date.today().isoformat()

# Per-entry ingestion metadata, indexed by 0-based position in the curated JSON.
# Each entry: id, form, rights, themes, mood, register, citation (PL only), pill.
INGESTION: dict[int, dict] = {
    0: {  # Pope, To err is human
        "id": "pope-essay-criticism-to-err-is-human",
        "form": "aphorism", "rights": "public_domain",
        "themes": ["everyday-life", "tender-companionship"], "mood": ["wry", "warm"],
        "register": ["aphoristic", "classical"],
        "pill": "The pivot is the chiastic *and*. Pope sets up two human qualities, splits the line at the semicolon, and the second half of each — *Sense* and *Forgive* — is the active virtue while the first half — *Nature* and *err* — is the given condition. The couplet's force comes from refusing to flatter; forgiveness is divine precisely because it costs the forgiver something.",
    },
    1: {  # Pope, A little learning
        "id": "pope-essay-criticism-little-learning",
        "form": "fragment", "rights": "public_domain",
        "themes": ["reading-and-study", "attention-and-listening"],
        "mood": ["wry", "stoic"], "register": ["aphoristic", "classical"],
        "pill": "The image is the *Pierian Spring*, sacred to the Muses in Macedonia. Pope's warning is hydraulic: *shallow Draughts intoxicate* — a small pull from the spring leaves you reeling, mistaking dizziness for inspiration. *Drinking largely sobers us again* — only a deep draught restores judgment. Knowledge is dangerous in the half-measure, not in the full one.",
    },
    2: {  # Pope, Hope springs eternal
        "id": "pope-essay-on-man-hope-springs-eternal",
        "form": "fragment", "rights": "public_domain",
        "themes": ["mortality", "everyday-life"], "mood": ["wistful", "stoic"],
        "register": ["aphoristic", "classical"],
        "pill": "The grammatical pivot is *Is* and *To be*. Pope capitalizes both as if naming forms of being. Man is denied the present tense (*never Is*) but granted the future infinitive (*always To be blest*). Hope, in this scheme, isn't an emotion — it's the structural condition of being human, the gap between what we are and what we wait to become.",
    },
    3: {  # Yeats, Things fall apart
        "id": "yeats-second-coming-opening",
        "form": "stanzaic", "rights": "public_domain",
        "themes": ["mortality", "decay-and-memory"], "mood": ["grim", "haunting"],
        "register": ["oracular", "iconic"],
        "pill": "The image is the *gyre* — Yeats's spiral, used here as the falconer's lure pattern. The hawk circles wider with each pass until it can no longer hear the call. Civilization, Yeats argues in *A Vision*, follows the same widening orbit: each cycle loosens the centre's grip on the periphery until the binding fails. The poem's first four lines are a single sentence enacting that loss.",
    },
    4: {  # Keats, Beauty is truth
        "id": "keats-grecian-urn-closing",
        "form": "fragment", "rights": "public_domain",
        "themes": ["mortality", "decay-and-memory", "attention-and-listening"],
        "mood": ["contemplative", "haunting"],
        "register": ["lyric", "oracular"],
        "pill": "The line is spoken by the *urn*, not by Keats — the inverted commas are essential. After eighty lines of the poet questioning the silent pot, the pot finally answers, and its answer is a tautology. Critics have argued for two centuries whether the urn is wise or empty. The line's power is that it refuses to settle: spoken by an artifact, addressed to humans, it stands outside the dialogue it ends.",
    },
    5: {  # Kipling, If—
        "id": "kipling-if-opening",
        "form": "stanzaic", "rights": "public_domain",
        "themes": ["solitude", "everyday-life"], "mood": ["stoic", "self-possessed"],
        "register": ["aphoristic", "formal"],
        "pill": "The poem is one 32-line conditional sentence — *If… If… If… you'll be a Man*. The grammar is the discipline: every virtue is conditional, every payoff deferred. Kipling wrote it for his son John (killed seven years later in WWI), modeling not stoicism as posture but as practice — *trust yourself when all men doubt you, but make allowance for their doubting too*. The qualification is the point.",
    },
    6: {  # Kipling, East and West
        "id": "kipling-east-west-opening",
        "form": "stanzaic", "rights": "public_domain",
        "themes": ["journey", "mortality"], "mood": ["grave", "stoic"],
        "register": ["formal", "classical"],
        "pill": "The popular cut at *meet* inverts the poem. Kipling's structure is a refrain plus its negation: lines 1-2 state the geographic certainty, lines 3-4 dissolve it into character — *neither East nor West, Border, nor Breed, nor Birth, when two strong men stand face to face*. The whole ballad that follows is one such meeting between an English colonel's son and an Afghan raider; they part as equals.",
    },
    7: {  # Milton, Mind is its own place
        "id": "milton-paradise-lost-mind-is-its-own-place",
        "form": "fragment", "rights": "public_domain",
        "themes": ["solitude", "mortality"], "mood": ["grim", "stoic"],
        "register": ["oracular", "classical"],
        "pill": "Spoken by *Satan* on the burning lake of Hell, after his fall. The proposition is a self-deception dressed as freedom: if mind makes its own place, then exile is voluntary, defeat is choice. Milton lets Satan have the rhetoric — the chiasmus *Heav'n of Hell, Hell of Heav'n* is genuinely beautiful — while the surrounding 600 lines slowly reveal that Hell is, in fact, a place, and Satan is in it.",
    },
    8: {  # Milton, Better to reign in Hell
        "id": "milton-paradise-lost-better-to-reign-in-hell",
        "form": "fragment", "rights": "public_domain",
        "themes": ["solitude", "mortality"], "mood": ["grim", "stoic"],
        "register": ["oracular", "classical"],
        "pill": "The line completes Satan's first speech. *Reign* is the load-bearing verb, used twice. Hell is acceptable because it permits sovereignty; Heaven is rejected because it demands service. Milton's Satan is the prototype of the modern anti-hero — the figure who would rather be the monarch of his diminishment than a subject of any greater good. Romantic readers (Blake, Shelley) loved him for it; Milton meant the love to be tragic.",
    },
    9: {  # Owen, Dulce et Decorum Est
        "id": "owen-dulce-decorum-est-closing",
        "form": "fragment", "rights": "public_domain",
        "themes": ["mortality", "machines-and-mechanisms"], "mood": ["grim", "raw"],
        "register": ["confessional", "documentary"],
        "pill": "The Latin is from Horace's *Odes* III.2.13 — *sweet and fitting to die for one's country*. Owen takes the schoolroom maxim and detonates it. The capital *L* in *Lie* is the move: not a falsehood (lowercase, particular) but a Lie (uppercase, mythic). The popular quote that strips out *The old Lie* and prints only the Latin tag does to Owen exactly what Owen accuses the schoolmasters of doing to children.",
    },
    10: {  # McCrae, In Flanders Fields
        "id": "mccrae-in-flanders-fields-opening",
        "form": "stanzaic", "rights": "public_domain",
        "themes": ["mortality", "rural-pastoral", "ritual-and-gathering"],
        "mood": ["grave", "haunting"], "register": ["formal", "lyric"],
        "pill": "The form is *rondeau* — McCrae's choice is exact. The rondeau's recurring refrain (*In Flanders fields*) lets the poem turn back on itself like the recurrence of seasons over the graves it describes. Written in 20 minutes after burying a friend at Ypres in 1915. The poppies were already there, weeds that thrived on the disturbed earth above each new burial — McCrae did not invent the symbol, he registered it.",
    },
    11: {  # Hamlet, lady doth protest
        "id": "shakespeare-hamlet-lady-doth-protest",
        "form": "quote", "rights": "public_domain",
        "themes": ["attention-and-listening"], "mood": ["wry", "ironic"],
        "register": ["aphoristic", "iconic"],
        "pill": "*Protest* in Elizabethan English meant *vow* or *affirm*, not *object*. Gertrude is watching the Player Queen swear undying devotion in the play-within-the-play and remarking that the Player Queen overdoes her vows. The popular reading — that someone who denies a charge too vehemently confirms it — is a clean inversion of the original sense. The phrase has now meant the inversion longer than it meant Shakespeare's intent.",
    },
    12: {  # King John, gild refined gold
        "id": "shakespeare-king-john-gild-refined-gold",
        "form": "fragment", "rights": "public_domain",
        "themes": ["everyday-life", "garden-and-grove"], "mood": ["wry", "deadpan"],
        "register": ["aphoristic", "classical"],
        "pill": "The popular abbreviation *gild the lily* fuses two of Shakespeare's parallel actions into one impossible compound. Salisbury's catalog gives six examples of *wasteful and ridiculous excess* — gilding gold, painting the lily, perfuming the violet, smoothing ice, recoloring the rainbow, lighting heaven's eye with a candle. Each is a separate absurdity. Combining them produces a gardening gaffe that Shakespeare did not write.",
    },
    13: {  # Twelfth Night
        "id": "shakespeare-twelfth-night-music-food-of-love",
        "form": "fragment", "rights": "public_domain",
        "themes": ["everyday-life", "tender-companionship"], "mood": ["melancholic", "wistful"],
        "register": ["lyric", "iconic"],
        "pill": "Orsino opens the play wanting to *kill* his love by overfeeding it. The metaphor is digestive — *surfeiting, the appetite may sicken, and so die* — and the strategy is self-defeating: Orsino is in love with the idea of being in love, and the more music he hears the deeper the appetite goes. The play that follows is a catalog of his failures to cure himself by indulgence; only Viola, in disguise, manages to redirect him.",
    },
    14: {  # Henry V, We few
        "id": "shakespeare-henry-v-band-of-brothers",
        "form": "fragment", "rights": "public_domain",
        "themes": ["ritual-and-gathering", "tender-companionship"],
        "mood": ["warm", "stoic"], "register": ["formal", "iconic"],
        "pill": "The trick is the temporary equality. *He to-day that sheds his blood with me / Shall be my brother* — for one day, on St Crispin's, the social distance between king and yeoman collapses into shared mortality. The morning after Agincourt the hierarchy resumes; Henry knows this, his men know this, and the brotherhood is more powerful for being explicitly bounded. Modern readings often miss the deadline.",
    },
    15: {  # Julius Caesar, Friends Romans
        "id": "shakespeare-julius-caesar-lend-me-your-ears",
        "form": "fragment", "rights": "public_domain",
        "themes": ["ritual-and-gathering", "mortality"],
        "mood": ["wry", "grave"], "register": ["formal", "iconic"],
        "pill": "The opening is a setup for ironic reversal. Antony swears he comes to *bury Caesar, not to praise him* — and then spends 130 lines praising Caesar so effectively that the crowd riots against the conspirators by the end. *The good is oft interred with their bones* is the warrant Antony gives himself for digging the good back up. The whole speech is a master class in saying the opposite of what you mean and being believed.",
    },
    16: {  # Merchant, quality of mercy
        "id": "shakespeare-merchant-venice-quality-of-mercy",
        "form": "fragment", "rights": "public_domain",
        "themes": ["ritual-and-gathering", "tender-companionship"],
        "mood": ["serene", "tender"], "register": ["formal", "lyric"],
        "pill": "*Strain'd* means *constrained, forced* — not stretched. Portia's argument is that mercy by definition cannot be compelled; if it could be, it would not be mercy. The hydraulic image (*droppeth as the gentle rain from heaven*) makes mercy meteorological — a gift from outside the contract, sovereign because it owes nothing. Shylock's refusal of mercy in this scene is a refusal of grace itself.",
    },
    17: {  # Romeo and Juliet
        "id": "shakespeare-romeo-juliet-wherefore-art-thou",
        "form": "fragment", "rights": "public_domain",
        "themes": ["solitude", "tender-companionship"],
        "mood": ["wistful", "tender"], "register": ["lyric", "iconic"],
        "pill": "*Wherefore* means *why*, not *where* — the line is a complaint about Romeo's identity, not a search for his location. Juliet, alone on the balcony, is wishing he were not a Montague. The next four lines spell it out: *Deny thy father and refuse thy name* — i.e., be someone else, anyone else. The frequency with which the line is misperformed as a search reveals how language drift can erase a play's emotional architecture.",
    },
    18: {  # Macbeth, Double double
        "id": "shakespeare-macbeth-double-double",
        "form": "quote", "rights": "public_domain",
        "themes": ["ritual-and-gathering", "night-and-lamplight"],
        "mood": ["grim", "uncanny"], "register": ["formal", "iconic"],
        "pill": "The chant is *trochaic tetrameter* — a meter Shakespeare used almost only for the Witches and for the fairies in *Midsummer*. The trochee (*DUM-da*) inverts the iambic foot of normal speech, marking the speakers as outside the social order. The doubled vowels (*Double, double*) and the rhyme (*trouble / bubble*) push toward incantation, not communication; the meaning matters less than the meter's spell.",
    },
    19: {  # Hamlet, To be
        "id": "shakespeare-hamlet-to-be-or-not-to-be",
        "form": "fragment", "rights": "public_domain",
        "themes": ["solitude", "mortality"],
        "mood": ["contemplative", "grim"], "register": ["formal", "iconic"],
        "pill": "Not *should I die* but *should I exist* — the verb *to be* is the largest available. Hamlet weighs *suffering the slings and arrows* (passive endurance) against *taking arms against a sea of troubles* (active resistance), and lands on *by opposing end them* — where *end* fuses two senses (terminate the troubles, terminate the self). The soliloquy's force is in refusing to resolve which sense is operative.",
    },
    20: {  # Donne, Sun Rising
        "id": "donne-sun-rising-opening",
        "form": "stanzaic", "rights": "public_domain",
        "themes": ["interior-and-domestic", "morning", "tender-companionship"],
        "mood": ["wry", "warm"], "register": ["lyric", "intimate"],
        "pill": "The metaphysical conceit is that two lovers in bed *are* the world — and the sun, by arriving at the bedroom window, is interrupting the actual cosmos by reporting on a model of it. Donne addresses the sun as *busy old fool*, demoting the celestial to the domestic. The poem's argument across three stanzas is that the bedroom is large and the sun small; by the closing line the lovers have absorbed the universe.",
    },
    21: {  # Whitman, Song of Myself opening
        "id": "whitman-song-of-myself-opening",
        "form": "fragment", "rights": "public_domain",
        "themes": ["solitude", "everyday-life"],
        "mood": ["warm", "self-possessed"], "register": ["confessional", "lyric"],
        "pill": "The audacity is the *and*. *I celebrate myself, and sing myself* — and then, with no rhetorical preparation, *what I assume you shall assume*. Whitman extends the first-person *I* outward to enroll the reader. The justification arrives in line three as physics: every atom of mine is also yours. The poem's hundreds of catalogs that follow are warranted by this opening claim of constitutional equality at the atomic level.",
    },
    22: {  # Whitman, Do I contradict
        "id": "whitman-song-of-myself-multitudes",
        "form": "fragment", "rights": "public_domain",
        "themes": ["solitude", "everyday-life"],
        "mood": ["self-possessed", "warm"], "register": ["aphoristic", "lyric"],
        "pill": "The parenthetical is the move. *I am large, I contain multitudes* sounds like a boast but is offered in brackets — Whitman tucks the largest claim of the poem into an aside. The structure mirrors the meaning: a self that contradicts itself isn't fragmented, it's *capacious* enough to hold the contradictions. The line answers in advance every charge of inconsistency, including the ones Whitman knew critics would bring.",
    },
    23: {  # Whitman, O Captain
        "id": "whitman-o-captain-opening",
        "form": "stanzaic", "rights": "public_domain",
        "themes": ["mortality", "ritual-and-gathering", "sea-and-sky"],
        "mood": ["grave", "haunting"], "register": ["formal", "lyric"],
        "pill": "An elegy for Lincoln (April 1865) cast in nautical apostrophe. The ship is the Union, the *fearful trip* is the Civil War, the prize is preserved national survival. Whitman, who usually rejected formal meter, used here a strict iambic with rhyme — a public elegy needs a public form. The contrast in the closing stanzas (the Captain dead on the deck while the bells ring victory) borrows directly from classical apotheosis.",
    },
    24: {  # Whitman, Body Electric
        "id": "whitman-i-sing-the-body-electric-opening",
        "form": "stanzaic", "rights": "public_domain",
        "themes": ["body-and-figure", "tender-companionship"],
        "mood": ["warm", "ecstatic"], "register": ["confessional", "lyric"],
        "pill": "*Engirth* is Whitman's coinage — to circle, to enclose with arms. Reciprocal: those he loves circle him; he circles them. The body in Whitman is never a vessel for soul; it *is* soul. *Discorrupt* is also coined, the negation of *corrupt* — to undo decay rather than prevent it. The poem's nine sections that follow are an inventory of body parts treated as equal in dignity, an early democratic anatomy.",
    },
    25: {  # Angelou, Still I Rise
        "id": "angelou-still-i-rise-opening-quatrain",
        "form": "stanzaic", "rights": "personal_library",
        "citation": "Angelou, *And Still I Rise*, Random House, 1978",
        "themes": ["solitude", "mortality"],
        "mood": ["self-possessed", "stoic"], "register": ["confessional", "iconic"],
        "pill": "The trick is the simile *like dust*. Angelou could have written *like fire* or *like a phoenix* — both are in the poem's later stanzas — but she opens with the most despised material in the speaker's environment. Dust is what gets *trod* and swept aside; choosing it as the rising medium reverses the contempt. The rhyme *lies / rise* is half-internal, half-end — the structure refuses to let the lies and the rising stand apart.",
    },
    26: {  # Plath, Lady Lazarus
        "id": "plath-lady-lazarus-closing",
        "form": "fragment", "rights": "personal_library",
        "citation": "Plath, *Ariel*, Harper & Row, 1965 (posthumous)",
        "themes": ["mortality", "body-and-figure"],
        "mood": ["raw", "grim"], "register": ["confessional", "iconic"],
        "pill": "The closing tercet is the speaker's resurrection threat. *Out of the ash* echoes the phoenix; *red hair* names Plath's own; *eat men like air* turns the predator-prey relation inside out — air, the most necessary substance, becomes the food. The line is often quoted as feminist swagger, but in the poem it follows seven pages of staged suicide as performance art. The triumph is conditional on the dying.",
    },
    27: {  # Poe, Quoth the Raven
        "id": "poe-raven-nevermore-refrain",
        "form": "quote", "rights": "public_domain",
        "themes": ["mortality", "night-and-lamplight"],
        "mood": ["grim", "haunting"], "register": ["iconic", "lyric"],
        "pill": "*Nevermore* arrives eleven times across the poem — first as the bird's accidental answer, then as the speaker's deliberate solicitation. The narrator asks ever more devastating questions (will he see Lenore again, will his soul find rest) knowing the answer in advance, because *Nevermore* is the only word the bird knows. The horror isn't the bird's prophecy; it's the speaker's compulsion to keep asking.",
    },
    28: {  # Poe, Once upon a midnight
        "id": "poe-raven-opening-quatrain",
        "form": "stanzaic", "rights": "public_domain",
        "themes": ["night-and-lamplight", "reading-and-study", "solitude"],
        "mood": ["haunting", "atmospheric"], "register": ["lyric", "iconic"],
        "pill": "The meter is *trochaic octameter* — eight feet of *DUM-da* per line — which Poe defended at length in *The Philosophy of Composition*. The internal rhyme (*dreary / weary*, *napping / tapping / rapping*) plus the cascading subordinations (*while I pondered / over many a volume / while I nodded*) build a hypnotic loop. By the time the tapping arrives, the reader is already in the speaker's drowsy state.",
    },
    29: {  # FitzGerald-Khayyam, Moving Finger
        "id": "khayyam-fitzgerald-moving-finger",
        "form": "stanzaic", "rights": "public_domain",
        "themes": ["mortality", "decay-and-memory"],
        "mood": ["stoic", "wistful"], "register": ["aphoristic", "classical"],
        "pill": "The image is *fate as scribe* — but the script can't be revised once laid down. *Piety* and *Wit* are FitzGerald's glosses for the two human strategies against fate: prayer (asking for revision) and cleverness (engineering a workaround). Both fail. The quatrain's elegiac couplet form (rubai) gives the determinism a pleasant rhythm; you can resign yourself to fate more easily when fate scans this well.",
    },
    30: {  # FitzGerald-Khayyam, Jug of Wine
        "id": "khayyam-fitzgerald-jug-of-wine",
        "form": "stanzaic", "rights": "public_domain",
        "themes": ["tender-companionship", "rural-pastoral", "everyday-life"],
        "mood": ["warm", "tender"], "register": ["lyric", "intimate"],
        "pill": "The capitalized *Thou* is the centerpiece — the verses, the wine, and the bread are all preliminaries. FitzGerald's translation is famously loose (Persian scholars argue it's a paraphrase rather than translation), but the recipe for an earthly Paradise is unmistakable: book, drink, food, companion, wilderness. The order matters — the *Thou* arrives last and the *Wilderness* gets the last word, made into Paradise by the company.",
    },
    31: {  # Catullus 85
        "id": "catullus-carmen-85",
        "form": "aphorism", "rights": "public_domain",
        "themes": ["solitude", "tender-companionship", "mortality"],
        "mood": ["raw", "grim"], "register": ["confessional", "classical"],
        "pill": "The complete poem is a single elegiac couplet — hexameter then pentameter, the meter Catullus borrowed from Greek love-elegy. *Excrucior* literally means *I am crucified* (from *crux*, the cross), but in classical Latin the verb's force is closer to *I am stretched apart on a frame*. Catullus invents the modern emotional vocabulary in two lines: love that knows itself as suffering, and refuses either to renounce or to explain.",
    },
    32: {  # Horace I.11
        "id": "horace-odes-i-11-carpe-diem",
        "form": "fragment", "rights": "public_domain",
        "themes": ["mortality", "everyday-life"],
        "mood": ["stoic", "wistful"], "register": ["aphoristic", "classical"],
        "pill": "*Carpe* is from *carpere*, to *pluck* — the metaphor is horticultural, not military. Horace is addressing Leuconoë; the day is a fruit on the vine, ready to come away cleanly if you take it now and going to drop and rot if you don't. *Quam minimum credula postero* — *trusting tomorrow as little as you can* — is the ode's logical engine. The familiar English imperative *seize the day* hardens what was, in Horace, a gentle picking.",
    },
    33: {  # Horace III.30
        "id": "horace-odes-iii-30-exegi-monumentum",
        "form": "fragment", "rights": "public_domain",
        "themes": ["decay-and-memory", "mortality", "architecture-and-structure"],
        "mood": ["self-possessed", "stoic"], "register": ["formal", "classical"],
        "pill": "Horace closes Book III with an explicit boast about his own poems — they outlast bronze, exceed the pyramids, withstand rain and northern wind. The conceit is materialist: poetry has a longer half-life than the most durable physical materials Rome knew. Two thousand years on, the boast turned out to be true — Horace's Odes survive while every Augustan-era bronze is melted down and the pyramids weather. The poem is its own evidence.",
    },
    34: {  # Macbeth, Out brief candle
        "id": "shakespeare-macbeth-out-brief-candle",
        "form": "fragment", "rights": "public_domain",
        "themes": ["mortality", "night-and-lamplight"],
        "mood": ["grim", "stoic"], "register": ["formal", "iconic"],
        "pill": "Macbeth has just been told his wife is dead. The metaphor is theatrical: life is a candle (briefly burning), then a *poor player* (briefly strutting), then a *tale told by an idiot* (briefly told, signifying nothing). Each metaphor compresses the previous one into something more contemptible. The speech is Shakespeare's bleakest because Macbeth, whose ambition drove the play, no longer believes in the value of what his ambition produced.",
    },
    35: {  # Macbeth, Tomorrow
        "id": "shakespeare-macbeth-tomorrow-and-tomorrow",
        "form": "fragment", "rights": "public_domain",
        "themes": ["mortality", "everyday-life"],
        "mood": ["grim", "stoic"], "register": ["formal", "iconic"],
        "pill": "The trick is the verb *creeps* — Macbeth's despair is that time itself moves, but slowly, with no urgency, *in this petty pace*. The triple repetition (*tomorrow, and tomorrow, and tomorrow*) enacts the monotony it names; each reiteration of the word adds nothing because tomorrow adds nothing. *To the last syllable of recorded time* turns time into language — and language, like time, just keeps spelling itself out.",
    },
    36: {  # As You Like It
        "id": "shakespeare-as-you-like-it-all-the-worlds-a-stage",
        "form": "fragment", "rights": "public_domain",
        "themes": ["mortality", "everyday-life"],
        "mood": ["wry", "wistful"], "register": ["aphoristic", "iconic"],
        "pill": "Spoken by Jaques, the play's professional melancholic — Shakespeare gives the stage-of-life conceit to the character whose detachment makes it possible. The speech's seven ages (infant, schoolboy, lover, soldier, justice, lean and slippered pantaloon, second childishness) are each given two or three lines of vivid detail. The coolness is the move: a metaphor that should be tragic delivered as observation.",
    },
    37: {  # Cummings
        "id": "cummings-anyone-lived-in-a-pretty-how-town-opening",
        "form": "stanzaic", "rights": "personal_library",
        "citation": "Cummings, *50 Poems*, Duell, Sloan and Pearce, 1940",
        "themes": ["everyday-life", "ritual-and-gathering"],
        "mood": ["playful", "wistful"], "register": ["lyric", "iconic"],
        "pill": "The grammar trick is *anyone* and *noone* (later in the poem) used as proper names. Cummings sets a love story between two people whose names are pronouns of nonexistence, in a town described not by its appearance but by *how* — a placeholder. *He sang his didn't he danced his did* substantivizes the negative and the affirmative as objects you can sing or dance. The poem is a pastoral elegy in linguistic costume.",
    },
    38: {  # Tennyson, Lady of Shalott
        "id": "tennyson-lady-of-shalott-opening",
        "form": "stanzaic", "rights": "public_domain",
        "themes": ["rural-pastoral", "water-and-reflection", "solitude"],
        "mood": ["atmospheric", "serene"], "register": ["lyric", "formal"],
        "pill": "The opening is geographic establishing-shot: river between two banks of barley and rye, fields rising to *the wold* (the open uplands), road running through to *many-tower'd Camelot*. The stanza form is Tennyson's invention for this poem — five lines rhyming AAAAB, with a short fifth line that names Camelot like a refrain. The Lady herself doesn't appear for forty-four more lines; the poem first builds the world she will refuse to leave.",
    },
    39: {  # Yeats, Innisfree
        "id": "yeats-lake-isle-innisfree-opening",
        "form": "stanzaic", "rights": "public_domain",
        "themes": ["solitude", "rural-pastoral", "garden-and-grove"],
        "mood": ["wistful", "serene"], "register": ["lyric", "iconic"],
        "pill": "*Arise and go* is the King James Bible's verb pair (*Luke 15:18*, the Prodigal Son). Yeats borrows the prodigal's diction for a much smaller homecoming — not to a father's house but to a small cabin he plans to build himself, on a lake island in County Sligo, alone. *Bee-loud glade* is the move: a meadow defined by a single auditory texture. The poem is famously about a place Yeats never actually went to live.",
    },
    40: {  # Williams, This Is Just To Say
        "id": "williams-this-is-just-to-say",
        "form": "free-verse", "rights": "personal_library",
        "citation": "Williams, *Collected Poems 1909-1939, Volume I*, New Directions, 1986 (orig. 1934)",
        "themes": ["interior-and-domestic", "everyday-life", "tender-companionship"],
        "mood": ["tender", "wry"], "register": ["confessional", "intimate"],
        "pill": "Williams claimed the poem was a literal note left on the kitchen table. The line breaks turn a domestic confession into something formal: each stanza is one syntactic unit, each unit ends mid-clause to force the eye down. *Forgive me / they were delicious* is the closing bait-and-switch — apology dissolves into appetite. The whole poem is twenty-eight words of refrigerator forensics that has been anthologized for a hundred years.",
    },
    41: {  # Frost, Mending Wall
        "id": "frost-mending-wall-good-fences",
        "form": "fragment", "rights": "public_domain",
        "themes": ["rural-pastoral", "tender-companionship", "everyday-life"],
        "mood": ["wry", "stoic"], "register": ["lyric", "documentary"],
        "pill": "The famous line is the *neighbor's*, not Frost's. Frost spends the whole poem dismantling the saying — *something there is that doesn't love a wall* opens the poem, then he watches the neighbor *like an old-stone savage armed* repeating his father's wisdom unexamined. The narrator wants the neighbor to think it through; the neighbor refuses. The line that gets quoted approvingly is the one Frost is criticizing.",
    },
    42: {  # Niemöller
        "id": "niemoller-first-they-came",
        "form": "stanzaic", "rights": "personal_library",
        "citation": "Niemöller, oral statements c. 1946-1976; canonical English text per US Holocaust Memorial Museum",
        "themes": ["solitude", "ritual-and-gathering", "mortality"],
        "mood": ["grave", "stoic"], "register": ["confessional", "oracular"],
        "pill": "There is no canonical original — Niemöller used many variants in lectures from 1946 onward, sometimes including Catholics, sometimes Communists, always rearranging the order. The structural move is the catalog with terminal collapse: each *I did not speak out* is justified by an exclusion (*I was not a…*) until the speaker himself becomes the excluded one. The argument is that solidarity isn't moral abstraction; it's the only available self-defense.",
    },
}


def write_sidecar(entry: dict, ingestion: dict) -> Path:
    rights = ingestion["rights"]
    folder = "personal_library" if rights == "personal_library" else "texts"
    out_dir = ROOT / "corpus" / folder
    sid = ingestion["id"]
    path = out_dir / f"{sid}.yaml"
    if path.exists():
        raise FileExistsError(f"sidecar already exists: {path.relative_to(ROOT)}")

    body = entry["snippet_in_source"]
    if not body.endswith("\n"):
        body = body + "\n"

    doc: dict = {
        "id": sid,
        "title": entry.get("poem_title") or "(untitled)",
        "author": entry.get("author") or "(unknown)",
        "year": entry.get("year"),
        "rights_tier": rights,
        "source": "wikisource" if "wikisource" in (entry.get("source_text_url") or "") else "web",
        "source_url": entry.get("source_text_url") or "",
        "form": ingestion["form"],
        "language": [entry.get("language") or "en"],
        "text_variants": {entry.get("language") or "en": body},
        "themes": ingestion["themes"],
        "mood": ingestion["mood"],
        "register": ingestion["register"],
        "added": TODAY,
        "smart_pill": {
            "body": ingestion["pill"],
            "generated_at": TODAY,
            "model": "human-curated",
        },
    }
    if rights == "personal_library":
        if "citation" not in ingestion:
            raise ValueError(f"{sid}: personal_library requires citation")
        # Insert citation near the top of the dict for readability — Python 3.7+ preserves insertion order
        ordered = {}
        for k, v in doc.items():
            ordered[k] = v
            if k == "source_url":
                ordered["citation"] = ingestion["citation"]
        doc = ordered

    path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


def main() -> int:
    data = json.loads(SRC.read_text())
    if len(data) != 43:
        print(f"WARNING: expected 43 entries, got {len(data)}", file=sys.stderr)

    by_folder: dict[str, list[str]] = {"texts": [], "personal_library": []}
    errors: list[str] = []
    for i, entry in enumerate(data):
        if i not in INGESTION:
            errors.append(f"  [{i}] no ingestion data: {entry.get('author')} / {entry.get('poem_title')}")
            continue
        ing = INGESTION[i]
        try:
            path = write_sidecar(entry, ing)
            folder = "personal_library" if ing["rights"] == "personal_library" else "texts"
            by_folder[folder].append(path.name)
            print(f"  [{i:2d}] wrote {path.relative_to(ROOT)}")
        except Exception as e:
            errors.append(f"  [{i}] {ing.get('id','?')}: {type(e).__name__}: {e}")

    print(f"\n=== Summary ===")
    print(f"  texts/             : {len(by_folder['texts'])}")
    print(f"  personal_library/  : {len(by_folder['personal_library'])}")
    print(f"  errors             : {len(errors)}")
    for e in errors:
        print(e)
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())

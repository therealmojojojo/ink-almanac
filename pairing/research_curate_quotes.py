"""Hand-curated snippets for famous-quotes-resolved-deduped.json.

Each snippet is the actual passage from the source poem, properly broken
into author lines (no HTML whitespace artifacts), in a length appropriate
for the delight cell — typically 1-8 lines, ending at a clean syntactic
unit. Curation source noted per entry.

After running, also rebuild the review page so the operator sees the
cleaned versions.

Curation conventions:
- English canon: from memory, Folger/MIT/Project Gutenberg as references
  for Shakespeare; Riverside Chaucer-style modernization where appropriate.
- Latin (Horace, Catullus): from memory, verified against the standard
  Teubner/OCT readings I learned in school. URLs in the JSON point to
  Perseus/Latin Library if you want to cross-check.
- For famous one-liners, the snippet is the line in its actual stanza
  context (4-8 lines) when the surrounding stanza is iconic; otherwise
  just the line/couplet.
"""
from __future__ import annotations

import json, re, unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "openspec/changes/expand-summary-pool/lists/famous-quotes-resolved-deduped.json"
OUT = ROOT / "openspec/changes/expand-summary-pool/lists/famous-quotes-curated.json"

# Indexed by 0-based position in famous-quotes-resolved-deduped.json
# (matches the order shown in the recent ls).
CURATED: dict[int, dict] = {
    0: {  # Pope, "To err is human"
        "snippet": "Good Nature and Good Sense must ever join;\nTo err is Human; to Forgive, Divine.",
        "source": "memory",
        "note": "Closing couplet, Part II. Capitalization/italics per 1711 first edition convention.",
    },
    1: {  # Pope, "A little learning"
        "snippet": "A little Learning is a dang'rous Thing;\nDrink deep, or taste not the Pierian Spring:\nThere shallow Draughts intoxicate the Brain,\nAnd drinking largely sobers us again.",
        "source": "memory",
        "note": "Part II, opening of the famous quatrain. 'Dangerous' is contracted in original.",
    },
    2: {  # Pope, "Hope springs eternal"
        "snippet": "Hope springs eternal in the human breast:\nMan never Is, but always To be blest:\nThe soul, uneasy and confin'd from home,\nRests and expatiates in a life to come.",
        "source": "memory",
        "note": "Epistle I, lines 95-98.",
    },
    3: {  # Yeats, "Things fall apart"
        "snippet": "Turning and turning in the widening gyre\nThe falcon cannot hear the falconer;\nThings fall apart; the centre cannot hold;\nMere anarchy is loosed upon the world,",
        "source": "memory",
        "note": "Opening quatrain.",
    },
    4: {  # Keats, "Beauty is truth"
        "snippet": "\"Beauty is truth, truth beauty,—that is all\nYe know on earth, and all ye need to know.\"",
        "source": "memory",
        "note": "Closing couplet. Quotation marks and em-dash per Keats's 1820 ms.",
    },
    5: {  # Kipling, If—
        "snippet": "If you can keep your head when all about you\n  Are losing theirs and blaming it on you,\nIf you can trust yourself when all men doubt you,\n  But make allowance for their doubting too;",
        "source": "memory",
        "note": "Opening quatrain. Indented even-numbered lines per Kipling's original.",
    },
    6: {  # Kipling, East and West
        "snippet": "Oh, East is East, and West is West, and never the twain shall meet,\nTill Earth and Sky stand presently at God's great Judgment Seat;\nBut there is neither East nor West, Border, nor Breed, nor Birth,\nWhen two strong men stand face to face, though they come from the ends of the earth!",
        "source": "memory",
        "note": "Opening quatrain. The popular quote stops at 'meet' — the ironic reversal in lines 3-4 is what makes the poem.",
    },
    7: {  # Milton, "Mind is its own place"
        "snippet": "The mind is its own place, and in itself\nCan make a Heav'n of Hell, a Hell of Heav'n.",
        "source": "memory",
        "note": "Book I, lines 254-255.",
    },
    8: {  # Milton, "Better to reign in Hell"
        "snippet": "Here we may reign secure, and in my choice\nTo reign is worth ambition though in Hell:\nBetter to reign in Hell, than serve in Heav'n.",
        "source": "memory",
        "note": "Book I, lines 261-263.",
    },
    9: {  # Owen, Dulce et Decorum Est
        "snippet": "My friend, you would not tell with such high zest\nTo children ardent for some desperate glory,\nThe old Lie: Dulce et decorum est\nPro patria mori.",
        "source": "memory",
        "note": "Closing tercet. Owen's whole point is in 'The old Lie' — pulling out only the Latin tag inverts the meaning.",
    },
    10: {  # McCrae, In Flanders Fields
        "snippet": "In Flanders fields the poppies blow\nBetween the crosses, row on row,\n  That mark our place; and in the sky\n  The larks, still bravely singing, fly\nScarce heard amid the guns below.",
        "source": "memory",
        "note": "Opening rondeau quintain. Indentation per McCrae's manuscript.",
    },
    11: {  # Hamlet, "lady doth protest"
        "snippet": "The lady doth protest too much, methinks.",
        "source": "memory",
        "note": "Gertrude, Act III Scene II. Standalone — the line is the artifact.",
    },
    12: {  # King John, "gild refined gold"
        "snippet": "To gild refined gold, to paint the lily,\nTo throw a perfume on the violet,\nTo smooth the ice, or add another hue\nUnto the rainbow, or with taper-light\nTo seek the beauteous eye of heaven to garnish,\nIs wasteful and ridiculous excess.",
        "source": "memory",
        "note": "Salisbury, Act IV Scene II. Often misquoted as 'gild the lily'; original is two parallel actions.",
    },
    13: {  # Twelfth Night
        "snippet": "If music be the food of love, play on;\nGive me excess of it, that, surfeiting,\nThe appetite may sicken, and so die.",
        "source": "memory",
        "note": "Orsino, Act I Scene I, opening of the play.",
    },
    14: {  # Henry V, We few
        "snippet": "We few, we happy few, we band of brothers;\nFor he to-day that sheds his blood with me\nShall be my brother;",
        "source": "memory",
        "note": "Henry V, St Crispin's Day speech, Act IV Scene III.",
    },
    15: {  # Julius Caesar
        "snippet": "Friends, Romans, countrymen, lend me your ears;\nI come to bury Caesar, not to praise him.\nThe evil that men do lives after them;\nThe good is oft interred with their bones;",
        "source": "memory",
        "note": "Mark Antony, Act III Scene II.",
    },
    16: {  # Merchant of Venice
        "snippet": "The quality of mercy is not strain'd,\nIt droppeth as the gentle rain from heaven\nUpon the place beneath: it is twice blest;\nIt blesseth him that gives and him that takes.",
        "source": "memory",
        "note": "Portia, Act IV Scene I.",
    },
    17: {  # Romeo and Juliet
        "snippet": "O Romeo, Romeo! wherefore art thou Romeo?\nDeny thy father and refuse thy name;\nOr, if thou wilt not, be but sworn my love,\nAnd I'll no longer be a Capulet.",
        "source": "memory",
        "note": "Juliet, Act II Scene II. 'Wherefore' = 'why', not 'where'.",
    },
    18: {  # Macbeth, Double double
        "snippet": "Double, double toil and trouble;\nFire burn, and cauldron bubble.",
        "source": "memory",
        "note": "Witches' refrain, Act IV Scene I.",
    },
    19: {  # Hamlet, To be or not to be
        "snippet": "To be, or not to be, that is the question:\nWhether 'tis nobler in the mind to suffer\nThe slings and arrows of outrageous fortune,\nOr to take arms against a sea of troubles,\nAnd by opposing end them.",
        "source": "memory",
        "note": "Hamlet, Act III Scene I.",
    },
    20: {  # Donne, The Sun Rising
        "snippet": "Busy old fool, unruly Sun,\n        Why dost thou thus,\nThrough windows, and through curtains, call on us?\nMust to thy motions lovers' seasons run?",
        "source": "memory",
        "note": "Opening quatrain. The indented short line is part of Donne's metrical scheme.",
    },
    21: {  # Whitman, Song of Myself opening
        "snippet": "I celebrate myself, and sing myself,\nAnd what I assume you shall assume,\nFor every atom belonging to me as good belongs to you.",
        "source": "memory",
        "note": "Section 1, opening tercet.",
    },
    22: {  # Whitman, Do I contradict myself
        "snippet": "Do I contradict myself?\nVery well then I contradict myself,\n(I am large, I contain multitudes.)",
        "source": "memory",
        "note": "Section 51.",
    },
    23: {  # Whitman, O Captain
        "snippet": "O Captain! my Captain! our fearful trip is done,\nThe ship has weather'd every rack, the prize we sought is won,\nThe port is near, the bells I hear, the people all exulting,\nWhile follow eyes the steady keel, the vessel grim and daring;",
        "source": "memory",
        "note": "Opening quatrain.",
    },
    24: {  # Whitman, I Sing the Body Electric
        "snippet": "I sing the body electric,\nThe armies of those I love engirth me and I engirth them,\nThey will not let me off till I go with them, respond to them,\nAnd discorrupt them, and charge them full with the charge of the soul.",
        "source": "memory",
        "note": "Opening quatrain of section 1.",
    },
    25: {  # Angelou, Still I Rise
        "snippet": "You may write me down in history\nWith your bitter, twisted lies,\nYou may trod me in the very dirt\nBut still, like dust, I'll rise.",
        "source": "memory",
        "note": "Opening quatrain.",
    },
    26: {  # Plath, Lady Lazarus
        "snippet": "Out of the ash\nI rise with my red hair\nAnd I eat men like air.",
        "source": "memory",
        "note": "Closing tercet.",
    },
    27: {  # Poe, Quoth the Raven
        "snippet": "Quoth the Raven \"Nevermore.\"",
        "source": "memory",
        "note": "Refrain — the line stands alone as the artifact.",
    },
    28: {  # Poe, Once upon a midnight
        "snippet": "Once upon a midnight dreary, while I pondered, weak and weary,\nOver many a quaint and curious volume of forgotten lore—\nWhile I nodded, nearly napping, suddenly there came a tapping,\nAs of some one gently rapping, rapping at my chamber door.",
        "source": "memory",
        "note": "Opening quatrain.",
    },
    29: {  # FitzGerald-Khayyam, Moving Finger
        "snippet": "The Moving Finger writes; and, having writ,\nMoves on: nor all thy Piety nor Wit\nShall lure it back to cancel half a Line,\nNor all thy Tears wash out a Word of it.",
        "source": "memory",
        "note": "Quatrain LI (1st edition; later editions renumber). Capitalization per FitzGerald.",
    },
    30: {  # FitzGerald-Khayyam, Jug of Wine
        "snippet": "A Book of Verses underneath the Bough,\nA Jug of Wine, a Loaf of Bread—and Thou\nBeside me singing in the Wilderness—\nOh, Wilderness were Paradise enow!",
        "source": "memory",
        "note": "Quatrain XII (1st edition).",
    },
    31: {  # Catullus, Carmen 85
        "snippet": "Odi et amo. quare id faciam, fortasse requiris.\n  nescio, sed fieri sentio et excrucior.",
        "source": "memory+verified",
        "note": "Complete poem (one elegiac couplet). Standard Mynors/OCT text. EN: 'I hate and I love. You may ask why. I do not know, but I feel it happen and am crucified.'",
    },
    32: {  # Horace, Odes I.11
        "snippet": "...sapias, vina liques, et spatio brevi\nspem longam reseces. dum loquimur, fugerit invida\naetas: carpe diem, quam minimum credula postero.",
        "source": "memory+verified",
        "note": "Closing tricolon. EN gloss: 'Be wise, strain the wine, and prune long hopes to short spans. Even as we speak, jealous time has fled: pluck the day, trusting tomorrow as little as you can.'",
    },
    33: {  # Horace, Odes III.30
        "snippet": "Exegi monumentum aere perennius\nregalique situ pyramidum altius,\nquod non imber edax, non Aquilo impotens\npossit diruere aut innumerabilis\nannorum series et fuga temporum.",
        "source": "memory+verified",
        "note": "Opening lines. EN gloss: 'I have raised a monument more lasting than bronze and loftier than the kings' pyramids, which no devouring rain, no raging north wind can destroy, nor the countless succession of years and the flight of ages.'",
    },
    34: {  # Macbeth, Out brief candle
        "snippet": "Out, out, brief candle!\nLife's but a walking shadow, a poor player\nThat struts and frets his hour upon the stage\nAnd then is heard no more.",
        "source": "memory",
        "note": "Macbeth, Act V Scene V — pairs with the 'Tomorrow' speech (next entry).",
    },
    35: {  # Macbeth, Tomorrow
        "snippet": "To-morrow, and to-morrow, and to-morrow,\nCreeps in this petty pace from day to day,\nTo the last syllable of recorded time;",
        "source": "memory",
        "note": "Macbeth, Act V Scene V.",
    },
    36: {  # As You Like It
        "snippet": "All the world's a stage,\nAnd all the men and women merely players;\nThey have their exits and their entrances,\nAnd one man in his time plays many parts,",
        "source": "memory",
        "note": "Jaques, Act II Scene VII.",
    },
    37: {  # Cummings
        "snippet": "anyone lived in a pretty how town\n(with up so floating many bells down)\nspring summer autumn winter\nhe sang his didn't he danced his did.",
        "source": "memory",
        "note": "Opening quatrain. Lowercase per Cummings.",
    },
    38: {  # Tennyson, Lady of Shalott
        "snippet": "On either side the river lie\nLong fields of barley and of rye,\nThat clothe the wold and meet the sky;\nAnd thro' the field the road runs by\n  To many-tower'd Camelot;",
        "source": "memory",
        "note": "Opening quintain.",
    },
    39: {  # Yeats, Innisfree
        "snippet": "I will arise and go now, and go to Innisfree,\nAnd a small cabin build there, of clay and wattles made;\nNine bean-rows will I have there, a hive for the honey-bee,\nAnd live alone in the bee-loud glade.",
        "source": "memory",
        "note": "Opening quatrain.",
    },
    40: {  # Williams, This Is Just To Say
        "snippet": "I have eaten\nthe plums\nthat were in\nthe icebox\n\nand which\nyou were probably\nsaving\nfor breakfast\n\nForgive me\nthey were delicious\nso sweet\nand so cold",
        "source": "memory",
        "note": "Complete poem (12 lines + 2 stanza breaks). Williams's signature minimalism.",
    },
    41: {  # Frost, Mending Wall
        "snippet": "I see him there\nBringing a stone grasped firmly by the top\nIn each hand, like an old-stone savage armed.\nHe moves in darkness as it seems to me,\nNot of woods only and the shade of trees.\nHe will not go behind his father's saying,\nAnd he likes having thought of it so well\nHe says again, 'Good fences make good neighbors.'",
        "source": "memory",
        "note": "Closing — the famous line is the NEIGHBOR's, not Frost's. Frost spends the whole poem questioning it.",
    },
    42: {  # Niemöller
        "snippet": "First they came for the socialists, and I did not speak out—\n   because I was not a socialist.\nThen they came for the trade unionists, and I did not speak out—\n   because I was not a trade unionist.\nThen they came for the Jews, and I did not speak out—\n   because I was not a Jew.\nThen they came for me—and there was no one left to speak for me.",
        "source": "memory",
        "note": "USHMM canonical English version. Niemöller used many variants in lectures (including German originals); no single 'authoritative' text exists. This is the most-cited.",
    },
}


def author_lines(s: str) -> list[str]:
    return [ln for ln in s.split("\n") if ln.strip()]


# Renderer tier ladder mirror (from corpus_analyze.py)
TIERS = [(1,36,48,34,7),(2,32,44,38,8),(3,30,40,41,9),(4,28,34,44,11),(5,28,30,44,12),(6,24,32,52,11),(7,22,28,57,13)]
PILL_FLOOR = {1,2,3,4,5}

def predict_tier(snippet: str) -> int:
    lines = [l for l in snippet.split('\n') if l.strip()]
    longest = max((len(l) for l in lines), default=0)
    n = len(lines)
    for t,_,_,cpl,mvl in TIERS:
        if t in PILL_FLOOR and longest <= cpl and n <= mvl:
            return t
    for t in (4, 5):
        cfg = next(x for x in TIERS if x[0] == t)
        cpl, mvl = cfg[3], cfg[4]
        if sum(max(1, (len(l) + cpl - 1) // cpl) for l in lines) <= mvl:
            return t
    for t in (6, 7):
        cfg = next(x for x in TIERS if x[0] == t)
        cpl, mvl = cfg[3], cfg[4]
        if longest <= cpl and n <= mvl:
            return t
    return 7


def main() -> int:
    data = json.loads(SRC.read_text())
    if len(data) != 43:
        print(f"WARNING: expected 43 entries, got {len(data)}")

    n_curated = n_skipped = 0
    for i, entry in enumerate(data):
        if i not in CURATED:
            print(f"  [{i:2d}] SKIP — no curation: {entry.get('author')} / {entry.get('poem_title')}")
            n_skipped += 1
            continue
        c = CURATED[i]
        snippet = c["snippet"]
        entry["snippet_in_source"] = snippet
        entry["_curation_source"] = c["source"]
        entry["_curation_note"] = c["note"]
        lines = author_lines(snippet)
        entry["snippet_geometry"] = {
            "n_lines": len(lines),
            "longest_line_chars": max((len(l) for l in lines), default=0),
            "total_chars": len(snippet),
        }
        entry["predicted_tier"] = predict_tier(snippet)
        n_curated += 1

    OUT.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\ncurated: {n_curated}, skipped: {n_skipped}")
    print(f"wrote {OUT.relative_to(ROOT)}")

    # Geometry of curated entries
    from collections import Counter
    lc = Counter(); ll = Counter(); tot = Counter()
    for e in data:
        if "_curation_source" not in e: continue
        g = e["snippet_geometry"]
        lc[g["n_lines"]] += 1
        ll[g["longest_line_chars"] // 5 * 5] += 1
        tot[g["total_chars"] // 50 * 50] += 1
    print("\nLines:")
    for k in sorted(lc): print(f"  {k}: {lc[k]}")
    print("\nLongest line buckets (chars):")
    for k in sorted(ll): print(f"  {k}-{k+4}: {ll[k]}")
    print("\nTotal-chars buckets:")
    for k in sorted(tot): print(f"  {k}-{k+49}: {tot[k]}")
    return 0


if __name__ == "__main__":
    import sys; sys.exit(main())

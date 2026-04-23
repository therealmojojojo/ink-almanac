"""Targeted retry for stage-2 fetch misses with hand-tuned queries.

Each entry is (work_id, creator_id, creator_name, query_override). The title
token filter is relaxed for this retry — we assume the query is specific
enough that the top artist-matching hit IS the right work.
"""
from __future__ import annotations
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pairing"))

import yaml
from corpus_api_fetch import (
    commons_search, met_search, strict_match, fetch_bytes, measure,
    sidecar_for, append_manifest, REPO, FLOOR_SHORT, PREF_LONG,
)

# Retry manifest: per-work query override + optional source order override.
# `source_order` is a list; default is ["commons", "met"].
RETRIES = [
    # Kollwitz — German titles
    ("kollwitz-weavers-march", "kathe-kollwitz", "Käthe Kollwitz", "Kollwitz Weberzug Ein Weberaufstand", None),
    ("kollwitz-weavers-end", "kathe-kollwitz", "Käthe Kollwitz", "Kollwitz Ende Weberaufstand", None),
    ("kollwitz-peasants-war-outbreak", "kathe-kollwitz", "Käthe Kollwitz", "Kollwitz Losbruch Bauernkrieg", None),
    ("kollwitz-peasants-war-prisoners", "kathe-kollwitz", "Käthe Kollwitz", "Kollwitz Gefangene Bauernkrieg", None),
    ("kollwitz-war-the-mothers", "kathe-kollwitz", "Käthe Kollwitz", "Kollwitz Mütter Krieg woodcut", None),
    ("kollwitz-war-the-widow-i", "kathe-kollwitz", "Käthe Kollwitz", "Kollwitz Witwe Krieg", None),
    ("kollwitz-death-seizes-a-woman", "kathe-kollwitz", "Käthe Kollwitz", "Kollwitz Tod packt Frau", None),
    ("kollwitz-self-portrait-profile-1927", "kathe-kollwitz", "Käthe Kollwitz", "Kollwitz Selbstbildnis 1927", None),

    # Dix — Der Krieg plates
    ("dix-krieg-stormtroops-advancing-under-gas", "otto-dix", "Otto Dix", "Otto Dix Sturmtruppe Gas vor", None),
    ("dix-krieg-dead-men-before-position-tahure", "otto-dix", "Otto Dix", "Otto Dix Tote Stellung Tahure", None),
    ("dix-krieg-wounded-soldier", "otto-dix", "Otto Dix", "Otto Dix Verwundeter Krieg", None),
    ("dix-krieg-lens-being-bombed", "otto-dix", "Otto Dix", "Otto Dix Lens beschossen", None),
    ("dix-sylvia-von-harden-drawing", "otto-dix", "Otto Dix", "Otto Dix Sylvia von Harden", None),

    # Kirchner
    ("kirchner-two-women-on-the-street", "ernst-ludwig-kirchner", "Ernst Ludwig Kirchner", "Kirchner zwei Frauen Straße", None),
    ("kirchner-davos-winter-landscape", "ernst-ludwig-kirchner", "Ernst Ludwig Kirchner", "Kirchner Davos Winter woodcut", None),

    # Picasso — French titles
    ("picasso-frugal-repast", "pablo-picasso", "Pablo Picasso", "Picasso Repas frugal", None),
    ("picasso-minotauromachy", "pablo-picasso", "Pablo Picasso", "Picasso Minotauromachie 1935", None),
    ("picasso-vollard-minotaur-caresses-sleeping-woman", "pablo-picasso", "Pablo Picasso", "Picasso Minotaure caressant femme endormie", None),
    ("picasso-vollard-sculptors-studio", "pablo-picasso", "Pablo Picasso", "Picasso atelier sculpteur Vollard", None),
    ("picasso-bull-lithograph-state-xi", "pablo-picasso", "Pablo Picasso", "Picasso Taureau lithographie etat", None),
    ("picasso-dove-of-peace", "pablo-picasso", "Pablo Picasso", "Picasso Colombe 1949", None),
    ("picasso-three-nudes", "pablo-picasso", "Pablo Picasso", "Picasso Trois femmes Vollard", None),
    ("picasso-guernica-weeping-woman-study", "pablo-picasso", "Pablo Picasso", "Picasso Femme qui pleure 1937", None),

    # Blake — simpler titles
    ("blake-ancient-of-days", "william-blake", "William Blake", "William Blake Ancient Days Europe Prophecy", None),
    ("blake-newton", "william-blake", "William Blake", "William Blake Newton 1795", None),
    ("blake-nebuchadnezzar", "william-blake", "William Blake", "William Blake Nebuchadnezzar", None),
    ("blake-great-red-dragon-woman-clothed-in-sun", "william-blake", "William Blake", "William Blake Great Red Dragon", None),
    ("blake-job-when-morning-stars-sang", "william-blake", "William Blake", "Blake Morning Stars Sang Job", None),
    ("blake-job-satan-smiting", "william-blake", "William Blake", "Blake Satan Smiting Job sore boils", None),
    ("blake-dante-whirlwind-of-lovers", "william-blake", "William Blake", "Blake Whirlwind Lovers Dante", None),

    # Doré
    ("dore-inferno-minotaur", "gustave-dore", "Gustave Doré", "Dore Minotaur Dante Inferno", None),
    ("dore-inferno-paolo-francesca", "gustave-dore", "Gustave Doré", "Dore Paolo Francesca Inferno", None),
    ("dore-don-quixote-library", "gustave-dore", "Gustave Doré", "Dore Don Quixote library books", None),
    ("dore-london-over-london-by-rail", "gustave-dore", "Gustave Doré", "Dore Over London Rail Pilgrimage", None),
    ("dore-london-ludgate-hill", "gustave-dore", "Gustave Doré", "Dore Ludgate Hill London Pilgrimage", None),
    ("dore-raven-perched-bust-pallas", "gustave-dore", "Gustave Doré", "Dore Raven Poe Perched", None),

    # Daumier (2 misses from 429)
    ("daumier-gargantua", "honore-daumier", "Honoré Daumier", "Daumier Gargantua 1831 La Caricature", None),
    ("daumier-ratapoil", "honore-daumier", "Honoré Daumier", "Daumier Ratapoil statuette bronze", None),

    # Meryon
    ("meryon-le-stryge", "charles-meryon", "Charles Meryon", "Meryon Stryge Notre-Dame", None),

    # Redon — Origines plates
    ("redon-origins-germination", "odilon-redon", "Odilon Redon", "Redon Germination Origines lithograph", None),
    ("redon-origins-gnome", "odilon-redon", "Odilon Redon", "Redon vision première fleur Origines", None),
    ("redon-hommage-a-goya-marsh-flower", "odilon-redon", "Odilon Redon", "Redon Hommage Goya fleur marais embryonnaires", None),

    # Whistler Piazzetta (just retry Met on cooldown)
    ("whistler-venice-piazzetta", "james-mcneill-whistler", "James McNeill Whistler", "Whistler Piazzetta Venice etching", None),

    # Beardsley + Lautrec (2 misses)
    ("beardsley-salome-jai-baise-ta-bouche", "aubrey-beardsley", "Aubrey Beardsley", "Beardsley jai baise ta bouche Iokanaan Salome Studio", None),
    ("lautrec-elles-femme-qui-se-peigne", "henri-de-toulouse-lautrec", "Henri de Toulouse-Lautrec", "Toulouse Lautrec Femme qui se peigne Elles", None),

    # Callot
    ("callot-miseres-arquebusade", "jacques-callot", "Jacques Callot", "Callot Arquebusade Miseres Guerre", None),
    ("callot-balli-di-sfessania-captain", "jacques-callot", "Jacques Callot", "Callot Capitano Cerimonia Balli Sfessania", None),
    ("callot-les-gueux-seated-beggar", "jacques-callot", "Jacques Callot", "Callot Gueux seated beggar", None),

    # Goya Caprichos/aquatints
    ("goya-caprichos-there-is-no-remedy", "francisco-goya", "Francisco Goya", "Goya No hay remedio Caprichos 24", None),
    ("goya-caprichos-hasta-la-muerte", "francisco-goya", "Francisco Goya", "Goya Hasta la muerte Caprichos 55", None),
    ("goya-giant-aquatint", "francisco-goya", "Francisco Goya", "Goya Gigante aquatint colossus", None),

    # Seurat
    ("seurat-seated-boy-straw-hat", "georges-seurat", "Georges Seurat", "Seurat seated boy straw hat conte", None),
    ("seurat-at-the-concert-europeen", "georges-seurat", "Georges Seurat", "Seurat Concert Europeen drawing", None),
    ("seurat-cafe-concert", "georges-seurat", "Georges Seurat", "Seurat Cafe Concert drawing", None),
    ("seurat-gleaner", "georges-seurat", "Georges Seurat", "Seurat Glaneuse gleaner", None),

    # Schiele
    ("schiele-embrace", "egon-schiele", "Egon Schiele", "Schiele Embrace Cardinal Nun Umarmung", None),

    # Hopper etchings
    ("hopper-night-shadows", "edward-hopper", "Edward Hopper", "Hopper Night Shadows 1921 etching", None),
    ("hopper-the-lonely-house", "edward-hopper", "Edward Hopper", "Hopper Lonely House 1923 etching", None),

    # Lewis drypoints
    ("lewis-relics-speakeasy-corner", "martin-lewis", "Martin Lewis", "Martin Lewis Relics Speakeasy", None),
    ("lewis-shadow-dance", "martin-lewis", "Martin Lewis", "Martin Lewis Shadow Dance 1930 drypoint", None),
    ("lewis-glow-of-the-city", "martin-lewis", "Martin Lewis", "Martin Lewis Glow City", None),
    ("lewis-little-penthouse", "martin-lewis", "Martin Lewis", "Martin Lewis Little Penthouse", None),
    ("lewis-stoops-in-snow", "martin-lewis", "Martin Lewis", "Martin Lewis Stoops Snow", None),
    ("lewis-fifth-avenue-bridge", "martin-lewis", "Martin Lewis", "Martin Lewis Fifth Avenue Bridge", None),

    # Lynd Ward
    ("ward-gods-man-frontispiece", "lynd-ward", "Lynd Ward", "Lynd Ward Gods Man frontispiece", None),
    ("ward-gods-man-city-at-night", "lynd-ward", "Lynd Ward", "Lynd Ward Gods Man city night", None),
    ("ward-madmans-drum-drummer", "lynd-ward", "Lynd Ward", "Lynd Ward Madmans Drum drummer", None),
    ("ward-wild-pilgrimage-road", "lynd-ward", "Lynd Ward", "Lynd Ward Wild Pilgrimage road", None),
    ("ward-vertigo-factory", "lynd-ward", "Lynd Ward", "Lynd Ward Vertigo factory", None),

    # Sesshū
    ("sesshu-winter-landscape", "sesshu-toyo", "Sesshū", "Sesshu Winter Landscape Toyo", None),
    ("sesshu-long-landscape-scroll", "sesshu-toyo", "Sesshū", "Sesshu sansui chokan landscape scroll", None),
    ("sesshu-amanohashidate", "sesshu-toyo", "Sesshū", "Sesshu Amanohashidate", None),

    # Hakuin
    ("hakuin-one-stroke-daruma", "hakuin-ekaku", "Hakuin", "Hakuin Ippitsu Daruma one stroke", None),
    ("hakuin-blind-men-crossing-log-bridge", "hakuin-ekaku", "Hakuin", "Hakuin blind men log bridge", None),
    ("hakuin-giant-radish", "hakuin-ekaku", "Hakuin", "Hakuin daikon radish", None),
    ("hakuin-monkey-grasping-moon", "hakuin-ekaku", "Hakuin", "Hakuin monkey moon reflection", None),
]


WORKS_BY_ID: dict[str, dict] = {}
CREATOR_META: dict[str, dict] = {}


def load_works():
    """Read all works-*.yaml and stash each entry by id."""
    lists_dir = REPO / "openspec" / "changes" / "add-bw-graphic-arts-canon" / "lists"
    for p in sorted(lists_dir.glob("works-*.yaml")):
        doc = yaml.safe_load(p.read_text())
        lineage = doc.get("lineage", "")
        file_defaults = doc.get("defaults", {}) or {}
        for cid, cr in doc.get("creators", {}).items():
            creator_defaults = (cr.get("defaults") or {})
            CREATOR_META[cid] = {
                "lineage": lineage,
                "rights_tier": creator_defaults.get(
                    "rights_tier", file_defaults.get("rights_tier", "public_domain")),
            }
            for w in cr.get("works", []):
                if isinstance(w, dict) and "id" in w:
                    WORKS_BY_ID[w["id"]] = w


def try_one(work_id: str, creator_id: str, creator_name: str, query: str,
            source_order):
    work = WORKS_BY_ID.get(work_id)
    if not work:
        print(f"  {work_id}  — NOT IN LIST, skipping")
        return None
    meta = CREATOR_META.get(creator_id, {})
    tier = work.get("rights_tier", meta.get("rights_tier", "public_domain"))
    folder = "corpus/personal_library" if tier == "personal_library" else "corpus/images"
    if (REPO / folder / f"{work_id}.yaml").exists():
        print(f"  {work_id}  — already on disk, skipping")
        return {"work_id": work_id, "status": "skipped"}
    print(f"  • {work_id}")
    print(f"     query: {query!r}")
    chain = source_order or ["commons", "met"]
    for src in chain:
        try:
            if src == "commons":
                cands = commons_search(query)
            elif src == "met":
                cands = met_search(query)
            else:
                continue
        except Exception as e:
            print(f"     {src}: search error: {e}")
            continue
        qtitle = work.get("title", work_id)
        for c in cands:
            if not strict_match(creator_name, qtitle, c["hay"], loose=True):
                continue
            if not c.get("url"):
                continue
            try:
                data = fetch_bytes(c["url"])
            except Exception as e:
                print(f"     {src}: dl error ({str(e)[:60]})")
                continue
            try:
                (w_, h_), fmt = measure(data)
            except Exception:
                continue
            if min(w_, h_) < FLOOR_SHORT:
                continue
            ext = "png" if fmt == "png" else "jpg"
            rel_img = f"{folder}/{work_id}.{ext}"
            rel_yml = f"{folder}/{work_id}.yaml"
            yaml_text = sidecar_for(
                work, creator_id, creator_name,
                meta.get("rights_tier", "public_domain"), data, c, w_, h_)
            (REPO / rel_img).write_bytes(data)
            (REPO / rel_yml).write_text(yaml_text)
            append_manifest(rel_img, data, fmt)
            pref = "" if max(w_, h_) >= PREF_LONG else " ⚠below 1800pref"
            print(f"     ✓ {src} · {w_}×{h_} · {len(data):,}B{pref}")
            return {"work_id": work_id, "w": w_, "h": h_, "source": c["source"]}
        else:
            print(f"     {src}: no artist match in {len(cands)} candidates")
    return {"work_id": work_id, "status": "miss"}


def main():
    load_works()
    print(f"Loaded {len(WORKS_BY_ID)} works across {len(CREATOR_META)} creators")
    print(f"Retry list: {len(RETRIES)} items")
    results = []
    for work_id, cid, cname, query, src_order in RETRIES:
        r = try_one(work_id, cid, cname, query, src_order)
        if r:
            results.append(r)

    hits = [r for r in results if "w" in r]
    miss = [r for r in results if r.get("status") == "miss"]
    skip = [r for r in results if r.get("status") == "skipped"]
    print(f"\n======== RETRY SUMMARY ========")
    print(f"  hits={len(hits)}  misses={len(miss)}  already-on-disk={len(skip)}")
    if miss:
        print("  still missing:")
        for r in miss:
            print(f"    {r['work_id']}")


if __name__ == "__main__":
    main()

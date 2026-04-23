"""Shared web-search primitives for corpus ingestion.

Used by corpus_harvest (primary photographer-level flow) and the future
corpus_fetch_work (targeted per-work flow). Keeps DDG handshake, candidate
gate, perceptual-hash dedup, and the reject/allow-list in one place.

Design rationale: see openspec/changes/add-ingestion-automation/design.md.
"""
from __future__ import annotations
import io
import json
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, asdict
from typing import Iterable

# -- HTTP --------------------------------------------------------------------

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15")
TIMEOUT = 20
IMG_EXTS = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp")


def http_get(url: str, headers: dict | None = None, binary: bool = False, timeout: int = TIMEOUT):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    return data if binary else data.decode("utf-8", errors="replace")


# -- Perceptual hash (dHash-8) -----------------------------------------------

def dhash(img_bytes: bytes, size: int = 8) -> int | None:
    """9x8 difference-hash — 64-bit perceptual hash.

    Numpy + PIL only; no scipy. Same image at different resolutions hashes
    to near-identical values (Hamming ≤ 8 under normal compression).
    """
    try:
        from PIL import Image
        import numpy as np
        img = Image.open(io.BytesIO(img_bytes)).convert("L").resize(
            (size + 1, size), Image.LANCZOS
        )
    except Exception:
        return None
    import numpy as np  # type: ignore
    px = np.asarray(img, dtype=np.int16)
    diff = px[:, 1:] > px[:, :-1]
    h = 0
    for b in diff.flatten():
        h = (h << 1) | int(b)
    return h


def hamming(a: int | None, b: int | None) -> int:
    if a is None or b is None:
        return 64
    return bin(a ^ b).count("1")


# -- Domain lists ------------------------------------------------------------

BANNED_HOSTS = (
    "pinterest", "pinimg",
    "facebook.com", "fbsbx.com", "fb.com",
    "instagram.com", "x.com",
    "centerblog.net",
    "alchetron.com",
    "shutterstock.com", "alamy.com",
)

DOMAIN_WEIGHTS: dict[str, float] = {
    # Museums + national institutions
    "moma.org": 1.00, "metmuseum.org": 1.00, "getty.edu": 0.95,
    "artic.edu": 0.95, "nga.gov": 0.95, "loc.gov": 1.00, "tate.org.uk": 0.95,
    "sfmoma.org": 0.95, "museumca.org": 0.90, "icp.org": 0.95,
    "npg.org.uk": 0.95, "nationalmuseum.se": 0.90,
    "dorothealange.museumca.org": 0.95,
    # Artist estates / archive sites
    "magnumphotos.com": 1.00, "henricartierbresson.org": 1.00,
    "irvingpennfoundation.org": 1.00, "galerie-roger-viollet.fr": 0.90,
    "vivianmaier.com": 0.95,
    # Auction houses
    "sothebys.com": 0.85, "christies.com": 0.85, "phillips.com": 0.80,
    "bukowskis.com": 0.65, "1stdibs.com": 0.55,
    # Galleries
    "fraenkelgallery.com": 0.85, "rosegallery.net": 0.75,
    "jacksonfineart.com": 0.75, "holdenluntz.com": 0.80,
    "pacegallery.com": 0.80, "obscuragallery.net": 0.60,
    "souslesetoilesgallery.net": 0.70,
    # Editorial / curator-adjacent
    "artblart.com": 0.85, "aperture.org": 0.90, "blind-magazine.com": 0.60,
    "loeildelaphotographie.com": 0.55, "artsy.net": 0.80, "urth.co": 0.55,
    "photofrome.org": 0.60, "andrewsmithgallery.com": 0.70,
    "arthur.io": 0.55, "flashbak.com": 0.50, "publicdelivery.org": 0.50,
    "aboutphotography.blog": 0.50,
    # Wiki
    "wikimedia.org": 1.00, "wikipedia.org": 1.00,
    "commons.wikimedia.org": 1.00,
    # Demoted (considered but low weight)
    "reddit.com": 0.30, "youtube.com": 0.20,
    "blogspot.com": 0.20, "wordpress.com": 0.25, "tumblr.com": 0.20,
    "mutualart.com": 0.55, "artnet.com": 0.55, "artsper.com": 0.55,
    "art.salon": 0.55,
}


def host_of(url: str) -> str:
    try:
        return urllib.parse.urlparse(url).netloc.lower()
    except Exception:
        return ""


def is_banned(url: str) -> bool:
    host = host_of(url)
    return any(b in host for b in BANNED_HOSTS)


def domain_weight(url: str) -> float:
    host = host_of(url)
    for k, v in DOMAIN_WEIGHTS.items():
        if k in host:
            return v
    return 0.35  # unknown-domain baseline


# -- Candidate gate ----------------------------------------------------------

def surname_in(text: str, surname: str) -> bool:
    """Word-boundary surname match; handles short (Ho) and multi-word (Álvarez Bravo)."""
    if not text or not surname:
        return False
    blob = text.lower()
    sl = surname.lower()
    if sl in blob:
        return True
    for t in re.findall(r"[\w']+", sl):
        if len(t) >= 2 and re.search(r"(?<![a-z])" + re.escape(t) + r"(?![a-z])", blob):
            return True
    return False


def res_floor(w: int, h: int) -> bool:
    """Orientation-aware MUST floor from corpus-schema."""
    if w <= 0 or h <= 0:
        return False
    return (w >= 1080) if w >= h else (h >= 693)


def res_preferred(w: int, h: int) -> bool:
    return max(w, h) >= 1800


# -- DDG search --------------------------------------------------------------

def build_ddg_filter(orientation: str | None = None,
                      media_type: str = "photo") -> str:
    """DDG `iaf` filter string.

    `media_type` controls which of DDG's content classes we accept:
      - "photo"  — photographs (correct for the B&W photography canon)
      - "line"   — line drawings / illustrations / comic art (correct for
                    manga, comic-strip, caricature — anything drawn)
      - None     — omit the type filter (accept any image class)
    """
    parts = ["size:Large"]
    if media_type:
        parts.append(f"type:{media_type}")
    parts.append("color:Monochrome")
    if orientation == "tall":
        parts.append("layout:Tall")
    elif orientation == "wide":
        parts.append("layout:Wide")
    elif orientation == "square":
        parts.append("layout:Square")
    return ",".join(parts)


def ddg_search(query: str, orientation: str | None = None,
                max_results: int = 40, media_type: str = "photo") -> list[dict]:
    """Two-step DDG image search: HTML vqd handshake → i.js JSON."""
    q_enc = urllib.parse.quote(query)
    filt = build_ddg_filter(orientation, media_type=media_type)
    filt_enc = urllib.parse.quote(filt)
    html = http_get(
        f"https://duckduckgo.com/?q={q_enc}&iar=images&iax=images&ia=images&iaf={filt_enc}"
    )
    m = re.search(r"vqd=['\"]?(\d+-\d+)", html)
    if not m:
        raise RuntimeError("DDG vqd token not found in HTML response")
    vqd = m.group(1)
    time.sleep(0.4)  # polite spacing
    ijs_url = "https://duckduckgo.com/i.js?" + urllib.parse.urlencode({
        "l": "us-en", "o": "json", "q": query, "vqd": vqd,
        "f": filt, "p": "1",
    })
    raw = http_get(ijs_url, headers={
        "Referer": "https://duckduckgo.com/",
        "Accept": "application/json",
    })
    return json.loads(raw).get("results", [])[:max_results]


# -- Candidate record + dedup -----------------------------------------------

@dataclass
class Candidate:
    ddg_rank: int
    title: str
    source_url: str
    image_url: str
    thumb_url: str
    width: int
    height: int
    host: str
    domain_weight: float
    surname_match: bool
    passes_floor: bool
    high_res: bool
    phash: int | None = None
    cluster_id: int | None = None  # populated by dedup
    cluster_size: int = 1           # how many candidates (inc. self) share this cluster
    # reason populated when rejected
    reject_reason: str | None = None

    def orientation(self) -> str:
        if self.width > self.height * 1.2:
            return "wide"
        if self.height > self.width * 1.2:
            return "tall"
        return "square"


def to_candidate(rank: int, row: dict, surname: str) -> Candidate:
    w, h = int(row.get("width", 0) or 0), int(row.get("height", 0) or 0)
    src = row.get("url") or ""
    img = row.get("image") or ""
    thumb = row.get("thumbnail") or img
    title = (row.get("title") or "")
    blob = " ".join([title, src, img]).lower()
    host = host_of(src or img)
    return Candidate(
        ddg_rank=rank,
        title=title,
        source_url=src,
        image_url=img,
        thumb_url=thumb,
        width=w, height=h,
        host=host,
        domain_weight=domain_weight(src or img),
        surname_match=surname_in(blob, surname),
        passes_floor=res_floor(w, h),
        high_res=res_preferred(w, h),
    )


def apply_gate(cand: Candidate) -> Candidate:
    """Set reject_reason in place; returns the candidate for chaining."""
    if is_banned(cand.source_url or cand.image_url):
        cand.reject_reason = "banned_domain"
    elif not cand.passes_floor:
        cand.reject_reason = "below_floor"
    elif not cand.surname_match:
        cand.reject_reason = "no_surname_match"
    return cand


def fetch_thumbnail(cand: Candidate) -> bytes | None:
    """Download DDG-hosted thumbnail for pHash. Polite failure returns None."""
    if not cand.thumb_url:
        return None
    try:
        return http_get(cand.thumb_url, binary=True,
                        headers={"Referer": "https://duckduckgo.com/"})
    except Exception:
        return None


def cluster_dedup(candidates: list[Candidate], threshold: int = 8) -> list[list[Candidate]]:
    """Greedy single-linkage by pHash Hamming distance.

    Returns list of clusters; within each cluster the highest-resolution
    candidate is placed first.
    """
    clusters: list[list[Candidate]] = []
    for c in candidates:
        if c.phash is None:
            clusters.append([c])
            continue
        placed = False
        for cl in clusters:
            rep_phash = next((x.phash for x in cl if x.phash is not None), None)
            if rep_phash is not None and hamming(rep_phash, c.phash) <= threshold:
                cl.append(c)
                placed = True
                break
        if not placed:
            clusters.append([c])
    for i, cl in enumerate(clusters):
        cl.sort(key=lambda x: (-max(x.width, x.height), -x.domain_weight))
        for c in cl:
            c.cluster_id = i
            c.cluster_size = len(cl)
    return clusters


# -- Serialization ----------------------------------------------------------

def candidates_to_json(cands: Iterable[Candidate]) -> list[dict]:
    out = []
    for c in cands:
        d = asdict(c)
        # phash rendered as hex for readability
        if d.get("phash") is not None:
            d["phash"] = f"{c.phash:016x}"
        out.append(d)
    return out

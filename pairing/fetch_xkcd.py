"""Fetch XKCD strips via the public JSON API.

For each work in openspec/changes/add-contemporary-pen-canon/lists/works-xkcd.yaml,
pulls xkcd.com/<num>/info.0.json, downloads the PNG from the `img` URL, and
writes sidecar + binary to corpus/personal_library/ with manifest update.

Usage:
    python3 pairing/fetch_xkcd.py --dry
    python3 pairing/fetch_xkcd.py --commit
"""
from __future__ import annotations
import argparse
import datetime
import hashlib
import io
import json
import sys
import urllib.request
from pathlib import Path

import yaml
from PIL import Image

REPO = Path(__file__).resolve().parent.parent
CORPUS = REPO / "corpus"
MANIFEST = CORPUS / "_manifest.json"
LIST_PATH = REPO / "openspec" / "changes" / "add-contemporary-pen-canon" / "lists" / "works-xkcd.yaml"

UA = "inkplate-corpus/1.0 (kitchen fridge; one-operator household)"
FLOOR_SHORT = 200   # xkcd strips can be small — loosen the floor


def get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


def fetch_bytes(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=60).read()


def measure(data: bytes):
    with Image.open(io.BytesIO(data)) as im:
        return im.size, (im.format or "PNG").lower()


def upscale_if_needed(data: bytes, fmt: str) -> tuple[bytes, tuple[int, int]]:
    """XKCD serves native-digital line art at 300–800 px. Upscale so the
    landscape short-edge ≥ 1080 (or portrait short-edge ≥ 693). Line art
    upscales cleanly via bicubic — no loss of legibility."""
    with Image.open(io.BytesIO(data)) as im:
        w, h = im.size
        is_landscape = w >= h
        fill = w if is_landscape else h
        target = 1080 if is_landscape else 693
        if fill >= target:
            return data, (w, h)
        scale = target / fill
        # Don't go wild — cap the scale factor at 4x
        scale = min(scale, 4.0)
        new_w, new_h = int(w * scale + 0.5), int(h * scale + 0.5)
        up = im.resize((new_w, new_h), Image.BICUBIC)
        out = io.BytesIO()
        save_fmt = "PNG" if fmt == "png" else "JPEG"
        if save_fmt == "JPEG":
            up.save(out, format="JPEG", quality=92, optimize=True)
        else:
            up.save(out, format="PNG", optimize=True)
        return out.getvalue(), (new_w, new_h)


def sidecar(work: dict, info: dict, w: int, h: int, citation: str) -> str:
    def q(s: str) -> str:
        return '"' + (s or "").replace("\\", "\\\\").replace('"', '\\"') + '"'
    # xkcd publication date: info["year"], info["month"], info["day"]
    try:
        year = int(info["year"])
    except Exception:
        year = work.get("year")
    title = info.get("safe_title") or info.get("title") or work.get("title", "")
    alt = info.get("alt", "")
    source_url = f"https://xkcd.com/{info['num']}/"
    img_url = info.get("img", "")
    lines = [
        f"id: {work['id']}",
        f"title: {q(title)}",
        f"artist: \"Randall Munroe\"",
        f"year: {year if year else 'null'}",
        f"rights_tier: personal_library",
        f"source: xkcd",
        f"source_url: {source_url}",
        f"citation: {q(citation)}",
        f"medium: digital pen-and-ink",
        f"pixel_width: {w}",
        f"pixel_height: {h}",
        f"panel_fidelity: native",
        f"form: drawing",
        f"themes:",
        *[f"- {t}" for t in work.get("themes", [])],
        f"mood:",
        *[f"- {m}" for m in work.get("mood", [])],
        f"register:",
        *[f"- {r}" for r in work.get("register", [])],
        f"added: '{datetime.date.today().isoformat()}'",
        f"xkcd_num: {info['num']}",
        f"xkcd_alt: {q(alt)}",
        f"xkcd_img: {q(img_url)}",
    ]
    return "\n".join(lines) + "\n"


def append_manifest(rel_path: str, data: bytes, mime: str):
    m = json.loads(MANIFEST.read_text())
    sha = hashlib.sha256(data).hexdigest()
    m["entries"] = [e for e in m["entries"] if e["path"] != rel_path]
    m["entries"].append({
        "path": rel_path,
        "sha256": sha,
        "bytes": len(data),
        "mime": f"image/{'png' if mime == 'png' else 'jpeg'}",
        "backup_uri": f"file://{(REPO / rel_path)}",
    })
    MANIFEST.write_text(json.dumps(m, indent=2) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()

    doc = yaml.safe_load(LIST_PATH.read_text())
    citation = (doc.get("defaults") or {}).get("citation", "")
    works = doc["creators"]["randall-munroe"]["works"]

    hits = []
    miss = []
    for w in works:
        n = w["xkcd_num"]
        print(f"• #{n} {w['title']}")
        try:
            info = get_json(f"https://xkcd.com/{n}/info.0.json")
        except Exception as e:
            print(f"    API error: {e}"); miss.append(w["id"]); continue
        img_url = info.get("img")
        if not img_url:
            print(f"    no img url"); miss.append(w["id"]); continue
        try:
            data = fetch_bytes(img_url)
        except Exception as e:
            print(f"    dl error: {e}"); miss.append(w["id"]); continue
        try:
            (pw, ph), fmt = measure(data)
        except Exception as e:
            print(f"    not an image: {e}"); miss.append(w["id"]); continue
        data, (pw, ph) = upscale_if_needed(data, fmt)
        print(f"    ✓ {pw}×{ph} · {len(data):,}B · {fmt}")
        if args.commit:
            ext = "png" if fmt == "png" else "jpg"
            rel_img = f"corpus/personal_library/{w['id']}.{ext}"
            rel_yml = f"corpus/personal_library/{w['id']}.yaml"
            (REPO / rel_img).write_bytes(data)
            (REPO / rel_yml).write_text(sidecar(w, info, pw, ph, citation))
            append_manifest(rel_img, data, fmt)
        hits.append(w["id"])

    print("\n" + "=" * 50)
    print(f"SUMMARY hits={len(hits)}  misses={len(miss)}")
    if miss:
        for m in miss:
            print(f"  miss: {m}")


if __name__ == "__main__":
    main()

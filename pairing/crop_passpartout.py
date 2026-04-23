"""Crop museum passpartout (white mat) from an image — keep just the plate.

Detects the bounding box of non-white content and crops with a small margin.
Saves the original binary to corpus/_staging/<batch>-originals/<id>.<ext>
before overwriting, updates the sidecar's pixel_width / pixel_height, and
refreshes the manifest sha256 + bytes.

Usage:
    python3 pairing/crop_passpartout.py goya-disasters-of-war-one
    python3 pairing/crop_passpartout.py --prefix goya        # all goya-*
    python3 pairing/crop_passpartout.py --prefix goya --dry  # preview only

Tuning:
    --threshold N        pixel intensity (0-255) above which is "paper"; default 232
    --margin N           pixels of breathing room around detected bbox; default 24
    --min-black-frac F   abort if <F of image is below-threshold (suspiciously empty); default 0.01
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import re
import sys
from pathlib import Path

from PIL import Image, ImageOps, ImageFilter

REPO = Path(__file__).resolve().parent.parent
CORPUS = REPO / "corpus"
MANIFEST = CORPUS / "_manifest.json"
BACKUP = CORPUS / "_staging" / "crop-originals"


def detect_bbox(img: Image.Image, threshold: int, min_frac: float):
    """Return (l, t, r, b) bbox of the plate/content, using row+column
    darkness projections. Rejects rows/cols that are overwhelmingly paper
    (a few scan specks no longer pull the bbox out to the sheet edge)."""
    g = ImageOps.grayscale(img).filter(ImageFilter.MedianFilter(size=5))
    W, H = g.size
    # dark mask: 1 where pixel is below threshold (i.e., content), 0 elsewhere
    px = list(g.getdata())
    # Row and column sums of "darkness" (lower pixel = darker; we use
    # (255 - px) so that black is brightest contribution).
    # Work in numpy if available; fall back to pure-python sums.
    try:
        import numpy as np
        arr = np.asarray(g, dtype=np.int16)
        dark = (arr < threshold).astype(np.int32)   # 1 where content-dark
        row_frac = dark.sum(axis=1) / W
        col_frac = dark.sum(axis=0) / H
    except Exception:
        # pure-python fallback (slow on large images)
        row_frac = [sum(1 for i in range(W) if px[y*W + i] < threshold) / W
                    for y in range(H)]
        col_frac = [sum(1 for j in range(H) if px[j*W + x] < threshold) / H
                    for x in range(W)]

    # A row/col is a "content" row/col if ≥ min_frac of its pixels are dark.
    def runs(fracs, thresh):
        hits = [i for i, f in enumerate(fracs) if f >= thresh]
        return (hits[0], hits[-1] + 1) if hits else None

    # Content fraction threshold: 3% of a row needs to be dark for that row to
    # count as plate. This excludes isolated specks in the paper margin.
    content_thr = max(0.03, min_frac)
    rb = runs(row_frac, content_thr)
    cb = runs(col_frac, content_thr)
    if not rb or not cb:
        # relax: try 1%
        rb = runs(row_frac, 0.01)
        cb = runs(col_frac, 0.01)
    if not rb or not cb:
        return None
    t, b = rb
    l, r = cb
    return (l, t, r, b)


def pad_bbox(bbox, w, h, margin):
    l, t, r, b = bbox
    return (max(0, l - margin), max(0, t - margin),
            min(w, r + margin), min(h, b + margin))


def process(img_path: Path, threshold: int, margin: int, min_frac: float,
            dry: bool):
    if not img_path.exists():
        print(f"  {img_path.name}: missing"); return False
    try:
        im = Image.open(img_path)
        im.load()
    except Exception as e:
        print(f"  {img_path.name}: not an image ({e})"); return False

    bbox = detect_bbox(im, threshold, min_frac)
    if bbox is None:
        print(f"  {img_path.name}: no content detected (threshold too tight?)")
        return False
    W, H = im.size
    L, T, R, B = pad_bbox(bbox, W, H, margin)
    cw, ch = R - L, B - T
    frac_kept = (cw * ch) / (W * H)
    print(f"  {img_path.name}: {W}×{H} → {cw}×{ch}  ({frac_kept*100:.1f}% kept)")

    if dry:
        return True

    # Backup
    BACKUP.mkdir(parents=True, exist_ok=True)
    backup_path = BACKUP / img_path.name
    if not backup_path.exists():
        backup_path.write_bytes(img_path.read_bytes())

    # Crop + save
    cropped = im.crop((L, T, R, B))
    buf = io.BytesIO()
    fmt = (im.format or "JPEG").upper()
    if fmt == "JPEG":
        cropped.save(buf, format="JPEG", quality=92, optimize=True)
    elif fmt == "PNG":
        cropped.save(buf, format="PNG", optimize=True)
    else:
        cropped.save(buf, format=fmt)
    data = buf.getvalue()
    img_path.write_bytes(data)

    # Update sidecar
    yaml_path = img_path.with_suffix(".yaml")
    if yaml_path.exists():
        t = yaml_path.read_text()
        t = re.sub(r"^pixel_width:\s*\d+", f"pixel_width: {cw}", t, flags=re.MULTILINE)
        t = re.sub(r"^pixel_height:\s*\d+", f"pixel_height: {ch}", t, flags=re.MULTILINE)
        yaml_path.write_text(t)

    # Update manifest
    try:
        m = json.loads(MANIFEST.read_text())
        rel = str(img_path.relative_to(REPO))
        sha = hashlib.sha256(data).hexdigest()
        for e in m["entries"]:
            if e["path"] == rel:
                e["sha256"] = sha
                e["bytes"] = len(data)
                break
        MANIFEST.write_text(json.dumps(m, indent=2) + "\n")
    except Exception as e:
        print(f"    manifest update failed: {e}")

    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="*", help="bare ids (no extension); e.g., goya-disasters-of-war-one")
    ap.add_argument("--prefix", help="run on all items whose id starts with PREFIX")
    ap.add_argument("--threshold", type=int, default=232)
    ap.add_argument("--margin", type=int, default=24)
    ap.add_argument("--min-black-frac", type=float, default=0.01)
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()

    targets: list[Path] = []
    search = [CORPUS / "images", CORPUS / "personal_library"]
    if args.prefix:
        for d in search:
            for p in d.glob(f"{args.prefix}*"):
                if p.suffix.lower() in (".jpg", ".jpeg", ".png"):
                    targets.append(p)
    else:
        for ident in args.ids:
            for d in search:
                for ext in (".jpg", ".jpeg", ".png"):
                    p = d / f"{ident}{ext}"
                    if p.exists():
                        targets.append(p); break

    if not targets:
        print("No targets.")
        sys.exit(1)

    targets.sort()
    print(f"{'DRY-RUN ' if args.dry else ''}cropping {len(targets)} image(s)  "
          f"threshold={args.threshold} margin={args.margin}")
    ok = 0
    for p in targets:
        if process(p, args.threshold, args.margin, args.min_black_frac, args.dry):
            ok += 1
    print(f"done: {ok}/{len(targets)}")


if __name__ == "__main__":
    main()

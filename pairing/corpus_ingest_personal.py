"""corpus ingest-personal — ingest a folder of web-downloaded images /
typed text fragments into the personal-library tier, via a safe
staging → commit two-phase.

Phase 1 (stage):
    corpus ingest-personal --folder <path> --citation <string>
        [--batch-id <id>]        (default: personal-YYYY-MM-DD-HHMMSS)
        [--nocturne]             (route to personal_library/nocturne/)
        [--language <codes>]     (default: en; comma-sep for bilingual text)
        [--source-url <url>]     (same for all; e.g., a museum page)
        [--id-prefix <string>]   (prepended to each generated id)
        [--backup-scheme file|icloud]   (default: file)
        [--backup-base <path>]   (default: absolute path to the committed binary)
        [--dry-run]

    Copies binaries / text bodies into `corpus/_staging/<batch-id>/` and writes
    sidecar YAMLs with mandatory fields present and tag fields seeded with TODO
    placeholders. Prints a review checklist. NOTHING in the live corpus is
    touched. This is the safe half of the flow; the operator edits the staged
    sidecars to fill in real themes / mood / register / form tags from the
    taxonomy before committing.

Phase 2 (commit):
    corpus ingest-personal --commit --batch-id <id> [--dry-run]

    Validates every staged sidecar has real taxonomy tags (no TODO left).
    Moves binaries + sidecars from `_staging/<batch-id>/` into the real
    corpus/personal_library/[nocturne/] folders, appends manifest entries, and
    reports the batch.

Rights posture: personal-library items MUST NOT be git-committed (binaries) or
uploaded to schemes that leave operator control. This tool writes `file://`
backup URIs by default and accepts `icloud://` as an alternate operator-local
scheme. `b2://` / `s3://` are refused — see corpus-schema "Rights tiers".
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Optional

try:
    import yaml
except ImportError:
    sys.exit("corpus_ingest_personal requires PyYAML. Install: pip install pyyaml")

try:
    from PIL import Image
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False


REPO_ROOT = Path(__file__).resolve().parent.parent
CORPUS = REPO_ROOT / "corpus"
STAGING = CORPUS / "_staging"
MANIFEST = CORPUS / "_manifest.json"
TAXONOMY_DIR = CORPUS / "_taxonomy"

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}
TEXT_EXTS = {".txt", ".md"}
MIME_BY_EXT = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".tif": "image/tiff", ".tiff": "image/tiff",
    ".webp": "image/webp",
    ".txt": "text/plain", ".md": "text/plain",
}
TODO_MARK = "TODO"
PLACEHOLDER = [TODO_MARK]
ALLOWED_BACKUP_SCHEMES = {"file", "icloud"}

KEBAB_RE = re.compile(r"[^a-z0-9-]+")


def kebab(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[_\s]+", "-", s)
    s = KEBAB_RE.sub("", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "item"


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def image_dims(path: Path) -> Optional[tuple[int, int]]:
    if not HAVE_PIL:
        return None
    try:
        with Image.open(path) as im:
            return im.size  # (width, height)
    except Exception:
        return None


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open() as f:
        return yaml.safe_load(f) or {}


def dump_yaml(doc: dict[str, Any]) -> str:
    return yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, default_flow_style=False)


def load_taxonomy_keys() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for name in ("themes", "mood", "register", "form"):
        p = TAXONOMY_DIR / f"{name}.yaml"
        data = load_yaml(p) if p.exists() else {}
        out[name] = set(data.keys()) if isinstance(data, dict) else set()
    return out


def today() -> str:
    return dt.date.today().isoformat()


def new_batch_id() -> str:
    return "personal-" + dt.datetime.now().strftime("%Y-%m-%d-%H%M%S")


# ---------- staging -----------------------------------------------------------

def build_image_sidecar(
    item_id: str, *,
    source_path: Path,
    citation: str,
    source_url: Optional[str],
    w: Optional[int],
    h: Optional[int],
    nocturne: bool,
) -> dict[str, Any]:
    title = item_id.replace("-", " ").title()
    doc: dict[str, Any] = {
        "id": item_id,
        "title": title,
        "artist": TODO_MARK,
        "year": None,
        "rights_tier": "personal_library",
        "source": "web",
    }
    if source_url:
        doc["source_url"] = source_url
    doc["citation"] = citation
    doc["medium"] = TODO_MARK
    if w and h:
        doc["pixel_width"] = int(w)
        doc["pixel_height"] = int(h)
    else:
        doc["pixel_width"] = TODO_MARK
        doc["pixel_height"] = TODO_MARK
    doc["panel_fidelity"] = TODO_MARK  # operator picks native | robust; color-dependent will be refused on commit
    doc["form"] = TODO_MARK
    doc["themes"] = list(PLACEHOLDER)
    doc["mood"] = list(PLACEHOLDER)
    doc["register"] = list(PLACEHOLDER)
    doc["added"] = today()
    if nocturne:
        doc["_destination_hint"] = "personal_library/nocturne"
    return doc


def build_text_sidecar(
    item_id: str, *,
    source_path: Path,
    citation: str,
    source_url: Optional[str],
    languages: list[str],
) -> dict[str, Any]:
    body = source_path.read_text(encoding="utf-8", errors="replace").strip() + "\n"
    lang = languages[0] if languages else "en"
    doc: dict[str, Any] = {
        "id": item_id,
        "title": item_id.replace("-", " ").title(),
        "author": TODO_MARK,
        "year": None,
        "rights_tier": "personal_library",
        "source": "web",
    }
    if source_url:
        doc["source_url"] = source_url
    doc["citation"] = citation
    doc["form"] = TODO_MARK
    doc["language"] = list(languages)
    if len(languages) == 1:
        doc["text_variants"] = {lang: body}
    else:
        # Multi-language — operator splits the body by hand.
        doc["text_variants"] = {lc: TODO_MARK for lc in languages}
        doc["_source_raw"] = body
    doc["themes"] = list(PLACEHOLDER)
    doc["mood"] = list(PLACEHOLDER)
    doc["register"] = list(PLACEHOLDER)
    doc["added"] = today()
    return doc


def enumerate_folder(folder: Path) -> list[Path]:
    files: list[Path] = []
    for p in sorted(folder.iterdir()):
        if p.name.startswith(".") or p.name.startswith("_"):
            continue
        if p.is_file() and p.suffix.lower() in (IMAGE_EXTS | TEXT_EXTS):
            files.append(p)
    return files


def stage(args: argparse.Namespace) -> int:
    folder = Path(args.folder).expanduser().resolve()
    if not folder.is_dir():
        print(f"error: --folder must be an existing directory: {folder}", file=sys.stderr)
        return 2
    if not args.citation:
        print("error: --citation is required", file=sys.stderr)
        return 2
    files = enumerate_folder(folder)
    if not files:
        print(f"error: no supported files in {folder} (expected extensions: "
              f"{sorted(IMAGE_EXTS | TEXT_EXTS)})", file=sys.stderr)
        return 2

    languages = [c.strip() for c in (args.language or "en").split(",") if c.strip()]
    batch_id = args.batch_id or new_batch_id()
    batch_dir = STAGING / batch_id
    sidecars_dir = batch_dir / "sidecars"
    binaries_dir = batch_dir / "binaries"

    print(f"staging batch: {batch_id}")
    print(f"source folder: {folder}")
    print(f"  files: {len(files)}")
    print(f"  destination: corpus/personal_library/{'nocturne/' if args.nocturne else ''}")
    print()

    if args.dry_run:
        for src in files:
            print(f"  {src.name}  →  [dry-run] would stage")
        return 0

    sidecars_dir.mkdir(parents=True, exist_ok=True)
    binaries_dir.mkdir(parents=True, exist_ok=True)

    staged: list[dict[str, Any]] = []
    for src in files:
        base_id = kebab((args.id_prefix or "") + src.stem) if args.id_prefix else kebab(src.stem)
        item_id = base_id
        ext = src.suffix.lower()
        if ext in IMAGE_EXTS:
            w_h = image_dims(src)
            doc = build_image_sidecar(
                item_id,
                source_path=src,
                citation=args.citation,
                source_url=args.source_url,
                w=w_h[0] if w_h else None,
                h=w_h[1] if w_h else None,
                nocturne=args.nocturne,
            )
            dest_bin = binaries_dir / f"{item_id}{ext}"
            shutil.copy2(src, dest_bin)
            staged.append({"id": item_id, "kind": "image", "bin": dest_bin.name})
        else:
            doc = build_text_sidecar(
                item_id,
                source_path=src,
                citation=args.citation,
                source_url=args.source_url,
                languages=languages,
            )
            staged.append({"id": item_id, "kind": "text", "bin": None})
        (sidecars_dir / f"{item_id}.yaml").write_text(dump_yaml(doc), encoding="utf-8")

    # Write README with the review checklist.
    readme = [
        f"# Batch `{batch_id}`",
        "",
        f"- source folder: `{folder}`",
        f"- citation: {args.citation}",
        f"- destination: `corpus/personal_library/{'nocturne/' if args.nocturne else ''}`",
        f"- files staged: {len(files)}",
        "",
        "## Review checklist",
        "",
        "Every `TODO` must be resolved before commit. Required edits per sidecar:",
        "",
        "- **image items**: `artist`, `year`, `medium`, `panel_fidelity` (`native` or `robust`; `color-dependent` items SHALL NOT be committed), `form`, `themes`, `mood`, `register`.",
        "- **text items**: `author`, `year`, `form`, `themes`, `mood`, `register`; for bilingual texts split `text_variants` into each language key.",
        "",
        "Every tag (themes, mood, register, form) must be a canonical key in `corpus/_taxonomy/`.",
        "",
        "## Commit",
        "",
        "When all sidecars are clean:",
        "",
        "```sh",
        f"corpus ingest-personal --commit --batch-id {batch_id}",
        "```",
        "",
        "## Staged items",
        "",
    ]
    for item in staged:
        readme.append(f"- `{item['id']}` ({item['kind']})")
    (batch_dir / "README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")

    print(f"staged {len(staged)} item(s) under corpus/_staging/{batch_id}/")
    print(f"review checklist: corpus/_staging/{batch_id}/README.md")
    print()
    print("next:")
    print(f"  1. edit sidecars under corpus/_staging/{batch_id}/sidecars/")
    print(f"  2. corpus ingest-personal --commit --batch-id {batch_id}")
    return 0


# ---------- commit ------------------------------------------------------------

def _has_todo(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() == TODO_MARK
    if isinstance(value, list):
        return any(_has_todo(v) for v in value)
    if isinstance(value, dict):
        return any(_has_todo(v) for v in value.values())
    return False


def validate_staged_sidecar(path: Path, doc: dict[str, Any], tax: dict[str, set[str]]) -> list[str]:
    errors: list[str] = []

    required_common = ("id", "title", "year", "rights_tier", "source", "citation", "form", "themes", "mood", "register", "added")
    for k in required_common:
        if k not in doc:
            errors.append(f"{path.name}: missing required field `{k}`")
        elif _has_todo(doc[k]):
            errors.append(f"{path.name}: `{k}` still has a TODO placeholder")

    if doc.get("rights_tier") != "personal_library":
        errors.append(f"{path.name}: rights_tier must be 'personal_library' (was {doc.get('rights_tier')!r})")

    # Image vs text disambiguation by field presence
    is_image = "pixel_width" in doc or "pixel_height" in doc or "panel_fidelity" in doc or "artist" in doc
    is_text = "text" in doc or "text_variants" in doc or "body_files" in doc

    if is_image:
        for k in ("artist", "medium", "pixel_width", "pixel_height", "panel_fidelity"):
            if k not in doc:
                errors.append(f"{path.name}: image item missing `{k}`")
            elif _has_todo(doc[k]):
                errors.append(f"{path.name}: image `{k}` still has a TODO placeholder")
        if doc.get("panel_fidelity") == "color-dependent":
            errors.append(f"{path.name}: panel_fidelity 'color-dependent' cannot be committed")
        # pixel dims must be integers
        for k in ("pixel_width", "pixel_height"):
            v = doc.get(k)
            if isinstance(v, int) and v <= 0:
                errors.append(f"{path.name}: {k} must be a positive integer")
            if isinstance(v, str) and v != TODO_MARK:
                errors.append(f"{path.name}: {k} must be an integer (got string)")

    if is_text:
        if "author" not in doc or _has_todo(doc.get("author")):
            errors.append(f"{path.name}: text item `author` still a TODO placeholder")
        if "text" not in doc and not doc.get("text_variants") and not doc.get("body_files"):
            errors.append(f"{path.name}: text item must have `text` or `text_variants` or `body_files`")
        if "text_variants" in doc and _has_todo(doc.get("text_variants")):
            errors.append(f"{path.name}: text_variants still carry TODO for at least one language")

    # Taxonomy membership
    for field_name in ("themes", "mood", "register"):
        v = doc.get(field_name) or []
        if not isinstance(v, list) or not v:
            errors.append(f"{path.name}: {field_name} must be a non-empty array")
            continue
        for term in v:
            if term == TODO_MARK or term not in tax[field_name]:
                errors.append(f"{path.name}: {field_name} value '{term}' not in corpus/_taxonomy/{field_name}.yaml")
    form_v = doc.get("form")
    if isinstance(form_v, str) and form_v != TODO_MARK and form_v not in tax["form"]:
        errors.append(f"{path.name}: form '{form_v}' not in corpus/_taxonomy/form.yaml")

    # Orientation-aware resolution floor (images only)
    if is_image:
        w = doc.get("pixel_width")
        h = doc.get("pixel_height")
        if isinstance(w, int) and isinstance(h, int):
            if w > h and w < 1080:
                errors.append(f"{path.name}: landscape fill-axis {w} < 1080")
            elif h >= w and h < 693:
                errors.append(f"{path.name}: portrait fill-axis {h} < 693")

    return errors


def make_backup_uri(scheme: str, base: Optional[str], target: Path) -> str:
    if scheme == "file":
        # Default: absolute file:// URI of the committed binary path.
        return f"file://{target.resolve()}"
    if scheme == "icloud":
        if not base:
            base = "icloud:///Corpus"
        if not base.startswith("icloud://"):
            base = f"icloud://{base.lstrip('/')}"
        return f"{base.rstrip('/')}/{target.name}"
    raise ValueError(f"unsupported backup scheme: {scheme}")


def commit(args: argparse.Namespace) -> int:
    if not args.batch_id:
        print("error: --commit requires --batch-id", file=sys.stderr)
        return 2
    batch_dir = STAGING / args.batch_id
    if not batch_dir.is_dir():
        print(f"error: no staging dir at {batch_dir}", file=sys.stderr)
        return 2
    sidecars_dir = batch_dir / "sidecars"
    binaries_dir = batch_dir / "binaries"

    tax = load_taxonomy_keys()

    sidecars = sorted(sidecars_dir.glob("*.yaml")) if sidecars_dir.is_dir() else []
    if not sidecars:
        print(f"error: no sidecars in {sidecars_dir}", file=sys.stderr)
        return 2

    errors: list[str] = []
    parsed: list[tuple[Path, dict[str, Any]]] = []
    for path in sidecars:
        try:
            doc = load_yaml(path)
        except yaml.YAMLError as e:
            errors.append(f"{path.name}: YAML parse failure: {e}")
            continue
        errors.extend(validate_staged_sidecar(path, doc, tax))
        parsed.append((path, doc))

    if errors:
        print(f"staged batch {args.batch_id} has {len(errors)} error(s); cannot commit:\n", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return 1

    backup_scheme = args.backup_scheme or "file"
    if backup_scheme not in ALLOWED_BACKUP_SCHEMES:
        print(f"error: personal-library permits only operator-controlled schemes "
              f"({sorted(ALLOWED_BACKUP_SCHEMES)}); got '{backup_scheme}'", file=sys.stderr)
        return 2

    # Prepare manifest append set.
    if MANIFEST.exists():
        manifest_doc = json.loads(MANIFEST.read_text())
    else:
        manifest_doc = {"schema_version": 1, "created": today(), "entries": []}
    existing_paths = {e["path"] for e in manifest_doc.get("entries", [])}

    # Plan moves.
    plan: list[dict[str, Any]] = []
    for path, doc in parsed:
        item_id = doc["id"]
        is_image = "pixel_width" in doc
        dest_parent = CORPUS / "personal_library"
        if doc.get("_destination_hint") == "personal_library/nocturne":
            dest_parent = dest_parent / "nocturne"
        dest_parent.mkdir(parents=True, exist_ok=True)
        if is_image:
            # Locate the staged binary by id + any image ext.
            staged_bins = [p for p in binaries_dir.glob(f"{item_id}.*") if p.suffix.lower() in IMAGE_EXTS]
            if not staged_bins:
                errors.append(f"{item_id}: no staged binary under {binaries_dir}")
                continue
            src_bin = staged_bins[0]
            dest_bin = dest_parent / src_bin.name
            plan.append({
                "id": item_id,
                "kind": "image",
                "sidecar_src": path,
                "sidecar_dst": dest_parent / f"{item_id}.yaml",
                "bin_src": src_bin,
                "bin_dst": dest_bin,
            })
        else:
            plan.append({
                "id": item_id,
                "kind": "text",
                "sidecar_src": path,
                "sidecar_dst": dest_parent / f"{item_id}.yaml",
                "bin_src": None,
                "bin_dst": None,
            })

    if errors:
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return 1

    # Guard against collisions with existing items.
    for p in plan:
        if p["sidecar_dst"].exists():
            errors.append(f"{p['id']}: sidecar already exists at {p['sidecar_dst']} (refusing to overwrite)")
        if p["bin_dst"] and p["bin_dst"].exists():
            errors.append(f"{p['id']}: binary already exists at {p['bin_dst']} (refusing to overwrite)")
    if errors:
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return 1

    print(f"commit plan ({len(plan)} item(s)):")
    for p in plan:
        print(f"  {p['id']} ({p['kind']})  →  {p['sidecar_dst'].relative_to(REPO_ROOT)}")

    if args.dry_run:
        print("(dry-run; no files moved)")
        return 0

    new_entries: list[dict[str, Any]] = []
    for p in plan:
        if p["bin_src"]:
            shutil.copy2(p["bin_src"], p["bin_dst"])
            rel = p["bin_dst"].relative_to(REPO_ROOT).as_posix()
            if rel in existing_paths:
                # Replace in place to keep order stable? For simplicity, skip.
                pass
            else:
                new_entries.append({
                    "path": rel,
                    "sha256": sha256_of(p["bin_dst"]),
                    "bytes": p["bin_dst"].stat().st_size,
                    "mime": MIME_BY_EXT.get(p["bin_dst"].suffix.lower(), "application/octet-stream"),
                    "backup_uri": make_backup_uri(backup_scheme, args.backup_base, p["bin_dst"]),
                })
        # Strip the _destination_hint before landing
        doc = load_yaml(p["sidecar_src"])
        doc.pop("_destination_hint", None)
        p["sidecar_dst"].write_text(dump_yaml(doc), encoding="utf-8")

    if new_entries:
        manifest_doc["entries"].extend(new_entries)
        MANIFEST.write_text(json.dumps(manifest_doc, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")
        print(f"manifest: appended {len(new_entries)} entrie(s)")

    # Clean up staging on success.
    shutil.rmtree(batch_dir)
    print(f"committed batch {args.batch_id}; staging dir removed")
    print("run `corpus validate` to confirm the corpus is still clean.")
    return 0


# ---------- entry -------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        prog="corpus ingest-personal",
        description="Ingest a folder of web-downloaded images / typed text fragments into the personal-library tier.",
    )
    ap.add_argument("--folder", help="Source folder to ingest (phase 1 / stage).")
    ap.add_argument("--citation", help="Bibliographic citation shared by every item.")
    ap.add_argument("--batch-id", help="Batch identifier; defaults to personal-YYYY-MM-DD-HHMMSS.")
    ap.add_argument("--nocturne", action="store_true", help="Route items into personal_library/nocturne/.")
    ap.add_argument("--language", help="Text language(s), comma-sep ISO 639-1 codes. Default: en.")
    ap.add_argument("--source-url", help="Optional source URL shared by all items (e.g., museum page).")
    ap.add_argument("--id-prefix", help="Optional prefix prepended to each generated id.")
    ap.add_argument("--backup-scheme", choices=sorted(ALLOWED_BACKUP_SCHEMES), default=None,
                    help="Backup URI scheme used on commit. Default: file.")
    ap.add_argument("--backup-base", help="Override base location for the backup URI (icloud only).")
    ap.add_argument("--commit", action="store_true", help="Phase 2: commit a staged batch.")
    ap.add_argument("--dry-run", action="store_true", help="Show what would happen; don't write files.")
    args = ap.parse_args()

    if args.commit:
        return commit(args)
    if not args.folder:
        ap.error("either --folder (to stage) or --commit --batch-id (to commit) is required")
    return stage(args)


if __name__ == "__main__":
    sys.exit(main())

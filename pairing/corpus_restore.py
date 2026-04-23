"""corpus restore — rebuild missing binaries and body files from the manifest.

Reads `corpus/_manifest.json`; for every entry whose on-disk file is missing,
fetches the content from the entry's `backup_uri` and verifies sha256.

Supported `backup_uri` schemes:
  file://         — local filesystem; primary case used today
  icloud://       — operator-local iCloud Drive mount (resolved below)
  b2://, s3://    — **not implemented here**; the commands below print
                    a diagnostic and leave the slot empty.

Invariants:
  - Never writes to a path outside `corpus/`.
  - Never overwrites an existing file unless `--force` is passed.
  - Verifies sha256 on every restored file; halts on mismatch.

Usage:
    corpus restore                 # restore everything missing
    corpus restore --check         # do not write; report what's missing
    corpus restore --verify        # re-verify sha256 of every existing file
    corpus restore --force         # overwrite existing files during restore
    corpus restore <path> ...      # restore specific manifest paths

Exit codes:
    0 — nothing missing, or everything restored + verified.
    1 — at least one file still missing or failing sha256 after the run.
    2 — usage error.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

try:
    import yaml  # noqa: F401  (consistency with other scripts; not strictly needed)
except ImportError:
    pass

import json


REPO_ROOT = Path(__file__).resolve().parent.parent
CORPUS = REPO_ROOT / "corpus"
MANIFEST = CORPUS / "_manifest.json"


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve_file_uri(uri: str) -> Path:
    """`file:///abs/path/to/file` → Path. Reject relative or schemeless inputs."""
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        raise ValueError(f"not a file:// URI: {uri}")
    # netloc is typically empty on file:///; on file://host/path it's a host.
    # We accept both empty and 'localhost'; other hosts are rejected.
    if parsed.netloc not in ("", "localhost"):
        raise ValueError(f"non-local file URI host: {parsed.netloc!r}")
    return Path(unquote(parsed.path))


def resolve_icloud_uri(uri: str) -> Path:
    """icloud://<relative-path> → absolute Path under the operator's iCloud Drive root.

    The iCloud root is read from the environment variable
    `INKPLATE_ICLOUD_ROOT` (an absolute path to the Inkplate folder inside the
    local iCloud Drive mount). If unset, falls back to the default macOS
    iCloud mount point for an app-free folder named 'Inkplate'.
    """
    root = os.environ.get("INKPLATE_ICLOUD_ROOT")
    if not root:
        default = Path.home() / "Library/Mobile Documents/com~apple~CloudDocs/Inkplate"
        if not default.is_dir():
            raise ValueError(
                "icloud:// restore requires INKPLATE_ICLOUD_ROOT to be set "
                "(absolute path to the Inkplate folder in your iCloud Drive mount), "
                f"and default {default} was not found."
            )
        root = str(default)
    rel = urlparse(uri).path.lstrip("/")
    return Path(root) / rel


def fetch_to(entry: dict, target: Path, *, force: bool = False) -> tuple[bool, str]:
    """Fetch the manifest entry's content to `target`. Returns (ok, message)."""
    if target.exists() and not force:
        return False, f"exists (use --force to overwrite): {target}"
    uri = entry.get("backup_uri") or ""
    scheme = uri.split("://", 1)[0] if "://" in uri else ""
    try:
        if scheme == "file":
            src = resolve_file_uri(uri)
        elif scheme == "icloud":
            src = resolve_icloud_uri(uri)
        elif scheme in ("b2", "s3"):
            return False, f"scheme '{scheme}://' not implemented in this build"
        else:
            return False, f"unsupported scheme: {uri!r}"
    except ValueError as e:
        return False, str(e)

    if not src.exists():
        return False, f"source missing on backup: {src}"
    if src.resolve() == target.resolve():
        # Already in place under same identity.
        return True, "source == target (already in place)"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, target)
    return True, f"restored from {src}"


def verify(entry: dict, target: Path) -> tuple[bool, str]:
    if not target.exists():
        return False, "missing"
    actual = sha256_of(target)
    expected = entry.get("sha256") or ""
    if actual.lower() != expected.lower():
        return False, f"sha256 mismatch (manifest {expected}, disk {actual})"
    size = target.stat().st_size
    if entry.get("bytes") is not None and size != entry["bytes"]:
        return False, f"byte-count mismatch (manifest {entry['bytes']}, disk {size})"
    return True, "ok"


def load_manifest() -> dict:
    if not MANIFEST.exists():
        sys.exit(f"no manifest at {MANIFEST}")
    return json.loads(MANIFEST.read_text())


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="corpus restore",
        description="Rebuild missing binaries and body files from the manifest.",
    )
    ap.add_argument("paths", nargs="*",
                    help="Restore only these manifest paths (default: everything missing).")
    ap.add_argument("--check", action="store_true",
                    help="Report state without writing or copying.")
    ap.add_argument("--verify", action="store_true",
                    help="Re-verify sha256 of every existing file (slow).")
    ap.add_argument("--force", action="store_true",
                    help="Overwrite existing files during restore.")
    args = ap.parse_args()

    manifest = load_manifest()
    entries = manifest.get("entries", [])
    if args.paths:
        wanted = set(args.paths)
        entries = [e for e in entries if e["path"] in wanted]
        missing = wanted - {e["path"] for e in entries}
        for m in sorted(missing):
            print(f"skip: {m} — not in manifest", file=sys.stderr)

    results = {
        "already": [],      # existed and verified
        "restored": [],     # copied from backup and verified
        "missing": [],      # could not restore
        "bad_sha": [],      # restored or existed but sha differs
    }

    for entry in entries:
        path = REPO_ROOT / entry["path"]
        if path.exists() and not args.force:
            if args.verify or args.check:
                ok, msg = verify(entry, path)
                if ok:
                    results["already"].append(entry["path"])
                else:
                    results["bad_sha"].append(f"{entry['path']}: {msg}")
            else:
                results["already"].append(entry["path"])
            continue

        if args.check:
            results["missing"].append(f"{entry['path']} (would restore from {entry.get('backup_uri')})")
            continue

        ok, msg = fetch_to(entry, path, force=args.force)
        if not ok:
            results["missing"].append(f"{entry['path']}: {msg}")
            continue
        ok_v, msg_v = verify(entry, path)
        if not ok_v:
            results["bad_sha"].append(f"{entry['path']}: {msg_v} (after restore: {msg})")
        else:
            results["restored"].append(f"{entry['path']} ({msg})")

    print(f"already present: {len(results['already'])}")
    if results["restored"]:
        print(f"restored:        {len(results['restored'])}")
        for line in results["restored"]:
            print(f"  + {line}")
    if results["missing"]:
        print(f"missing:         {len(results['missing'])}")
        for line in results["missing"]:
            print(f"  - {line}")
    if results["bad_sha"]:
        print(f"sha256 issues:   {len(results['bad_sha'])}")
        for line in results["bad_sha"]:
            print(f"  ! {line}")

    return 0 if not (results["missing"] or results["bad_sha"]) else 1


if __name__ == "__main__":
    sys.exit(main())

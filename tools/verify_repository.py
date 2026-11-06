#!/usr/bin/env python3
"""Verify published files; --update snapshots the tracked working tree before commit."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "repository-manifest.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tracked_paths() -> set[str] | None:
    if not (ROOT / ".git").exists():
        return None  # GitHub source ZIP: verify listed content without an index.
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True
    )
    return set(result.stdout.decode().split("\0")) - {"", MANIFEST.name}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update", action="store_true")
    args = parser.parse_args()
    tracked = tracked_paths()
    if args.update:
        if not tracked:
            parser.error("Stage the intended repository files with git add first.")
        data = {
            "schema_version": 1,
            "scope": "Git-tracked working-tree files; excludes this manifest itself. Local vendor downloads and build output are not included.",
            "sha256": {name: digest(ROOT / name) for name in sorted(tracked)},
        }
        MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        print(f"Updated {len(tracked)} published file hashes; stage the manifest before committing.")
        return 0

    expected = json.loads(MANIFEST.read_text())["sha256"]
    errors = []
    if tracked is not None and tracked != set(expected):
        errors += [f"unlisted tracked file: {p}" for p in sorted(tracked - set(expected))]
        errors += [f"no longer tracked: {p}" for p in sorted(set(expected) - tracked)]
    for name, wanted in expected.items():
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file():
            errors.append(f"missing or invalid file: {name}")
        elif digest(path) != wanted:
            errors.append(f"changed content: {name}")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"PASS: {len(expected)} published file hashes. Local vendor source archives are outside this check.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

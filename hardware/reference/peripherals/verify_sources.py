#!/usr/bin/env python3
"""Verify archived manufacturer assets without network access or source mutation."""
from pathlib import Path
import hashlib
import json
import sys


def main():
    directory = Path(__file__).resolve().parent
    repository = directory.parents[2]
    manifest = json.loads((directory / "sources.json").read_text())
    failures = []
    checked = 0
    online_only = 0
    for source in manifest["sources"]:
        identifier = source["id"]
        relative = source.get("local_path")
        if relative is None:
            online_only += 1
            if "sha256" in source or "bytes" in source:
                failures.append(f"{identifier}: online-only source claims local hash/bytes")
            continue
        path = repository / relative
        if not path.resolve().is_relative_to(repository.resolve()) or "build" in Path(relative).parts:
            failures.append(f"{identifier}: invalid archive path {relative}")
            continue
        if not path.is_file():
            failures.append(f"{identifier}: missing {relative}")
            continue
        data = path.read_bytes()
        if len(data) != source["bytes"]:
            failures.append(f"{identifier}: byte count mismatch")
        if hashlib.sha256(data).hexdigest() != source["sha256"]:
            failures.append(f"{identifier}: SHA-256 mismatch")
        checked += 1
    print(json.dumps({"result": "FAIL" if failures else "PASS",
                      "local_files_checked": checked, "online_only_sources": online_only,
                      "failures": failures}, ensure_ascii=False, indent=2))
    return bool(failures)


if __name__ == "__main__":
    sys.exit(main())

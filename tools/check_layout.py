#!/usr/bin/env python3
"""Check the fixed 16 MiB prototype OTA layout without importing ESP-IDF."""
import csv
from pathlib import Path
import sys


def validate_layout(path):
    entries = {}
    previous_end = 0x9000
    for row in csv.reader(path.read_text().splitlines()):
        if not row or row[0].lstrip().startswith("#"):
            continue
        name, kind, subtype, start, size, *_ = (x.strip() for x in row)
        start, size = int(start, 0), int(size, 0)
        if name in entries or size <= 0 or start < previous_end:
            raise ValueError(f"{name}: duplicate, empty or overlapping partition")
        if start % 4096 or size % 4096 or (kind == "app" and start % 65536):
            raise ValueError(f"{name}: invalid partition alignment")
        if start + size > 16 * 1024 * 1024:
            raise ValueError(f"{name}: exceeds 16 MiB Flash")
        entries[name] = (kind, subtype, start, size)
        previous_end = start + size
    for name in ("ota_0", "ota_1"):
        if name not in entries or entries[name][:2] != ("app", name):
            raise ValueError(f"missing {name} application slot")
    if entries["ota_0"][3] != entries["ota_1"][3]:
        raise ValueError("OTA slots must have equal capacity")
    if "otadata" not in entries or entries["otadata"][:2] != ("data", "ota") or entries["otadata"][3] != 0x2000:
        raise ValueError("otadata must occupy two sectors")
    return entries


if __name__ == "__main__":
    try:
        layout = validate_layout(Path(sys.argv[1]))
    except (ValueError, OSError, IndexError) as exc:
        sys.exit(f"layout validation failed: {exc}")
    print(f"layout: {len(layout)} partitions within 16 MiB; OTA slots {layout['ota_0'][3] // 1024} KiB each")

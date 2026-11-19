#!/usr/bin/env python3
"""Validate the N16R8 profile before generating bootstrap metadata (no GPIO I/O)."""
import argparse
import json
from pathlib import Path
import re

AVAILABLE = set(range(22)) | set(range(38, 49))
STRAPPING = {0, 3, 45, 46}


def validate(profile):
    if not isinstance(profile, dict):
        raise ValueError("board profile must be an object")
    if profile.get("schema_version") != 1:
        raise ValueError("unsupported board schema")
    if profile.get("module") != "ESP32-S3-WROOM-1-N16R8":
        raise ValueError("this validator only supports the agreed N16R8 module")
    if not re.fullmatch(r"[a-z][a-z0-9_]*", profile.get("id", "")):
        raise ValueError("invalid board ID")
    if profile.get("flash_bytes") != 16 * 1024 * 1024 or profile.get("psram_bytes") != 8 * 1024 * 1024:
        raise ValueError("N16R8 requires 16 MiB Flash and 8 MiB PSRAM")
    if type(profile.get("sd_bus_width")) is not int or profile["sd_bus_width"] not in (1, 4):
        raise ValueError("unsupported SD bus width")
    pins = profile.get("pins", {})
    if not isinstance(pins, dict) or not pins:
        raise ValueError("board pins are required")
    inputs = set(profile.get("input_only_roles", []))
    acknowledged = set(profile.get("acknowledged_strapping_roles", []))
    if not inputs <= pins.keys() or not acknowledged <= pins.keys():
        raise ValueError("pin annotations contain an unknown role")
    seen = {}
    for role, gpio in pins.items():
        if type(gpio) is not int or gpio not in AVAILABLE:
            raise ValueError(f"{role}: GPIO {gpio} unavailable on N16R8")
        if gpio in seen:
            raise ValueError(f"GPIO {gpio} reused by {seen[gpio]} and {role}")
        seen[gpio] = role
        if gpio == 46 and role not in inputs:
            raise ValueError("GPIO46 is input-only")
        if gpio in STRAPPING and role not in acknowledged:
            raise ValueError(f"{role}: strapping GPIO needs an explicit review annotation")
        if gpio in (19, 20) and role != {19: "usb_dm", 20: "usb_dp"}[gpio]:
            raise ValueError("GPIO19/20 are reserved for USB")
    for role, gpio in (("usb_dm", 19), ("usb_dp", 20), ("key_boot", 0)):
        if pins.get(role) != gpio:
            raise ValueError(f"{role} must remain on GPIO{gpio}")
    sd_required = {"sd_clk", "sd_cmd", "sd_d0"}
    if profile["sd_bus_width"] == 4:
        sd_required.update(("sd_d1", "sd_d2", "sd_d3"))
    if not sd_required <= pins.keys():
        raise ValueError(f"SD bus missing signals: {sorted(sd_required - pins.keys())}")
    for dimension in ("width", "height"):
        value = profile.get("display", {}).get(dimension)
        if type(value) is not int or value <= 0:
            raise ValueError(f"invalid display {dimension}")
    return profile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", type=Path)
    parser.add_argument("--header", type=Path)
    args = parser.parse_args()
    try:
        profile = validate(json.loads(args.profile.read_text()))
    except (ValueError, OSError) as exc:
        parser.exit(1, f"board validation failed: {exc}\n")
    if args.header:
        args.header.parent.mkdir(parents=True, exist_ok=True)
        args.header.write_text(
            "/* Generated metadata only; this header does not configure GPIOs. */\n#pragma once\n"
            f'#define EPP_BOARD_ID "{profile["id"]}"\n'
            f'#define EPP_BOARD_MODULE "{profile["module"]}"\n'
            f'#define EPP_BOARD_FLASH_BYTES {profile["flash_bytes"]}u\n'
            f'#define EPP_BOARD_PSRAM_BYTES {profile["psram_bytes"]}u\n'
        )
    print(f'board {profile["id"]}: {len(profile["pins"])} unique GPIOs validated; schematic review still required')


if __name__ == "__main__":
    main()

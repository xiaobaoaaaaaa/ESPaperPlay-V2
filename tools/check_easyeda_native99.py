#!/usr/bin/env python3
"""Compare an EasyEDA native netlist with the independently audited pin mapping.

Read-only. Does not import KiCad data or modify CAD. This electrical comparison
is necessary but does not replace schematic DRC, PCB DRC, or manufacturing checks.
"""
import argparse
import collections
import hashlib
import json
from pathlib import Path


def check(netlist_path, mapping_path, reference_path):
    actual = json.loads(netlist_path.read_text())
    mapping = json.loads(mapping_path.read_text())["by_reference"]
    references = {c["reference"]: c for c in json.loads(reference_path.read_text())["components"]}
    errors, by_ref = [], {}
    for uid, c in actual["components"].items():
        ref = c["props"].get("Designator")
        if ref in by_ref:
            errors.append({"kind": "duplicate_designator", "reference": ref})
        by_ref[ref] = c
    for ref in sorted(set(by_ref) ^ set(mapping)):
        errors.append({"kind": "component_set_difference", "reference": ref})
    expected_pin_count = connected_pin_count = 0
    nets = collections.Counter()
    for ref, expected in mapping.items():
        if ref not in by_ref:
            continue
        c = by_ref[ref]
        pins = c["pinInfoMap"]
        for n in sorted(set(pins) ^ set(expected["pins"])):
            errors.append({"kind": "pin_set_difference", "reference": ref, "pin": n})
        for n, p in expected["pins"].items():
            expected_pin_count += 1
            wanted = "" if p["no_connect"] else p["net"]
            got = pins.get(n, {}).get("net", "MISSING_PIN")
            if wanted != got:
                errors.append({"kind": "net_mismatch", "reference": ref, "pin": n, "expected": wanted, "actual": got})
            if wanted:
                connected_pin_count += 1
                nets[wanted] += 1
        props = c["props"]
        dnp = references[ref]["dnp"]
        if props.get("Add into BOM") != ("no" if dnp else "yes"):
            errors.append({"kind": "assembly_status_mismatch", "reference": ref})
        if props.get("Convert to PCB") != "yes":
            errors.append({"kind": "missing_pcb_component", "reference": ref})
        if not props.get("NativeSourceDeviceUUID") or not props.get("NativeSourceLibraryUUID"):
            errors.append({"kind": "missing_native_provenance", "reference": ref})
    special = {
        "R602": {"Manufacturer Part": "WFMB2010R4700FEA", "Supplier Part": "", "Value": "470mΩ"},
        "C501": {"Manufacturer Part": "", "Supplier Part": "", "Value": "TUNE / DNP"},
        "C502": {"Manufacturer Part": "", "Supplier Part": "", "Value": "TUNE / DNP"},
    }
    for ref, checks in special.items():
        props = by_ref.get(ref, {}).get("props", {})
        for key, wanted in checks.items():
            if props.get(key) != wanted:
                errors.append({"kind": "retained_catalog_attribute", "reference": ref, "field": key, "expected": wanted, "actual": props.get(key)})
    return {
        "status": "PASS" if not errors else "FAIL",
        "scope": "Native schematic electrical mapping and selected BOM metadata only; PCB/CAM not certified",
        "components": len(by_ref), "native_logical_pins": expected_pin_count,
        "connected_pins": connected_pin_count, "intentional_nc_pins": expected_pin_count - connected_pin_count,
        "named_nets": len(nets), "dnp": sorted(r for r, c in references.items() if c["dnp"]),
        "inputs_sha256": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in [netlist_path, mapping_path, reference_path]},
        "errors": errors,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("netlist", type=Path)
    parser.add_argument("mapping", type=Path)
    parser.add_argument("reference", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = check(args.netlist, args.mapping, args.reference)
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(text)
    print(text, end="")
    return bool(report["errors"])


if __name__ == "__main__":
    raise SystemExit(main())

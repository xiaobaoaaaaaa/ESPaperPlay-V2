#!/usr/bin/env python3
"""Read-only comparison of an official epro2 archive and schematic source snapshots."""
import argparse
import collections
import hashlib
import json
import zipfile
from pathlib import Path


PRIMITIVES = {"WIRE", "COMPONENT", "ATTR", "TEXT"}


def records(text):
    for line in text.splitlines():
        if not line:
            continue
        header, body = line.split("||", 1)
        body = body.rstrip("|")
        yield json.loads(header), json.loads(body) if body else None


def normalized(kind, value):
    if value is None:
        return None
    value = dict(value)
    if kind == "ATTR":
        # The runtime reindexes attributes and expands the absent false default.
        value.pop("zIndex", None)
        if not value.get("strikeout"):
            value.pop("strikeout", None)
    return value


def check(directory):
    archive = directory / "ESPaperPlay-99-Native-WIP.epro2"
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:
            raise ValueError("Corrupt archive entry")
        entries = [n for n in z.namelist() if n.endswith(".epru")]
        if len(entries) != 1:
            raise ValueError("Expected exactly one native project log")
        content = z.read(entries[0]).decode()
    documents, types = {}, collections.Counter()
    current = client = None
    tombstones = 0
    for h, body in records(content):
        if h["type"] == "DOCHEAD":
            current, client = body["uuid"], body.get("client", "")
            documents.setdefault(current, {})
            types[body["docType"]] += 1
            continue
        if current is None:
            raise ValueError("Record outside a document")
        key = (h["type"], h.get("id"))
        ticket = h.get("ticket", 0)
        prior = documents[current].get(key)
        if prior and (ticket < prior[0] or (ticket == prior[0] and client > prior[1])):
            continue
        if body in (None, ""):
            tombstones += 1
            body = None
        documents[current][key] = (ticket, client, body)
    pages = json.loads((directory / "audit/page-uuids.json").read_text())
    results, errors = {}, []
    for name, uid in pages.items():
        source = {(h["type"], h.get("id")): b for h, b in records(
            (directory / "source" / (name + ".esch")).read_text()
        ) if h["type"] in PRIMITIVES and b not in (None, "")}
        actual = {k: v[2] for k, v in documents.get(uid, {}).items()
                  if k[0] in PRIMITIVES and v[2] is not None}
        differences = [k for k in source.keys() | actual.keys()
                       if normalized(k[0], source.get(k)) != normalized(k[0], actual.get(k))]
        results[name] = {"compared_records": len(source), "differences": len(differences)}
        if differences:
            errors.append({"page": name, "records": sorted(differences)})
    return {
        "status": "PASS" if not errors else "FAIL",
        "scope": "Schematic component, wire, attribute and text records only; no PCB/CAM certification",
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "document_types": dict(types), "tombstones_applied": tombstones,
        "normalization": "ATTR zIndex and absent/false strikeout flags only",
        "pages": results, "errors": errors,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_directory", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = check(args.project_directory)
    output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(output)
    print(output, end="")
    return bool(report["errors"])


if __name__ == "__main__":
    raise SystemExit(main())

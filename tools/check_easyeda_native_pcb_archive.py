#!/usr/bin/env python3
"""Read-only PCB/key-footprint snapshot comparison against an official epro2 log.

Exit 0 means the compared records, including the physical stack, agree. Exit 2
means geometry/rules agree but physical-stack persistence remains pending. Exit 1
means a critical mismatch or malformed input. This is not a DRC/CAM certificate.
"""
import argparse
import collections
import hashlib
import io
import json
import zipfile
from pathlib import Path


FOOTPRINT_REFS = ("U101", "U802", "U203", "U301", "U803", "J501", "SW301", "F501")
GEOMETRY = {
    "COMPONENT", "ATTR", "PAD", "VIA", "PAD_NET", "NET", "NET_CLASS",
    "LINE", "ARC", "POLY", "FILL", "REGION", "POUR", "COPPER", "TEARDROP",
    "TEXT", "IMAGE", "PICTURE", "DIMENSION", "GROUP", "PARTITION",
    "CONSTRAINT", "DIFF_PAIR", "EQ_LEN_GRP", "PAD_PAIR", "PANELIZE",
}
RULES = {"RULE", "RULE_SELECTOR", "RULE_TEMPLATE"}
EDITOR_ONLY = {
    "CANVAS": "Editor viewport, grid and editing origin preferences.",
    "ACTIVE_LAYER": "Currently selected editor layer.",
    "PRIMITIVE": "Primitive visibility/picking/color preferences, not geometry.",
    "PREFERENCE": "Interactive routing/editing preferences, not persisted copper.",
    "ELE_PLACEHOLDER": "Next-element counters, not physical elements.",
    "META": "Library/project document metadata; identity checked via DOCHEAD and footprint references.",
    "D3_ATTRIBUTE": "3D appearance/settings; not a replacement for LAYER_PHYS.",
    "SILK_OPTS": "Editor silkscreen foreground/background color preferences; actual silk geometry is compared.",
}
LAYER_DISPLAY_KEYS = {"show", "locked", "activeColor", "activateTransparency",
                      "inactiveColor", "inactiveTransparency"}
EMPTY_NET_SELECTOR_KEY = ("RULE_SELECTOR", '["RULE_SELECTOR",["NET",""]]')
EMPTY_NET_SELECTOR = {
    "ruleOrder": 4, "ruleKeyValue": {"NET_LENGTH_TOLERANCE": ["default", None]},
    "copperValue": {}, "innerPlaneValue": {}, "parent": None,
}
HEIGHT_KEY = ("RULE", '["RULE","HEIGHT","height"]')
DEFAULT_HEIGHT = {"ruleState": "DEFAULT", "ruleContext": {"unit": "mm", "maxHeight": 0}}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def records(text):
    """Split before stripping the terminator: tombstones can end with |||."""
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            header, body = line.split("||", 1)
            header = json.loads(header)
            body = body.rstrip("|")
            body = json.loads(body) if body else None
            if not isinstance(header, dict) or not isinstance(header.get("type"), str):
                raise ValueError("Invalid record header")
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Invalid native record at line {number}: {exc}") from exc
        yield header, body


def merge_documents(text):
    """Same ticket/client winner rule as check_easyeda_native_archive.py.

    Highest ticket wins; equal tickets choose lexicographically smaller client;
    equal ticket and client choose the later log record. Tombstones participate.
    """
    documents, headers = {}, collections.defaultdict(list)
    current = client = None
    stats = collections.Counter()
    for header, body in records(text):
        if header["type"] == "DOCHEAD":
            if not isinstance(body, dict) or not body.get("uuid"):
                raise ValueError("DOCHEAD without document UUID")
            current, client = body["uuid"], body.get("client", "")
            documents.setdefault(current, {})
            headers[current].append(body)
            stats["document_segments"] += 1
            continue
        if current is None:
            raise ValueError("Record outside a document")
        key = (header["type"], header.get("id"))
        if key[1] is not None and not isinstance(key[1], (str, int)):
            raise ValueError(f"Unsupported native record id: {key}")
        ticket = header.get("ticket", 0)
        if not isinstance(ticket, (int, float)) or isinstance(ticket, bool):
            raise ValueError(f"Invalid ticket: {ticket}")
        prior = documents[current].get(key)
        stats["raw_records"] += 1
        if prior:
            stats["repeated_record_keys"] += 1
        if prior and (ticket < prior[0] or (ticket == prior[0] and client > prior[1])):
            stats["superseded_records"] += 1
            continue
        if body is None or body == "":
            body = None
            stats["accepted_tombstones"] += 1
        documents[current][key] = (ticket, client, body)
    active = {uid: {k: v[2] for k, v in doc.items() if v[2] is not None}
              for uid, doc in documents.items()}
    return active, dict(headers), dict(stats)


def load_snapshot(path):
    data = path.read_bytes()
    docs, headers, stats = merge_documents(data.decode("utf-8"))
    if len(docs) != 1:
        raise ValueError(f"Expected one snapshot document: {path}")
    uid = next(iter(docs))
    return uid, docs[uid], {"path": str(path), "sha256": sha256(data),
                           "document_uuid": uid, "merge": stats, "headers": headers[uid]}


def same(left, right):
    # Treat JSON numeric representations 1 and 1.0 as equal, never false and 0.
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(same(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(same(a, b) for a, b in zip(left, right))
    return left == right


def sort_key(key):
    return key[0], str(key[1])


def diff_records(expected, actual):
    result = []
    for key in sorted(expected.keys() | actual.keys(), key=sort_key):
        if key not in expected or key not in actual or not same(expected[key], actual[key]):
            result.append({"type": key[0], "id": key[1],
                           "snapshot_present": key in expected, "archive_present": key in actual,
                           "snapshot": expected.get(key), "archive": actual.get(key)})
    return result


def counts(data):
    return dict(sorted(collections.Counter(k[0] for k in data).items()))


def selected(data, kinds):
    return {k: v for k, v in data.items() if k[0] in kinds}


def component_index(data):
    attrs = collections.defaultdict(dict)
    for (kind, _), body in data.items():
        if kind == "ATTR" and body.get("parentId") and body.get("key") in ("Designator", "Footprint"):
            parent, key = body["parentId"], body["key"]
            if key in attrs[parent]:
                raise ValueError(f"Ambiguous {key} attribute for component {parent}")
            attrs[parent][key] = body.get("value")
    result = {}
    for (kind, ident), body in data.items():
        if kind != "COMPONENT":
            continue
        values = dict(body.get("attrs", {}))
        values.update(attrs[ident])
        ref = values.get("Designator")
        if not ref or ref in result:
            raise ValueError(f"Missing/duplicate component designator: {ref}")
        result[ref] = {"component_id": ident, "footprint_uuid": values.get("Footprint")}
    return result


def layer_projection(data, substrate=False):
    return {k: {a: b for a, b in v.items() if a not in LAYER_DISPLAY_KEYS}
            for k, v in data.items() if k[0] == "LAYER" and
            (v.get("layerType") == "SUBSTRATE") == substrate}


def stack_summary(data):
    phys = []
    for (kind, ident), body in data.items():
        if kind == "LAYER_PHYS":
            layer_id = json.loads(ident)[1]
            phys.append({"layer_id": layer_id, **body,
                         "thickness_mm": body.get("thickness", 0) * .0254})
    active = sorted(body["layerId"] for (kind, _), body in data.items()
                    if kind == "LAYER" and body.get("use") and
                    body.get("layerType") in ("TOP", "BOTTOM", "SIGNAL", "PLANE"))
    ids = {v["layer_id"] for v in phys}
    zcounts = collections.Counter(v.get("zIndex") for v in phys)
    return {"physical_record_count": len(phys), "records": phys,
            "active_copper_layers": active,
            "active_copper_without_physical_record": sorted(set(active) - ids),
            "total_including_mask_mm": round(sum(v["thickness_mm"] for v in phys), 10),
            "duplicate_zindices": [z for z, n in zcounts.items() if n > 1]}


def check(directory, archive=None):
    archive = archive or directory / "ESPaperPlay-99-Native-WIP.epro2"
    archive_bytes = archive.read_bytes()
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as z:
        corrupt = z.testzip()
        if corrupt is not None:
            raise ValueError(f"Corrupt archive entry: {corrupt}")
        logs = [n for n in z.namelist() if n.endswith(".epru")]
        if len(logs) != 1:
            raise ValueError("Expected exactly one epru project log")
        log = z.read(logs[0])
    docs, headers, merge_stats = merge_documents(log.decode("utf-8"))
    uid, source, snapshot = load_snapshot(directory / "source/PCB-layout.epcb")
    actual = docs.get(uid)
    if actual is None or {h.get("docType") for h in headers[uid]} != {"PCB"}:
        raise ValueError(f"PCB {uid} absent or has unexpected document type in archive")
    errors, defaults = [], []
    known = GEOMETRY | RULES | set(EDITOR_ONLY) | {"LAYER", "LAYER_PHYS"}
    unknown = sorted({k[0] for k in source.keys() | actual.keys()} - known)
    if unknown:
        errors.append({"scope": "pcb", "unclassified_record_types": unknown})
    geometry_diff = diff_records(selected(source, GEOMETRY), selected(actual, GEOMETRY))
    layer_diff = diff_records(layer_projection(source), layer_projection(actual))
    rule_source, rule_actual = selected(source, RULES), selected(actual, RULES)
    # Two exact, observed runtime/archive defaults. No generic rule dropping.
    for key, body, side, reason in (
        (EMPTY_NET_SELECTOR_KEY, EMPTY_NET_SELECTOR, "snapshot",
         "Runtime-added selector of the empty net, containing only the default length-tolerance binding."),
        (HEIGHT_KEY, DEFAULT_HEIGHT, "archive",
         "Archive-only DEFAULT height rule with maxHeight=0; no physical/routing rule is discarded."),
    ):
        owner, other = (rule_source, rule_actual) if side == "snapshot" else (rule_actual, rule_source)
        if key in owner and key not in other and same(owner[key], body):
            defaults.append({"type": key[0], "id": key[1], "present_only_in": side,
                             "exact_body": owner[key], "reason": reason})
            del owner[key]
    rule_diff = diff_records(rule_source, rule_actual)
    for scope, differences in (("pcb_geometry_network", geometry_diff),
                               ("enabled_layers", layer_diff), ("pcb_rules", rule_diff)):
        if differences:
            errors.append({"scope": scope, "differences": differences})
    source_components, actual_components = component_index(source), component_index(actual)
    footprint_results = {}
    fp_editor = set(EDITOR_ONLY) | RULES | {"LAYER", "LAYER_PHYS"}
    for ref in FOOTPRINT_REFS:
        path = directory / "source/footprints" / (ref + ".efoo")
        fuid, fsource, finfo = load_snapshot(path)
        binding = source_components.get(ref)
        if not binding or binding != actual_components.get(ref) or binding["footprint_uuid"] != fuid:
            errors.append({"scope": "footprint_binding", "ref": ref,
                           "snapshot_binding": binding, "archive_binding": actual_components.get(ref),
                           "footprint_snapshot_uuid": fuid})
        factual = docs.get(fuid, {})
        if not factual or {h.get("docType") for h in headers.get(fuid, [])} != {"FOOTPRINT"}:
            errors.append({"scope": "missing_or_wrong_type_footprint", "ref": ref, "uuid": fuid})
        unknown_fp = sorted({k[0] for k in fsource.keys() | factual.keys()} - GEOMETRY - fp_editor)
        differences = diff_records(selected(fsource, GEOMETRY), selected(factual, GEOMETRY))
        if differences or unknown_fp:
            errors.append({"scope": "footprint_geometry", "ref": ref,
                           "differences": differences, "unclassified_record_types": unknown_fp})
        footprint_results[ref] = {
            "status": "PASS" if not differences and not unknown_fp and binding and
                      binding == actual_components.get(ref) and binding["footprint_uuid"] == fuid and
                      factual and {h.get("docType") for h in headers.get(fuid, [])} == {"FOOTPRINT"} else "FAIL",
            "snapshot": finfo, "pcb_binding": binding,
            "compared_snapshot_records": counts(selected(fsource, GEOMETRY)),
            "compared_archive_records": counts(selected(factual, GEOMETRY)),
            "excluded_snapshot_records": counts(selected(fsource, fp_editor)),
            "excluded_archive_records": counts(selected(factual, fp_editor)),
            "differences": differences,
        }
    stack_diff = diff_records(selected(source, {"LAYER_PHYS"}), selected(actual, {"LAYER_PHYS"}))
    substrate_diff = diff_records(layer_projection(source, True), layer_projection(actual, True))
    ss, ast = stack_summary(source), stack_summary(actual)
    stack_pending = bool(stack_diff or substrate_diff or
                         ast["active_copper_without_physical_record"] or ast["duplicate_zindices"])
    status = "FAIL" if errors else ("GEOMETRY_RULES_PASS_STACK_PENDING" if stack_pending else
                                    "GEOMETRY_RULES_STACK_SNAPSHOT_MATCH")
    return {
        "status": status, "scope": "Official archive versus PCB and eight native footprint snapshots; not connectivity, DRC, CAM, assembly, impedance, or manufacturer-stack certification.",
        "archive": {"path": str(archive), "sha256": sha256(archive_bytes),
                    "log_entry": logs[0], "log_sha256": sha256(log), "merge": merge_stats,
                    "document_count": len(docs)},
        "normalization": {
            "record_identity": "(type,id); no geometry IDs are remapped.",
            "ticket_client": "Highest ticket; equal ticket chooses lexicographically smaller DOCHEAD.client; equal ticket/client last record wins; tombstones applied.",
            "numeric": "Exact numeric equality only (1 equals1.0); boolean differs from number; no coordinate tolerance, rounding, or unit conversion in comparison.",
            "object_order": "JSON object order ignored; list order, null/absent fields, all geometry/attribute bodies retained.",
            "layer_display_fields_excluded": sorted(LAYER_DISPLAY_KEYS),
            "exact_default_representation_differences": defaults,
        },
        "excluded_editor_record_types": EDITOR_ONLY,
        "footprint_scope_note": "Footprint PAD/FILL/POLY/etc bodies, mask/paste expansions, pad numbers and ATTR records are compared exactly. Editor-generated footprint layer tables, board stack/rules and editor settings are not footprint geometry; board-owned rules/stack are separately checked on PCB.",
        "pcb": {"snapshot": snapshot, "archive_document_segments": headers[uid],
                "geometry_network_status": "FAIL" if geometry_diff else "PASS",
                "rules_status": "FAIL" if rule_diff else "PASS_WITH_EXPLICIT_DEFAULT_REPRESENTATION_DIFFERENCES" if defaults else "PASS",
                "layer_function_status": "FAIL" if layer_diff else "PASS",
                "compared_snapshot_geometry_records": counts(selected(source, GEOMETRY)),
                "compared_archive_geometry_records": counts(selected(actual, GEOMETRY)),
                "compared_rule_records": len(rule_source), "component_count": len(actual_components)},
        "physical_stack": {"status": "PENDING_NOT_ARCHIVALLY_EQUIVALENT" if stack_pending else "SNAPSHOT_MATCH_ONLY",
                           "raw_thickness_unit": "mil; multiplied by0.0254 only for human-readable summaries, never for comparison",
                           "snapshot": ss, "archive": ast, "differences": stack_diff,
                           "runtime_only_physical_layer_ids": sorted(
                               json.loads(d["id"])[1] for d in stack_diff
                               if d["snapshot_present"] and not d["archive_present"]),
                           "substrate_layer_differences": substrate_diff,
                           "archive_enabled_copper_layer_count": len(ast["active_copper_layers"]),
                           "caution": "Enabled copper layers do not prove a complete physical stack. Runtime-added/missing stack records are displayed, never normalized into PASS. No claim that the summed default thickness is the intended1.6mm manufacturer stack."},
        "footprints": footprint_results, "errors": errors,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_directory", type=Path)
    parser.add_argument("--archive", type=Path, help="Override official archive path; snapshots remain under project_directory/source")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = check(args.project_directory, args.archive)
    except (ValueError, KeyError, TypeError, OSError, zipfile.BadZipFile) as exc:
        report = {"status": "FAIL", "errors": [{"scope": "input", "message": str(exc)}]}
    output = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(output)
    print(output, end="")
    if report["status"] == "FAIL":
        return 1
    return 2 if report["status"] == "GEOMETRY_RULES_PASS_STACK_PENDING" else 0


if __name__ == "__main__":
    raise SystemExit(main())

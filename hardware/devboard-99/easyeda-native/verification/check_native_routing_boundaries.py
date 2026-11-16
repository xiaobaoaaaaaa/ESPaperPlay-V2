#!/usr/bin/env python3
"""Read-only native routing/manufacturing-boundary checks, complementary to DRC.

Checks via keepouts explicitly; does not certify complete connectivity, all
copper clearances, impedance, or unparsed runtime poured-copper caches.
"""
import argparse
import collections
import hashlib
import importlib.util
import json
import math
from pathlib import Path

from shapely.geometry import LineString
from native_exact_smd import exact_smd_pads

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
import native_source_geometry as fan
TOL = .0001  # Round-trip tolerance0.1um, not a relaxed manufacturing rule.
TRACE_KINDS = {"LINE", "ARC", "CARC", "POLY"}


def read_source(path):
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text())
        if data.get("schema") != "native-thermal-feature-baseline-v1":
            raise ValueError("Unsupported baseline JSON schema")
        return {(r["type"],r["id"]):r["body"] for r in data["records"]}
    docs, _, _ = fan.archive_helper.merge_documents(path.read_text())
    if len(docs) != 1:
        raise ValueError("Expected exactly one PCB source document")
    return next(iter(docs.values()))


def centerline_length(kind, body):
    if kind == "LINE":
        return math.hypot(body["endX"]-body["startX"], body["endY"]-body["startY"])*fan.MM
    if kind in ("ARC", "CARC"):
        chord = math.hypot(body["endX"]-body["startX"], body["endY"]-body["startY"])*fan.MM
        angle = abs(math.radians(body["angle"]))
        if not angle:
            return chord
        if angle >= 2*math.pi:
            raise ValueError("Ambiguous full-circle ARC")
        return chord/(2*abs(math.sin(angle/2)))*angle
    return fan.path_line(body["path"]).length


def preserve_review(source, baseline):
    fields = {
        "VIA": ("netName", "centerX", "centerY", "holeDiameter", "viaDiameter", "viaType",
                "topSolderExpansion", "bottomSolderExpansion", "unusedInnerLayers"),
        "LINE": ("netName", "layerId", "startX", "startY", "endX", "endY", "width"),
    }
    result, problems = [], []
    for (kind, ident), b in baseline.items():
        if kind not in fields or b.get("netName") != "GND":
            continue
        actual = source.get((kind, ident))
        changes = {k: {"baseline": b.get(k), "current": actual.get(k) if actual else None}
                   for k in fields[kind] if actual is None or not fan.archive_helper.same(b.get(k), actual.get(k))}
        row = {"type": kind, "id": ident, "status": "MISSING" if actual is None else "MODIFIED" if changes else "PRESERVED", "changes": changes}
        result.append(row)
        if changes:
            problems.append(row)
    count = collections.Counter(r["type"] for r in result)
    if count != {"VIA": 22, "LINE": 11}:
        problems.append({"status": "WRONG_BASELINE", "expected": {"VIA": 22, "LINE": 11}, "observed": dict(count)})
    return {"status": "FAIL" if problems else "PASS", "baseline_counts": dict(count),
            "preserved_count": sum(r["status"] == "PRESERVED" for r in result),
            "records": result, "findings": problems}


def check(args):
    source, state, pads, holes, extra, evidence = fan.load_inputs(args)
    items, holes, regions, board, unparsed = fan.source_geometry(source, pads, holes)
    baseline=read_source(args.baseline)
    exact_smd=exact_smd_pads(source,state,args.archive)
    exact_smd_index=fan.Index(exact_smd)
    baseline_thermal_ids={ident for(kind,ident),b in baseline.items()if kind=="VIA"and b.get("netName")=="GND"}
    new_via_smd_findings=[];new_via_smd_rows=[]
    tracks_vias = [i for i in items if i["kind"] in {"line", "arc", "carc", "poly", "via"}]
    errors = []
    stats = collections.Counter()
    minima = {"board_edge_mm": None, "npth_edge_to_copper_mm": None, "via_drill_edge_gap_mm": None}
    by_id = {i["id"]: i for i in items}
    def minimum(key, val):
        minima[key] = val if minima[key] is None else min(minima[key], val)
    for obj in tracks_vias:
        stats[obj["kind"]] += 1
        g = obj["g"]
        edge_distance = g.distance(board.boundary)
        minimum("board_edge_mm", edge_distance)
        if not board.buffer(-(.30-TOL)).covers(g):
            errors.append({"check": "board_edge_0p30", "id": obj["id"], "kind": obj["kind"], "net": obj["net"],
                           "inside_board": board.covers(g), "distance_mm": edge_distance})
        for region in regions:
            if obj["layers"] & region["layers"]:
                overlap = g.intersection(region["g"])
                if not overlap.is_empty and overlap.area > 1e-10:
                    errors.append({"check": "via_keepout" if obj["kind"] == "via" else "route_keepout",
                                   "id": obj["id"], "net": obj["net"], "region_id": region["id"],
                                   "overlap_mm2": overlap.area, "overlap_bbox_mm": list(overlap.bounds)})
        for hole in holes:
            if hole.get("npth"):
                distance = g.distance(hole["g"])
                minimum("npth_edge_to_copper_mm", distance)
                if distance+TOL < hole["clearance"]:
                    errors.append({"check": "npth_or_slot_clearance", "id": obj["id"], "net": obj["net"],
                                   "hole_id": hole["id"], "distance_mm": distance, "required_mm": hole["clearance"]})
        if obj["kind"] == "via":
            b = source[("VIA", obj["id"])]
            h = fan.disk(b["centerX"]*fan.MM, b["centerY"]*fan.MM, b["holeDiameter"]*fan.MM/2)
            if obj["id"] not in baseline_thermal_ids:
                nearby_smd=exact_smd_index.near(g,.5)or exact_smd
                nearest=min(nearby_smd,key=lambda p:g.distance(p["g"]))
                hole_nearest=min(nearby_smd,key=lambda p:h.distance(p["g"]))
                gap=g.distance(nearest["g"]);hole_gap=h.distance(hole_nearest["g"])
                annulus_contacts=[p["ref"]+"."+str(p["pin"])for p in nearby_smd if g.intersection(p["g"]).area>1e-10]
                drill_contacts=[p["ref"]+"."+str(p["pin"])for p in nearby_smd if h.intersection(p["g"]).area>1e-10]
                row={"id":obj["id"],"net":obj["net"],"xy_mm":[b["centerX"]*fan.MM,b["centerY"]*fan.MM],
                     "nearest_smd":nearest["ref"]+"."+str(nearest["pin"]),"pad_id":nearest["id"],
                     "copper_gap_mm":gap,"hole_to_pad_gap_mm":hole_gap,
                     "nearest_drill_smd":hole_nearest["ref"]+"."+str(hole_nearest["pin"]),
                     "via_annulus_overlaps_smd":bool(annulus_contacts),"annulus_overlapping_pads":annulus_contacts,
                     "drill_overlaps_smd":bool(drill_contacts),"drill_overlapping_pads":drill_contacts}
                new_via_smd_rows.append(row)
                if gap+TOL<.15:
                    finding={"check":"new_via_smd_copper_gap_0p15",**row,"required_mm":.15}
                    new_via_smd_findings.append(finding);errors.append(finding)
            for other in holes:
                if other["id"] == obj["id"]+"_hole":
                    continue
                gap = h.distance(other["g"])
                minimum("via_drill_edge_gap_mm", gap)
                if gap+TOL < .25:
                    errors.append({"check": "via_hole_edge_gap_0p25", "id": obj["id"],
                                   "other_hole_id": other["id"], "distance_mm": gap})
    inner_errors, layer_errors = [], []
    net_stats = collections.defaultdict(lambda: {"centerline_total_mm": 0, "trace_count": 0, "via_count": 0,
                                                "minimum_width_mm": None, "by_layer_mm": collections.defaultdict(float)})
    pours = {ident: b for (kind, ident), b in source.items() if kind == "POUR"}
    for (kind, ident), b in source.items():
        if not isinstance(b, dict):
            continue
        layer, net = b.get("layerId"), b.get("netName", "")
        if kind == "POURED":
            parent = b.get("targetId")
            if parent is None:
                key = json.loads(ident)
                parent = key[1] if len(key) == 2 and key[0] == "POURED" else None
            if parent not in pours:
                layer_errors.append({"id": ident, "type": kind, "reason": "missing_pour_parent"})
                continue
            layer, net = pours[parent]["layerId"], pours[parent]["netName"]
        if kind in TRACE_KINDS | {"FILL", "POUR", "POURED", "TEARDROP", "TEXT", "IMAGE", "PICTURE"}:
            if layer in (15, 16) and net != "GND":
                inner_errors.append({"id": ident, "type": kind, "layer": layer, "net": net})
            if kind in TRACE_KINDS and net and layer not in fan.COPPER:
                layer_errors.append({"id": ident, "type": kind, "layer": layer, "net": net,
                                     "reason": "networked_route_on_non_copper_layer"})
        if kind in TRACE_KINDS and layer in fan.COPPER:
            length = centerline_length(kind, b)
            width = b.get("width", 0)*fan.MM
            ns = net_stats[net]
            ns["centerline_total_mm"] += length
            ns["trace_count"] += 1
            ns["by_layer_mm"][str(layer)] += length
            ns["minimum_width_mm"] = width if ns["minimum_width_mm"] is None else min(width, ns["minimum_width_mm"])
        if kind == "VIA":
            net_stats[net]["via_count"] += 1
    errors.extend({"check": "inner_layer_non_gnd", **i} for i in inner_errors)
    errors.extend({"check": "layer_assignment", **i} for i in layer_errors)
    stack = fan.archive_helper.stack_summary(source)
    ids = {r["layer_id"] for r in stack["records"]}
    expected_ids = {3, 7, 5, 1, 361, 15, 362, 16, 363, 2, 6, 8, 4}
    actual_order = [r["layer_id"] for r in sorted(stack["records"], key=lambda r: r.get("zIndex", -1))]
    expected_order = [3, 7, 5, 1, 361, 15, 362, 16, 363, 2, 6, 8, 4]
    stack_ok = actual_order == expected_order and len(stack["records"]) == 13 and ids == expected_ids and not stack["duplicate_zindices"] and stack["active_copper_layers"] == [1, 2, 15, 16]
    if not stack_ok:
        errors.append({"check": "physical_stack_13_records_order", "record_count": len(stack["records"]),
                       "layer_ids": sorted(ids), "observed_order": actual_order, "expected_order": expected_order, "duplicate_zindices": stack["duplicate_zindices"], "active_copper_layers": stack["active_copper_layers"]})
    keepout_layers = collections.Counter(next(iter(r["layers"])) for r in regions if len(r["layers"]) == 1)
    if len(regions) != 24 or keepout_layers != {1: 6, 2: 6, 15: 6, 16: 6}:
        errors.append({"check": "keepout_inventory", "count": len(regions), "per_layer": dict(keepout_layers)})
    preserved = preserve_review(source, baseline)
    if preserved["findings"]:
        errors.append({"check": "existing_thermal_vias_and_ground_lines", "findings": preserved["findings"]})
    classes = json.loads((HERE / "routing-net-classes.json").read_text())
    power_names, signal_names = set(classes["power"]), set(classes["selected_signal"])
    totals = {}
    for net, ns in sorted(net_stats.items()):
        totals[net] = {**ns, "centerline_total_mm": round(ns["centerline_total_mm"], 6),
                       "by_layer_mm": {k: round(v, 6) for k, v in ns["by_layer_mm"].items()},
                       "class": "power" if net in power_names else "selected_signal" if net in signal_names else "other"}
    return {
        "status": "FAIL" if errors else "PASS_SCOPED_ROUTING_BOUNDARIES",
        "implementation_sha256":{p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in [Path(__file__),HERE/"native_exact_smd.py",HERE/"native_source_geometry.py"]},
        "scope": "Native LINE/ARC/CARC/POLY routes and VIA copper/drills versus keepouts, board edge and NPTH; layer usage, physical stack inventory and retained thermal features. Not a full DRC or manufacture release.",
        "inputs": {name: {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for name, path in
                   (("source", args.source), ("state", args.state), ("archive", args.archive), ("baseline", args.baseline))},
        "geometry_inventory": {"route_and_via_counts": dict(stats), "pads": len(pads), "drills_and_slots": len(holes),
                               "prohibit_regions": len(regions), "prohibit_regions_by_layer": dict(keepout_layers)},
        "minima": minima, "boundary_findings": errors,
        "inner_layers": {"status": "FAIL" if inner_errors else "PASS", "policy": "Explicit routes/fills/pours on15/16 must beGND. NonGND through-vias/PTH annuli are permitted traversal, with clearance checked separately by nativeDRC.", "findings": inner_errors},
        "physical_stack": {"status": "PASS_SOURCE_INVENTORY" if stack_ok else "FAIL", **stack,
                           "limit": "13 source records and four enabled copper layers are checked here; source inspection alone does not prove archive persistence or manufacturer-selected stack."},
        "preserved_thermal_features": preserved,
        "new_via_smd_review":{"status":"FAIL"if new_via_smd_findings else"PASS",
            "exempt_existing_thermal_via_ids":sorted(baseline_thermal_ids),"checked_new_vias":len(new_via_smd_rows),
            "required_copper_gap_mm":.15,"roundtrip_tolerance_mm":TOL,
            "geometry":"Exact native footprint source widths/centers/POLYGON/RECT corner percentage transformed by exact PCB pose; API rounded pad coordinates are not used for this distance.",
            "minimum_gap_mm":min((v["copper_gap_mm"]for v in new_via_smd_rows),default=None),
            "rows":new_via_smd_rows,"findings":new_via_smd_findings},
        "net_length_summary": {"method": "Sum of actual source trace centerlines, grouped bynet/layer; LINE andARC analytical, POLY arcs sampled at<=0.25deg. Branches and duplicate segments contribute separately; pads, vias, plane spread and component-internal lengths excluded.",
                               "not_end_to_end_or_matched_length_certification": True,
                               "power_path_note": "24path resistance/neck and USB/SD end-to-end delay/skew checks require their dedicated path reports tied to this same source hash.",
                               "nets": totals},
        "unparsed_or_uncredited_pour_records": unparsed,
        "limitations": [
            "RuntimePOURED pourFill has different internal coordinates; it is not decoded or assumed to be safe copper. Only its parent net/layer is checked here. Actual filled-copper/CAM keepout review remains required.",
            "This check intentionally does not repeat all foreign-copper pair clearances covered by nativeDRC.",
            "Board and footprint pads are obstacles/hole sources; this entry checks route/via boundaries, not everyexistingpad's own manufacturing geometry.",
            "Zero boundary findings does not prove completion of routing, GND plane connectivity, USB impedance, or charge-current/thermal performance.",
            "0.0001mm comparison tolerance only absorbs source rounding; nominal requirements remain0.30mm edge,0.30mm NPTH/slot (MIC0.20mm),0.25mm hole-edge gap.",
        ], "read_only": True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, default=HERE / "thermal-feature-baseline.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = check(args)
    except (ValueError, KeyError, TypeError, IndexError, OSError) as exc:
        result = {"status": "FAIL", "error": str(exc), "read_only": True}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps({"status": result["status"], "output": str(args.output),
                      "findings": len(result.get("boundary_findings", [])), "error": result.get("error")}, ensure_ascii=False))
    return int(result["status"] == "FAIL")


if __name__ == "__main__":
    raise SystemExit(main())

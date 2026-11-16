#!/usr/bin/env python3
"""Read-only native PCB/library geometry shared by routing and CAM checks.

Requires Shapely2.x. All coordinates are mm,+Yup. Native log precedence comes
from the tracked archive checker. Unsupported geometry and stale input snapshots
fail explicitly; runtime POURED caches never count as copper or connectivity.
"""
import importlib.util
import json
import math
import zipfile
from pathlib import Path

from shapely.affinity import rotate, scale, translate
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import nearest_points, unary_union
from shapely.strtree import STRtree

MM = .0254
COPPER = {1, 2, 15, 16}
ALL = frozenset(COPPER)
ROOT = Path(__file__).resolve().parents[4]
# Use the tracked canonical native-log merger: ticket/client precedence and
# tombstones must match the formal archive checker, never a simplified parser.
spec = importlib.util.spec_from_file_location("native_archive_check", ROOT / "tools/check_easyeda_native_pcb_archive.py")
archive_helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(archive_helper)

def native_polygon(path):
 """Decode native absolute-mil L/ARC paths; signed ARC sweeps are degrees.

 API POLYGON paths already include pad translation and rotation. ARC's angle
 is an instruction argument, never an x/y ordinate. Use exact segment ends
 and at most 0.25-degree steps (under 0.000002 mm chord error for U803).
 """
 def numbers(start,count):
  values=path[start:start+count]
  if len(values)!=count or any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in values):
   raise ValueError('Malformed native POLYGON at token '+str(start))
  return values
 at=tuple(numbers(0,2));points=[at];i=2;mode='L'
 while i<len(path):
  if isinstance(path[i],str):
   mode=path[i];i+=1
  if mode=='L':
   at=tuple(numbers(i,2));points.append(at);i+=2
  elif mode=='ARC':
   degrees,ex,ey=numbers(i,3);i+=3;end=(ex,ey)
   theta=math.radians(degrees)
   if not theta:
    points.append(end);at=end;mode='L';continue
   dx,dy=end[0]-at[0],end[1]-at[1];chord=math.hypot(dx,dy)
   if not chord or abs(degrees)>=360:
    raise ValueError('Ambiguous native ARC sweep/endpoints')
   offset=chord/(2*math.tan(theta/2))
   cx=(at[0]+end[0])/2-dy/chord*offset
   cy=(at[1]+end[1])/2+dx/chord*offset
   radius=math.hypot(at[0]-cx,at[1]-cy)
   start=math.atan2(at[1]-cy,at[0]-cx)
   steps=max(2,math.ceil(abs(degrees)/.25))
   for step in range(1,steps):
    angle=start+theta*step/steps
    points.append((cx+radius*math.cos(angle),cy+radius*math.sin(angle)))
   points.append(end);at=end;mode='L'
  else:
   raise ValueError('Unsupported native POLYGON command '+str(mode))
 if len(points)<3:
  raise ValueError('Native POLYGON requires at least three points')
 return Polygon([(px*.0254,py*.0254) for px,py in points]).buffer(0)

def layer_set(layer):
    return ALL if layer == 12 else frozenset({layer})


def disk(x, y, radius):
    return Point(x, y).buffer(radius, quad_segs=64)


def centered_shape(kind, width, height, angle, x, y):
    if kind == "RECT":
        shape = box(-width/2, -height/2, width/2, height/2)
    elif kind in ("OVAL", "ROUND", "SLOT"):
        radius = min(width, height)/2
        if width > height:
            shape = LineString([(-width/2+radius, 0), (width/2-radius, 0)]).buffer(radius, quad_segs=64)
        elif height > width:
            shape = LineString([(0, -height/2+radius), (0, height/2-radius)]).buffer(radius, quad_segs=64)
        else:
            shape = disk(0, 0, radius)
    elif kind == "ELLIPSE":
        shape = scale(disk(0, 0, 1), width/2, height/2)
    else:
        raise ValueError(f"Unsupported pad/hole shape: {kind}")
    return translate(rotate(shape, angle, origin=(0, 0)), x, y)


def polygon(path):
    if not path:
        raise ValueError("Empty native path")
    if isinstance(path[0], list):
        outer = polygon(path[0])
        for hole in path[1:]:
            outer = outer.difference(polygon(hole))
        return outer
    if path[0] == "CIRCLE":
        return disk(path[1]*MM, path[2]*MM, path[3]*MM)
    if path[0] == "R":
        _, x, y, width, height, angle, *rest = path
        # Source R uses upper-left in native +Y-up coordinates. Preserve a
        # conservative square corner for obstacle geometry.
        g = box(x*MM, (y-height)*MM, (x+width)*MM, y*MM)
        return rotate(g, angle, origin=(x*MM, y*MM))
    if isinstance(path[0], str):
        raise ValueError(f"Unsupported native polygon: {path[0]}")
    return native_polygon(path)


def path_line(path):
    """Native straight/arc centerline. Closed polygon helper is not used to
    invent a closing trace for an open path."""
    if path[0] == "CIRCLE":
        return polygon(path).boundary
    if path[0] == "R":
        return polygon(path).boundary
    at = (path[0]*MM, path[1]*MM)
    pts = [at]
    index, mode = 2, "L"
    while index < len(path):
        if isinstance(path[index], str):
            mode = path[index]
            index += 1
        if mode == "L":
            at = (path[index]*MM, path[index+1]*MM)
            pts.append(at)
            index += 2
        elif mode in ("ARC", "CARC"):
            degrees, ex, ey = path[index:index+3]
            end = (ex*MM, ey*MM)
            theta = math.radians(degrees)
            dx, dy = end[0]-at[0], end[1]-at[1]
            chord = math.hypot(dx, dy)
            if not chord or not degrees or abs(degrees) >= 360:
                raise ValueError("Degenerate arc")
            off = chord/(2*math.tan(theta/2))
            cx, cy = (at[0]+end[0])/2-dy/chord*off, (at[1]+end[1])/2+dx/chord*off
            radius, start = math.hypot(at[0]-cx, at[1]-cy), math.atan2(at[1]-cy, at[0]-cx)
            steps = max(2, math.ceil(abs(degrees)/.25))
            pts.extend((cx+radius*math.cos(start+theta*j/steps), cy+radius*math.sin(start+theta*j/steps)) for j in range(1, steps))
            pts.append(end)
            at, index, mode = end, index+3, "L"
        else:
            raise ValueError(f"Unsupported trace command {mode}")
    return LineString(pts)


class Index:
    def __init__(self, items):
        self.items = items
        self.tree = STRtree([i["g"] for i in items]) if items else None

    def near(self, geometry, distance=0):
        if self.tree is None:
            return []
        return [self.items[int(n)] for n in self.tree.query(geometry.buffer(distance) if distance else geometry)]


def load_inputs(args):
    source_bytes = args.source.read_bytes()
    source_docs, _, _ = archive_helper.merge_documents(source_bytes.decode())
    if len(source_docs) != 1:
        raise ValueError("Source must contain one PCB")
    source = next(iter(source_docs.values()))
    state = json.loads(args.state.read_text())
    if isinstance(state, dict):
        state = state.get("components", state.get("result", {}).get("components"))
    if not isinstance(state, list):
        raise ValueError("State must be a native component/pin array")
    with zipfile.ZipFile(args.archive) as z:
        names = [n for n in z.namelist() if n.endswith(".epru")]
        if len(names) != 1:
            raise ValueError("Archive needs exactly one epru")
        libraries, headers, _ = archive_helper.merge_documents(z.read(names[0]).decode())
    bindings = archive_helper.component_index(source)
    components = {ident: b for (kind, ident), b in source.items() if kind == "COMPONENT"}
    if set(components) != {c["id"] for c in state}:
        raise ValueError("Source/state component identity mismatch")
    pad_nets = {}
    for (kind, ident), body in source.items():
        if kind == "PAD_NET":
            fields = json.loads(ident)
            pad_nets[fields[1]+fields[3]] = body["padNet"]
    pads, holes, extra, footprint_evidence = [], [], [], []
    for c in state:
        comp = components[c["id"]]
        if max(abs(comp[axis]-c[axis])*MM for axis in ("x", "y")) > .003 or abs((comp["angle"]-c["rotation"]+180)%360-180) > .001:
            raise ValueError(f"Stale placement state: {c['ref']}")
        if comp["layerId"] != 1:
            raise ValueError(f"Bottom-side footprint transform not yet supported: {c['ref']}; refresh/extend parser rather than guess")
        uid = bindings[c["ref"]]["footprint_uuid"]
        lib = libraries.get(uid)
        if lib is None or {h.get("docType") for h in headers[uid]} != {"FOOTPRINT"}:
            raise ValueError(f"Missing archive footprint for {c['ref']}")
        local_pads = {c["id"]+ident: b for (kind, ident), b in lib.items() if kind == "PAD"}
        footprint_evidence.append({"ref": c["ref"], "uuid": uid})
        for p in c["pins"]:
            if p["id"] not in local_pads:
                raise ValueError(f"State/archive footprint pad mismatch: {p['id']}")
            if p["id"] in pad_nets and pad_nets[p["id"]] != p["net"]:
                raise ValueError(f"Stale state pad net: {c['ref']}.{p['n']}")
            kind, *shape = p["pad"]
            x, y = p["x"]*MM, p["y"]*MM
            if kind == "POLYGON":
                g = native_polygon(shape[0])
            else:
                g = centered_shape(kind, shape[0]*MM, shape[1]*MM, p["rotation"], x, y)
            lp = local_pads[p["id"]]
            angle = math.radians(comp["angle"])
            expected_xy = ((comp["x"]+lp["centerX"]*math.cos(angle)-lp["centerY"]*math.sin(angle))*MM,
                           (comp["y"]+lp["centerX"]*math.sin(angle)+lp["centerY"]*math.cos(angle))*MM)
            if math.dist((x, y), expected_xy) > .003:
                raise ValueError(f"State/archive footprint pad position mismatch: {p['id']}")
            expected_angle = comp["angle"]+lp.get("padAngle", 0)
            if abs((p["rotation"]-expected_angle+180)%360-180) > .001:
                raise ValueError(f"State/archive footprint pad angle mismatch: {p['id']}")
            default_pad = lp.get("defaultPad", {})
            if kind in ("RECT", "OVAL", "ELLIPSE") and default_pad.get("padType") == kind:
                if any(abs(shape[i]-default_pad[key])*MM > .003 for i, key in enumerate(("width", "height"))):
                    raise ValueError(f"State/archive footprint pad size mismatch: {p['id']}")
            plated = bool(lp.get("plated"))
            item = {"id": p["id"], "ref": c["ref"], "pin": p["n"], "g": g,
                    "net": p["net"], "layers": layer_set(p["layer"]), "kind": "pad",
                    "anchor": bool(p.get("hole") and plated and p["layer"] == 12)}
            if not p.get("hole") or plated:
                pads.append(item)
            hole = lp.get("hole")
            if hole and hole.get("width", 0) > 0 and hole.get("height", 0) > 0:
                ox, oy = lp.get("padOffsetX", 0) or 0, lp.get("padOffsetY", 0) or 0
                if ox or oy:
                    raise ValueError(f"Offset hole requires exact transform: {p['id']}")
                hg = centered_shape(hole["holeType"], hole["width"]*MM, hole["height"]*MM,
                                    p["rotation"]+(lp.get("relativeAngle", 0) or 0), x, y)
                holes.append({"id": p["id"]+"_hole", "g": hg, "npth": not plated, "clearance": .30})
        # Non-pad holes and conductive graphics are not present in pin state.
        for (kind, ident), body in lib.items():
            layer = body.get("layerId") if isinstance(body, dict) else None
            if kind not in ("FILL", "REGION", "POLY", "LINE", "ARC", "CARC") or layer not in COPPER | {12}:
                continue
            if kind != "FILL" or layer != 12:
                raise ValueError(f"Unmodeled conductive/keepout footprint primitive {c['ref']} {kind} layer{layer}")
            hg = polygon(body["path"])
            hg = translate(rotate(hg, comp["angle"], origin=(0, 0)), comp["x"]*MM, comp["y"]*MM)
            holes.append({"id": c["id"]+ident, "g": hg, "npth": True,
                          "clearance": .20 if c["ref"] == "U803" else .30})
    return source, state, pads, holes, extra, footprint_evidence


def source_geometry(source, pads, holes):
    items, prohibitions, boundaries, no_pour_credit = list(pads), [], [], []
    pours = {ident: b for (kind, ident), b in source.items() if kind == "POUR"}
    for (kind, ident), b in source.items():
        layer = b.get("layerId") if isinstance(b, dict) else None
        if kind == "PAD":
            hole = b.get("hole")
            if not hole or b.get("plated"):
                raise ValueError("Unexpected board-level conductive pad; add explicit geometry support")
            hg = centered_shape(hole["holeType"], hole["width"]*MM, hole["height"]*MM,
                                b.get("padAngle", 0)+(b.get("relativeAngle", 0) or 0), b["centerX"]*MM, b["centerY"]*MM)
            holes.append({"id": ident, "g": hg, "npth": True, "clearance": .30})
        elif kind == "VIA":
            if b.get("ruleName") or b.get("unusedInnerLayers"):
                raise ValueError(f"Nonstandard via layers require explicit handling: {ident}")
            g = disk(b["centerX"]*MM, b["centerY"]*MM, b["viaDiameter"]*MM/2)
            items.append({"id": ident, "g": g, "net": b["netName"], "layers": ALL, "kind": "via", "anchor": True,
                          "xy": (b["centerX"]*MM, b["centerY"]*MM)})
            holes.append({"id": ident+"_hole", "g": disk(b["centerX"]*MM, b["centerY"]*MM, b["holeDiameter"]*MM/2), "npth": False})
        elif kind == "REGION" and b.get("regionType") == "PROHIBIT":
            prohibitions.append({"id": ident, "g": polygon(b["path"]), "layers": layer_set(layer)})
        elif kind == "POLY" and layer == 11:
            boundaries.append(polygon(b["path"]))
        elif kind in ("LINE", "ARC", "CARC", "POLY", "FILL", "TEARDROP", "POUR", "POURED"):
            if kind == "POURED":
                if "pourFill" in b:
                    key = json.loads(ident)
                    parent = pours.get(key[1]) if len(key) == 2 and key[0] == "POURED" else None
                    if not parent:
                        raise ValueError("Runtime POURED without identifiable parent")
                    # This client stores pourFill paths in a different internal
                    # scale from board primitives. Do not guess that scale or
                    # grant electrical connectivity from an unparsed cache.
                    # Foreign parent POUR outlines are already conservative
                    # obstacles; GND caches are deliberately not credited.
                    no_pour_credit.append("UNPARSED_RUNTIME_POURED:"+ident)
                    continue
                parent = pours.get(b["targetId"])
                if not parent:
                    raise ValueError("POURED without parent")
                layer, net = parent["layerId"], parent["netName"]
            else:
                net = b.get("netName", "")
            if layer not in COPPER | {12}:
                continue
            if layer == 12:
                raise ValueError(f"Board slot graphic needs explicit handling: {kind} {ident}")
            if kind == "LINE":
                g = LineString([(b["startX"]*MM, b["startY"]*MM), (b["endX"]*MM, b["endY"]*MM)]).buffer(b["width"]*MM/2, quad_segs=32)
            elif kind in ("ARC", "CARC"):
                g = path_line([b["startX"], b["startY"], "ARC", b["angle"], b["endX"], b["endY"]]).buffer(b["width"]*MM/2, quad_segs=32)
            elif kind == "POLY":
                g = path_line(b["path"]).buffer(b["width"]*MM/2, quad_segs=32)
            else:
                g = polygon(b["path"]).buffer((b.get("width", b.get("strokeWidth", 0)) or 0)*MM/2)
            if kind == "POUR":
                # Never credit a zone boundary as connected copper. A foreign
                # zone conservatively occupies its whole outline until refilled.
                no_pour_credit.append(ident)
                if net == "GND":
                    continue
            items.append({"id": ident, "g": g, "net": net, "layers": layer_set(layer), "kind": kind.lower(), "anchor": False})
        elif kind in ("TEXT", "IMAGE", "PICTURE") and layer in COPPER:
            raise ValueError(f"Unmodeled copper text/image: {ident}")
    if len(boundaries) != 1:
        raise ValueError(f"Need one closed board outline POLY, found {len(boundaries)}")
    if len(prohibitions) < 24:
        raise ValueError(f"Expected at least24 native keepouts, found {len(prohibitions)}")
    return items, holes, prohibitions, boundaries[0], no_pour_credit


#!/usr/bin/env python3
"""Read-only native LINE/pad/via path geometry and trace-only resistance.

Never reads ignored build files. No live API. Actual FILL/POURED is deliberately
not credited; final CAM remains necessary. Via barrels and pad spreading cost
zero, so R20 is a trace-only lower bound rather than a power/thermal approval.
"""
import collections,heapq,hashlib
from shapely.geometry import LineString,Point
from shapely.ops import unary_union,nearest_points
import native_source_geometry as geo
from native_exact_smd import exact_smd_pads
MM=.0254

def digest(path):
    return {"path":str(path),"sha256":hashlib.sha256(path.read_bytes()).hexdigest()}

def load_scene(args):
    source,state,pads,holes,extra,evidence=geo.load_inputs(args)
    exact={p['id']:p for p in exact_smd_pads(source,state,args.archive)}
    pads=[exact.get(p['id'],p)for p in pads]
    items,holes,regions,board,unparsed=geo.source_geometry(source,pads,holes)
    lines=[segment((b['startX']*MM,b['startY']*MM),(b['endX']*MM,b['endY']*MM),b['width']*MM,i,b['netName'],b['layerId'])for(k,i),b in source.items()if k=='LINE'and b.get('layerId')in geo.COPPER]
    return source,state,pads,items,lines,unparsed,evidence

def segment(a, b, width, ident, net, layer):
    return {"id": ident, "net": net, "layer": layer, "a": tuple(a), "b": tuple(b),
            "width": width, "center": LineString([a, b])}

def copper(s):
    return s["center"].buffer(s["width"]/2, quad_segs=48)

def geometry_points(g):
    if g.is_empty:
        return []
    if g.geom_type == "Point":
        return [g]
    if g.geom_type in ("LineString", "LinearRing"):
        return [Point(g.coords[0]), Point(g.coords[-1])]
    if hasattr(g, "geoms"):
        return [p for child in g.geoms for p in geometry_points(child)]
    return []

def trace_path_audit(segments, pads, items, rules, thickness, width_tolerance=.00025, optimization_metric="trace_R20_mohm"):
    """LINE centerline graph with physical pad/via contact nodes. Pads and via
    barrels have zero graph cost, explicitly making R20 a TRACE-ONLY lower bound.
    Verified overlapping LINE capsules / contacts also join the graph; the
    center-to-center bridge is charged at the narrower width. Non-LINE
    FILL/POURED is never silently credited as a complete path. The default chooses
    minimum trace R20; explicit length_mm chooses minimum exposed trace length
    for signal measurements without changing the power-check default."""
    if optimization_metric not in {"trace_R20_mohm", "length_mm"}:
        raise ValueError("Unsupported path optimization metric")
    output = []
    by_net = collections.defaultdict(list)
    for s in segments:
        by_net[s["net"]].append(s)
    for rule in rules:
        net = rule["native_net"]
        lines = by_net[net]
        contacts = [p for p in pads if p["net"] == net]
        contacts += [p for p in items if p["net"] == net and p["kind"] == "via"]
        from_ids = {p["id"] for p in rule["native_from"]["physical_pads"]}
        to_ids = {p["id"] for p in rule["native_to"]["physical_pads"]}
        if not from_ids <= {p["id"] for p in contacts} or not to_ids <= {p["id"] for p in contacts}:
            raise ValueError(f"Power path {rule['id']} terminal pad IDs are stale")
        offsets = [{0.0, s["center"].length} for s in lines]
        attachments = collections.defaultdict(list)
        overlap_bridges = []
        contact_pairs = []
        for i,c in enumerate(contacts):
            for t in contacts[:i]:
                if c["layers"] & t["layers"] and c["g"].intersects(t["g"]):
                    contact_pairs.append((c,t))
        for i, s in enumerate(lines):
            for c in contacts:
                if s["layer"] not in c["layers"]:
                    continue
                intersection = s["center"].intersection(c["g"])
                if intersection.is_empty and copper(s).intersects(c["g"]):
                    p,q = nearest_points(s["center"],c["g"])
                    distance = s["center"].project(p)
                    offsets[i].add(distance)
                    attachments[i].append((distance,c["id"],c["kind"],p.distance(q)))
                    overlap_bridges.append({"type":"line_contact_edge","line_id":s["id"],"contact_id":c["id"],"center_to_contact_mm":p.distance(q)})
                for p in geometry_points(intersection):
                    distance = s["center"].project(p)
                    offsets[i].add(distance)
                    attachments[i].append((distance,c["id"],c["kind"]))
            for j in range(i):
                t = lines[j]
                if s["layer"] != t["layer"]:
                    continue
                crossing=s["center"].intersection(t["center"])
                if crossing.is_empty and copper(s).intersects(copper(t)):
                    a,b=nearest_points(s["center"],t["center"])
                    da,db=s["center"].project(a),t["center"].project(b)
                    offsets[i].add(da);offsets[j].add(db)
                    overlap_bridges.append({"type":"line_line_edge","i":i,"j":j,"da":da,"db":db,"line_ids":[s["id"],t["id"]],"center_gap_mm":a.distance(b)})
                for p in geometry_points(crossing):
                    offsets[i].add(s["center"].project(p))
                    offsets[j].add(t["center"].project(p))
        graph = collections.defaultdict(list)
        node_data = {}
        def point_key(s,d):
            p=s["center"].interpolate(d)
            return (s["layer"],round(p.x,7),round(p.y,7))
        def add(a,b,data):
            graph[a].append((b,data));graph[b].append((a,data))
        pad_union = {layer:unary_union([p["g"] for p in pads if p["net"]==net and layer in p["layers"]]) for layer in [1,2,15,16]}
        for i,s in enumerate(lines):
            distances = sorted(offsets[i])
            for da,db in zip(distances,distances[1:]):
                if db-da < 1e-8:continue
                pa,pb=s["center"].interpolate(da),s["center"].interpolate(db)
                exposed = LineString([(pa.x,pa.y),(pb.x,pb.y)]).difference(pad_union[s["layer"]]).length
                # rho=0.01724 ohm mm²/m; with t in um: R_mOhm=17.24*L/(w*t)
                resistance = 17.24*exposed/(s["width"]*thickness)
                narrow = exposed if s["width"]+width_tolerance < rule["trunk_min_mm"] else 0
                data={"id":s["id"],"length_mm":exposed,"narrow_mm":narrow,
                      "trace_R20_mohm":resistance,"width_mm":s["width"],"via":False}
                add(point_key(s,da),point_key(s,db),data)
            for attachment in attachments[i]:
                d,ident,kind,*gap_value=attachment;gap=gap_value[0] if gap_value else 0
                add(point_key(s,d),("contact",ident),{"length_mm":gap,"narrow_mm":gap if s["width"]+width_tolerance<rule["trunk_min_mm"] else 0,"trace_R20_mohm":17.24*gap/(s["width"]*thickness),"width_mm":s["width"],"via":kind=="via","id":ident})
        for c,t in contact_pairs:
            add(("contact",c["id"]),("contact",t["id"]),{"length_mm":0,"narrow_mm":0,"trace_R20_mohm":0,"via":False,"id":"overlap:"+c["id"]+":"+t["id"]})
        for bridge in overlap_bridges:
            if bridge["type"]!="line_line_edge":continue
            s,t=lines[bridge["i"]],lines[bridge["j"]]
            length=bridge["center_gap_mm"];width=min(s["width"],t["width"])
            add(point_key(s,bridge["da"]),point_key(t,bridge["db"]),{"length_mm":length,"narrow_mm":length if width+width_tolerance<rule["trunk_min_mm"] else 0,"trace_R20_mohm":17.24*length/(width*thickness),"width_mm":width,"via":False,"id":"edge-overlap:"+s["id"]+":"+t["id"]})
        start=("terminal","from");end=("terminal","to")
        for ident in from_ids:add(start,("contact",ident),{"length_mm":0,"narrow_mm":0,"trace_R20_mohm":0,"via":False,"id":ident})
        for ident in to_ids:add(end,("contact",ident),{"length_mm":0,"narrow_mm":0,"trace_R20_mohm":0,"via":False,"id":ident})
        distances={start:0.0};previous={};queue=[(0.0,0,start)];serial=0
        while queue:
            cost,_,node=heapq.heappop(queue)
            if cost != distances.get(node):continue
            if node==end:break
            for adjacent,data in graph[node]:
                new=cost+data[optimization_metric]
                if new+1e-12 < distances.get(adjacent,float("inf")):
                    distances[adjacent]=new;previous[adjacent]=(node,data);serial+=1
                    heapq.heappush(queue,(new,serial,adjacent))
        row={"path_id":rule["id"],"net":net,"from":rule["from"],"to":rule["to"],
             "trunk_min_mm":rule["trunk_min_mm"],"neck_budget_mm":rule["narrow_allowance_mm"],
             "trace_R20_review_limit_mohm":rule["review_R20_mohm"]}
        if end not in distances:
            row.update(status="NO_COMPLETE_LINE_CENTERLINE_PATH",neck_budget_pass=None,
                       note="Unrouted, centerline contact tolerance, or non-LINE copper path; no connection or power PASS inferred")
        else:
            edges=[];node=end
            while node!=start:
                parent,data=previous[node];edges.append(data);node=parent
            narrow=sum(e["narrow_mm"] for e in edges);length=sum(e["length_mm"] for e in edges)
            via_ids=sorted({e["id"] for e in edges if e["via"]})
            row.update(status="TRACE_ONLY_PATH_MEASURED",neck_budget_pass=narrow<=rule["narrow_allowance_mm"]+1e-5,
                       cumulative_neck_mm=narrow,exposed_trace_length_mm=length,trace_R20_lower_bound_mohm=distances[end] if optimization_metric=="trace_R20_mohm" else sum(e["trace_R20_mohm"] for e in edges),
                       trace_R20_lower_bound_within_limit=(distances[end] if optimization_metric=="trace_R20_mohm" else sum(e["trace_R20_mohm"] for e in edges))<=rule["review_R20_mohm"],
                       selected_path_source_ids=list(dict.fromkeys(e["id"] for e in reversed(edges))),via_ids=via_ids,
                       selected_path_width_min_mm=min((e["width_mm"] for e in edges if e.get("length_mm",0)>1e-7 and "width_mm"in e),default=None),
                       selected_path_width_max_mm=max((e["width_mm"] for e in edges if e.get("length_mm",0)>1e-7 and "width_mm"in e),default=None),
                       exposed_length_by_width_mm={str(round(w,6)):sum(e["length_mm"] for e in edges if e.get("width_mm")==w) for w in sorted({e["width_mm"]for e in edges if "width_mm"in e})},
                       via_and_pad_resistance_unmodeled=True,
                       power_qualification="NOT_PROVEN_BY_GEOMETRIC_OR_TRACE_ONLY_RESULT")
        row["copper_overlap_contacts"]=[{k:v for k,v in b.items() if k not in {"i","j","da","db"}} for b in overlap_bridges]
        row["direct_contact_overlaps"]=[{"a":c["id"],"b":t["id"]} for c,t in contact_pairs]
        output.append(row)
    return output

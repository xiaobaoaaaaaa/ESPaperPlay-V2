#!/usr/bin/env python3
"""Add documentation-only thermal-hole reservations; never save a board.

Public entry points: add_reservations(board, output_json_path) -> report dict,
check_reservations(board, output_json_path) -> report dict (strictly read-only).
Requires KiCad pcbnew and Shapely. All distances are mm. A PASS is a placement
geometry result, not thermal, soldering, routing, or manufacturing approval.
"""
from __future__ import annotations
import json
import hashlib
import math
from pathlib import Path
import pcbnew as P
from shapely.geometry import GeometryCollection, LineString, Point, Polygon
from shapely.ops import unary_union

GROUP_NAME = 'THERMAL_RESERVATIONS_LAYOUT_ONLY'
DRILL = .30
LAND = .60
COPPER_CLEARANCE = .15
HOLE_CLEARANCE = .15
HOLE_TO_HOLE = .25
EXTERNAL_HOLE_TO_MASK = .20
POLY_ERROR = .00001
EPS = .00002
SPECS = {
 'U101': {'kind': 'filled_capped_in_pad_exception', 'vias': [(-.4,-.4),(-.4,.4),(.4,-.4),(.4,.4)], 'routes': [],
          'note': '盘内填平盖帽工艺例外；0.701A充电热路径保留；不是普通盖油替代。'},
 'U201': {'kind': 'external_ground_vias', 'vias': [(1.7,0),(2.5,0)],
          'routes': [{'points': [(.55,0),(2.5,0)], 'width': .25}],
          'note': 'pad8向右接地孔；近端电容回流和开关回路仍需布线复核。'},
 'U203': {'kind': 'external_ground_vias', 'vias': [(0,-1.3),(0,1.3)],
          'routes': [{'points': [(0,-1.3),(0,1.3)], 'width': .60}],
          'note': 'EP上下外移孔；保留原EP与印膏。'},
 'U802': {'kind': 'external_ground_vias_thermal_validation_pending', 'vias': [(-2.3,.25),(2.3,-.25),(-.25,-2.3),(2.4,-1.05)],
          'routes': [{'points': [(0,.25),(-2.3,.25)], 'width': .30},
                     {'points': [(0,-.25),(2.3,-.25)], 'width': .30},
                     {'points': [(-.25,0),(-.25,-2.3)], 'width': .30},
                     {'points': [(2.3,-.25),(2.4,-.25),(2.4,-1.05)], 'width': .60}],
          'note': '通过GND3/11/15的外围地孔候选；与盘内孔热性能不等效，首板热测待完成。'}
}


def _xy(v):
    return [round(P.ToMM(v.x),6), round(P.ToMM(v.y),6)]


def _vector(v):
    return P.VECTOR2I(P.FromMM(v[0]), P.FromMM(v[1]))


def _polyset(ps):
    polys=[]
    for i in range(ps.OutlineCount()):
        q=ps.COutline(i)
        points=[_xy(q.CPoint(j)) for j in range(q.PointCount())]
        holes=[]
        for h in range(ps.HoleCount(i)):
            qh=ps.CHole(i,h)
            holes.append([_xy(qh.CPoint(j)) for j in range(qh.PointCount())])
        if len(points)>=3:
            polys.append(Polygon(points,holes))
    return unary_union(polys) if polys else GeometryCollection()


def _pad_copper(p, layer):
    ps=P.SHAPE_POLY_SET()
    p.TransformShapeToPolygon(ps,layer,0,P.FromMM(POLY_ERROR),P.ERROR_OUTSIDE)
    return _polyset(ps)


def _pad_hole(p):
    ps=P.SHAPE_POLY_SET()
    p.TransformHoleToPolygon(ps,0,P.FromMM(POLY_ERROR),P.ERROR_OUTSIDE)
    return _polyset(ps)


def local_to_absolute(fp, local):
    """Apply KiCad local-to-board rotation: x'=c*x+s*y, y'=-s*x+c*y."""
    angle=math.radians(fp.GetOrientationDegrees())
    c,s=math.cos(angle),math.sin(angle)
    x,y=local
    origin=_xy(fp.GetPosition())
    return [round(origin[0]+c*x+s*y,6), round(origin[1]-s*x+c*y,6)]


def _nearest(shape, obstacles):
    best=None
    for item in obstacles:
        gap=shape.distance(item['geometry'])
        if best is None or gap<best['clearance_mm']:
            best={'clearance_mm':gap, **{k:v for k,v in item.items() if k!='geometry'}}
    if best is not None:
        best['clearance_mm']=round(best['clearance_mm'],6)
    return best


def _electrical_signature(board):
    pads=sorted((f.GetReference(), p.m_Uuid.AsString(), p.GetNumber(),p.GetNetCode(),tuple(_xy(p.GetPosition())),tuple(_xy(p.GetDrillSize()))) for f in board.GetFootprints() for p in f.Pads())
    return {'tracks':len(board.GetTracks()),'zones':len(board.Zones()),'pads':pads}


def _add_circle(board,group,center,diameter):
    shape=P.PCB_SHAPE()
    shape.SetShape(P.SHAPE_T_CIRCLE)
    shape.SetStart(_vector(center))
    shape.SetEnd(_vector((center[0]+diameter/2,center[1])))
    shape.SetLayer(P.Dwgs_User)
    shape.SetWidth(P.FromMM(.025))
    shape.SetFilled(False)
    shape.SetLocked(True)
    board.Add(shape)
    group.AddItem(shape)


def _evaluate_reservations(board, output_json_path, create_if_missing):
    """Evaluate first; only a missing documentation group may be added.

    Never remove loaded group members. KiCad 10 SWIG BOARD.Remove on generic
    loaded group item proxies corrupted subsequent proxy access in reproduction.
    Reuse an existing group and report stale/incorrect circles as explicit FAIL.
    """
    before=_electrical_signature(board)
    fps={f.GetReference():f for f in board.GetFootprints()}
    errors=[]
    for ref in SPECS:
        if ref not in fps:
            raise ValueError('Missing thermal reservation footprint: '+ref)
        if fps[ref].GetLayer()!=P.F_Cu:
            raise ValueError('Thermal reservation transformation expects front-side footprint: '+ref)
        # Check transformation against actual library-pad placement, not assumed angle.
        for p in fps[ref].Pads():
            transformed=local_to_absolute(fps[ref],_xy(p.GetFPRelativePosition()))
            if math.dist(transformed,_xy(p.GetPosition()))>.000003:
                raise ValueError(f'Local coordinate transform mismatch: {ref}.{p.GetNumber()}')

    layers=list(board.GetEnabledLayers().CuStack())
    all_copper=[]
    front_copper=[]
    holes=[]
    npth=[]
    mask_openings=[]
    for fp in board.GetFootprints():
        for p in fp.Pads():
            ident={'ref':fp.GetReference(),'pad':p.GetNumber(),'net':p.GetNetname(),'position_mm':_xy(p.GetPosition())}
            if p.HasDrilledHole():
                item={'geometry':_pad_hole(p),**ident,'plated':p.GetAttribute()!=P.PAD_ATTRIB_NPTH}
                holes.append(item)
                if not item['plated']:
                    npth.append(item)
            if p.GetAttribute()!=P.PAD_ATTRIB_NPTH:
                shapes=[_pad_copper(p,l) for l in layers if p.IsOnLayer(l)]
                geometry=unary_union(shapes) if shapes else GeometryCollection()
                if not geometry.is_empty:
                    all_copper.append({'geometry':geometry,**ident})
                if p.IsOnLayer(P.F_Cu):
                    front_copper.append({'geometry':_pad_copper(p,P.F_Cu),**ident})
            if p.IsOnLayer(P.F_Mask) and p.IsOnLayer(P.F_Cu):
                geometry=_pad_copper(p,P.F_Cu).buffer(P.ToMM(p.GetSolderMaskExpansion(P.F_Mask)))
                if not geometry.is_empty:
                    mask_openings.append({'geometry':geometry,**ident})
    alien_copper=[p for p in all_copper if p['net']!='GND']
    alien_front=[p for p in front_copper if p['net']!='GND']

    existing_groups=[g for g in board.Groups() if g.GetName()==GROUP_NAME]
    if len(existing_groups)>1:
        errors.append({'kind':'duplicate_thermal_documentation_group','count':len(existing_groups)})

    def check_nearest(kind, record, nearest, limit):
        record[kind]={'required_mm':limit,'nearest':nearest,'pass':nearest is None or nearest['clearance_mm']+EPS>=limit}
        if not record[kind]['pass']:
            errors.append({'kind':kind,'reservation':record['id'],'required_mm':limit,'nearest':nearest})

    report={
      'status':'PENDING',
      'scope':'Dwgs.User documentation-only placement reservations; no physical vias/tracks added; no thermal, soldering, route, CAM, or coupon-cost sign-off',
      'board':board.GetFileName(),
      'mode':'add_missing_or_validate_existing' if create_if_missing else 'read_only_check',
      'geometry_method':'Actual KiCad pad polygons and drill polygons, conservative outside approximation <=0.00001 mm; Shapely distance checks; all-copper-layer pad union for through-via candidates, front copper for neck candidates; all physical pads/NPTH included',
      'thresholds_mm':{'copper_clearance':COPPER_CLEARANCE,'copper_to_npth':HOLE_CLEARANCE,'hole_to_hole':HOLE_TO_HOLE,'external_drill_edge_to_mask':EXTERNAL_HOLE_TO_MASK,'comparison_tolerance':EPS},
      'reserved_hole_diameter_mm':DRILL,'reserved_land_diameter_mm':LAND,
      'documentation_layer':'Dwgs.User','group':GROUP_NAME,'footprints':{},'reservations':[],'necks':[],'candidate_pair_checks':[],
      'actual_module_holes':[],
      'limitations':['No new copper neck or drill has been manufactured or routed by this function.','Candidate necks are hypothetical copper envelopes used only for obstacle checks.','Filled/capped U101 exception remains explicit; no claim of ordinary tenting equivalence.','U802 external thermal path awaits actual thermal verification.','Pad/mask geometry checks do not prove assembly voiding, enclosure clearance, or factory process acceptance.']}
    candidate_holes=[]
    for ref,spec in SPECS.items():
        fp=fps[ref]
        report['footprints'][ref]={'position_mm':_xy(fp.GetPosition()),'rotation_deg':fp.GetOrientationDegrees(),'process_kind':spec['kind'],'note':spec['note']}
        for index,local in enumerate(spec['vias'],1):
            absolute=local_to_absolute(fp,local)
            rec={'id':f'{ref}-TH{index}','ref':ref,'local_mm':list(local),'absolute_mm':absolute,'net_intent':'GND','process_kind':spec['kind']}
            land=Point(absolute).buffer(LAND/2,quad_segs=256)
            hole=Point(absolute).buffer(DRILL/2,quad_segs=256)
            check_nearest('land_to_other_net_pad',rec,_nearest(land,alien_copper),COPPER_CLEARANCE)
            check_nearest('land_to_npth',rec,_nearest(land,npth),HOLE_CLEARANCE)
            check_nearest('drill_to_existing_drill',rec,_nearest(hole,holes),HOLE_TO_HOLE)
            if spec['kind']!='filled_capped_in_pad_exception':
                check_nearest('drill_to_soldermask_opening',rec,_nearest(hole,mask_openings),EXTERNAL_HOLE_TO_MASK)
            else:
                rec['drill_to_soldermask_opening']={'pass':None,'exception':'Intentionally in EP solder opening; requires filled/planarized/copper-capped process, not ordinary tenting.'}
            rec['pass']=all(v['pass'] for v in rec.values() if isinstance(v,dict) and isinstance(v.get('pass'),bool))
            report['reservations'].append(rec)
            candidate_holes.append({'geometry':hole,'id':rec['id']})
        for index,route in enumerate(spec['routes'],1):
            points=[local_to_absolute(fp,p) for p in route['points']]
            rec={'id':f'{ref}-NECK{index}','ref':ref,'local_points_mm':route['points'],'absolute_points_mm':points,'width_mm':route['width'],'physical_copper_created':False}
            shape=LineString(points).buffer(route['width']/2,quad_segs=256)
            check_nearest('neck_to_other_net_pad',rec,_nearest(shape,alien_front),COPPER_CLEARANCE)
            check_nearest('neck_to_npth',rec,_nearest(shape,npth),HOLE_CLEARANCE)
            rec['pass']=all(v['pass'] for v in rec.values() if isinstance(v,dict) and isinstance(v.get('pass'),bool))
            report['necks'].append(rec)
    for i,first in enumerate(candidate_holes):
        for other in candidate_holes[i+1:]:
            distance=first['geometry'].distance(other['geometry'])
            if distance<1.0:
                item={'a':first['id'],'b':other['id'],'drill_edge_gap_mm':round(distance,6),'required_mm':HOLE_TO_HOLE,'pass':distance+EPS>=HOLE_TO_HOLE}
                report['candidate_pair_checks'].append(item)
                if not item['pass']:
                    errors.append({'kind':'candidate_drill_to_drill',**item})
    if 'U301' in fps:
        for p in fps['U301'].Pads():
            if p.GetNumber()=='41' and p.HasDrilledHole():
                report['actual_module_holes'].append({'absolute_mm':_xy(p.GetPosition()),'local_mm':_xy(p.GetFPRelativePosition()),'drill_mm':_xy(p.GetDrillSize()),'pad_mm':_xy(p.GetSize()),'net':p.GetNetname(),'actual_physical_hole':True,'additional_documentation_circle_created':False})
    module_ok=len(report['actual_module_holes'])==12 and all(h['drill_mm']==[.3,.3] and h['pad_mm']==[.6,.6] and h['net']=='GND' for h in report['actual_module_holes'])
    if not module_ok:
        errors.append({'kind':'U301_module_holes_not_12_ground_0p30_0p60','actual_count':len(report['actual_module_holes'])})
    created=False
    if not existing_groups and create_if_missing:
        group=P.PCB_GROUP(board)
        group.SetName(GROUP_NAME)
        group.SetLocked(True)
        board.Add(group)
        for rec in report['reservations']:
            _add_circle(board,group,rec['absolute_mm'],LAND)
            _add_circle(board,group,rec['absolute_mm'],DRILL)
        existing_groups=[group]
        created=True
    expected=sorted((tuple(rec['absolute_mm']),diameter) for rec in report['reservations'] for diameter in [LAND,DRILL])
    actual=[]
    members=[]
    for group in existing_groups:
        for item in group.GetItems():
            member={'uuid':item.m_Uuid.AsString(),'class':item.GetClass(),'layer':item.GetLayerName()}
            # Loaded group members are generic BOARD_ITEM proxies. Cast only for
            # read access; leave their ownership and parent membership untouched.
            if item.GetClass()=='PCB_SHAPE':
                shape=P.Cast_to_PCB_SHAPE(item)
                if shape.GetShape()==P.SHAPE_T_CIRCLE and shape.GetLayer()==P.Dwgs_User:
                    center=tuple(_xy(shape.GetStart()))
                    diameter=round(2*math.dist(center,_xy(shape.GetEnd())),6)
                    actual.append((center,diameter))
                    member.update(center_mm=list(center),diameter_mm=diameter,width_mm=P.ToMM(shape.GetWidth()))
                else:
                    errors.append({'kind':'thermal_documentation_non_circle_or_wrong_layer',**member})
            else:
                errors.append({'kind':'thermal_documentation_non_shape',**member})
            members.append(member)
    # KiCad stores nm integers; a floating point FromMM conversion can round an
    # endpoint down by 1 nm (2 nm in a derived diameter). This is documentation
    # coordinate tolerance, not a relaxed electrical-clearance rule.
    sorted_actual=sorted(actual)
    doc_tolerance=.000005
    doc_match=len(sorted_actual)==len(expected) and all(
        math.dist(a[0],e[0])<=doc_tolerance and abs(a[1]-e[1])<=doc_tolerance
        for a,e in zip(sorted_actual,expected))
    if not doc_match:
        errors.append({'kind':'thermal_documentation_geometry_mismatch','expected':expected,'actual':sorted(actual),'remedy':'Regenerate documentation from a clean base; this checker never deletes loaded groups.'})
    report['documentation_created']=created
    report['documentation_verified_existing']=bool(existing_groups) and not created
    report['documentation_members']=sorted(members,key=lambda v:v['uuid'])
    report['documentation_coordinate_tolerance_mm']=doc_tolerance
    report['documentation_circle_count']=len(actual)
    report['expected_documentation_circle_count']=len(expected)
    after=_electrical_signature(board)
    if before!=after:
        raise AssertionError('Documentation reservation unexpectedly changed electrical items')
    report['electrical_items_unchanged']=True
    report['tracks_and_vias_before']=before['tracks']
    report['tracks_and_vias_after']=after['tracks']
    board_file=Path(board.GetFileName())
    report['board_sha256']=hashlib.sha256(board_file.read_bytes()).hexdigest() if board_file.is_file() else None
    report['board_hash_scope']='Bytes of the saved board file; add mode may add documentation only to the passed in-memory board.'
    report['errors']=errors
    report['status']='FAIL' if errors else 'PASS_RESERVATION_GEOMETRY_ONLY'
    output=Path(output_json_path)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    return report


def add_reservations(board, output_json_path):
    """Add missing Dwgs.User circles, or validate/reuse the existing group.

    Idempotent for both freshly generated and saved/reloaded boards. Never
    deletes a group or saves CAD. Stale existing geometry returns FAIL.
    """
    return _evaluate_reservations(board, output_json_path, create_if_missing=True)


def check_reservations(board, output_json_path):
    """Read-only validation of existing circles and candidate clearance geometry.

    Writes the JSON report, including saved PCB SHA-256. No board mutation.
    """
    return _evaluate_reservations(board, output_json_path, create_if_missing=False)

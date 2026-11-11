#!/usr/bin/python3
"""Read-only mechanical/assembly audit of frozen r8; no Board.Save or mutations."""
from pathlib import Path
import sys, json, hashlib, re, itertools, argparse
ROOT=Path(__file__).resolve().parents[3]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output-directory',type=Path,default=Path(__file__).resolve().parent)
parser.add_argument('--python-deps',type=Path,default=ROOT/'build/dfm-r9/stencil/python',help='Existing local Shapely directory; pcbnew remains the system module')
args=parser.parse_args()
if args.python_deps.is_dir(): sys.path.insert(0,str(args.python_deps))
import pcbnew as P
from shapely.geometry import Polygon, Point, LineString, box
from shapely.ops import unary_union
OUT=args.output_directory.resolve()
OUT.mkdir(parents=True,exist_ok=True)
SRC=ROOT/'hardware/devboard-r0/ESPaperPlay_Devboard.kicad_pcb'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def mm(v): return round(P.ToMM(v),6)
def xy(v): return [mm(v.x),mm(v.y)]
def rnd(v): return round(float(v),6)
def natural(s): return tuple(int(x) if x.isdigit() else x for x in re.split(r'(\d+)',s))
def poly(ps):
    shapes=[]
    for i in range(ps.OutlineCount()):
        a=ps.COutline(i)
        coords=[xy(a.CPoint(j)) for j in range(a.PointCount())]
        holes=[]
        for k in range(ps.HoleCount(i)):
            h=ps.CHole(i,k);holes.append([xy(h.CPoint(j)) for j in range(h.PointCount())])
        if len(coords)>=3: shapes.append(Polygon(coords,holes))
    return unary_union(shapes)
def padshape(p,l=P.F_Cu):
    ps=P.SHAPE_POLY_SET();p.TransformShapeToPolygon(ps,l,0,P.FromMM(.001),P.ERROR_OUTSIDE)
    return poly(ps)
before=sha(SRC)
if before!='1a4556d866cc1352a2c45b674c94d2f233edf28c3e003bd96c8f6caf1e630681': raise ValueError('Formal source PCB no longer matches frozen r8; review must be updated explicitly')
b=P.LoadBoard(str(SRC));fps={f.GetReference():f for f in b.GetFootprints()}
outline=P.SHAPE_POLY_SET();outline_valid=b.GetBoardPolygonOutlines(outline,False);board=poly(outline)
layer_ids=list(b.GetEnabledLayers().CuStack())
courts={}
for ref,f in fps.items():
    f.BuildCourtyardCaches();courts[ref]=poly(f.GetCourtyard(P.F_CrtYd))
overlaps=[];minimum=None
for a,c in itertools.combinations(sorted(fps,key=natural),2):
    x,y=courts[a],courts[c]
    if x.is_empty or y.is_empty: continue
    area=x.intersection(y).area;distance=x.distance(y)
    if area>1e-6: overlaps.append({'refs':[a,c],'area_mm2':rnd(area)})
    if minimum is None or distance<minimum['distance_mm']: minimum={'refs':[a,c],'distance_mm':rnd(distance)}
outside=[];edge_distances=[]
for ref,c in courts.items():
    if c.is_empty: continue
    area=c.difference(board).area
    if area>1e-6: outside.append({'ref':ref,'outside_area_mm2':rnd(area),'bbox_mm':list(c.bounds)})
    else: edge_distances.append({'ref':ref,'distance_mm':rnd(c.distance(board.boundary))})
mounts=[]
for ref in ['H1','H2','H3','H4']:
    f=fps[ref];p=list(f.Pads())[0];center=Point(xy(p.GetPosition()));r=mm(p.GetDrillSizeX())/2
    nearest=min(((center.distance(c),rr) for rr,c in courts.items() if rr!=ref and not c.is_empty))
    mounts.append({'ref':ref,'xy_mm':xy(p.GetPosition()),'drill_mm':xy(p.GetDrillSize()),'npth':p.GetAttribute()==P.PAD_ATTRIB_NPTH,'hole_edge_to_board_edge_mm':rnd(center.distance(board.boundary)-r),'courtyard_bbox_mm':list(courts[ref].bounds),'nearest_other_courtyard_ref':nearest[1],'center_to_nearest_other_courtyard_mm':rnd(nearest[0]),'excluded_bom':f.IsExcludedFromBOM(),'excluded_position':f.IsExcludedFromPosFiles()})
directions={'J501':'north / -Y','J701':'east / +X','J601':'south / +Y','J406':'east / +X','J102':'south / +Y','J103':'south / +Y','J801':'north / -Y'}
connectors={}
for ref,direction in directions.items():
    f=fps[ref]
    connectors[ref]={'value':f.GetValue(),'mpn':f.GetFieldsText().get('Candidate_MPN'),'footprint':f.GetFPIDAsString(),'xy_mm':xy(f.GetPosition()),'native_rotation_deg':f.GetOrientationDegrees(),'entry_direction':direction,'courtyard_bbox_mm':list(courts[ref].bounds),'pads':[{'number':p.GetNumber(),'xy_mm':xy(p.GetPosition()),'net':p.GetNetname(),'drill_mm':xy(p.GetDrillSize())} for p in f.Pads() if p.GetNumber()]}
# Full path from mouth to the planned external workspace; tested against all other footprint courtyards.
# These are board-specific workspaces, not a claim that every USB cable moulding/hand fits them.
corridor_defs={
 'J501':(100,34,116,49.325),
 'J701':(208.925,63.575,220,77.425),
 'J601':(182.75,157.08,199.25,169),
 'J406':(207.65,102,220,108),
 'J102':(63,155.1,70.5,165),
 'J103':(76,155.1,83.5,165),
 'J801':(85.5,45,93,51.4),
}
corridors={}
for ref,coords in corridor_defs.items():
    c=box(*coords);hits=[]
    for other,s in courts.items():
        if other!=ref and c.intersection(s).area>1e-6: hits.append({'ref':other,'area_mm2':rnd(c.intersection(s).area)})
    corridors[ref]={'bbox_mm':coords,'other_footprint_obstructions':hits,'test':'corridor polygon versus native cached F.CrtYd; wires, fingers, latch motion in Z and future case are not represented'}
silk=[{'text':x.GetText(),'xy_mm':xy(x.GetPosition())} for x in b.GetDrawings() if isinstance(x,P.PCB_TEXT) and x.GetLayer()==P.F_SilkS and x.GetText() in ['BATT+','GND','NTC','SPK:1+ 2-']]
mic=fps['U803'];mic_holes=[p for p in mic.Pads() if p.GetAttribute()==P.PAD_ATTRIB_NPTH]
mic_zones=[z for z in mic.Zones() if z.GetIsRuleArea()]
acoustic=poly(mic_zones[0].Outline());hole_center=Point(xy(mic_holes[0].GetPosition()))
mic_intrusions=[]
for lid in layer_ids:
    lname=b.GetLayerName(lid)
    for ref,f in fps.items():
        for p in f.Pads():
            if p.GetAttribute()!=P.PAD_ATTRIB_NPTH and p.IsOnLayer(lid):
                area=acoustic.intersection(padshape(p,lid)).area
                if area>1e-5:mic_intrusions.append({'layer':lname,'kind':'pad','ref':ref,'pad':p.GetNumber(),'area_mm2':rnd(area)})
    for t in b.GetTracks():
        if not t.IsOnLayer(lid):continue
        if t.GetClass()=='PCB_VIA': s=Point(xy(t.GetPosition())).buffer(mm(t.GetWidth(lid))/2)
        elif t.GetClass()=='PCB_TRACK':s=LineString([xy(t.GetStart()),xy(t.GetEnd())]).buffer(mm(t.GetWidth())/2)
        else:continue
        area=acoustic.intersection(s).area
        if area>1e-5:mic_intrusions.append({'layer':lname,'kind':t.GetClass(),'uuid':t.m_Uuid.AsString(),'area_mm2':rnd(area)})
    for z in b.Zones():
        if not z.GetIsRuleArea() and z.IsOnLayer(lid) and z.IsFilled():
            area=acoustic.intersection(poly(z.GetFilledPolysList(lid))).area
            if area>1e-5:mic_intrusions.append({'layer':lname,'kind':'zone_fill','net':z.GetNetname(),'area_mm2':rnd(area)})
population=[]
hand_smd_connectors={'J501','J701','J601','J406'}
for ref in sorted(fps,key=natural):
    f=fps[ref];attr=f.GetAttributes()
    group='do_not_populate' if f.IsDNP() else ('mechanical_hole_only' if ref.startswith('H') else ('post_reflow_tht_hand_solder' if attr&P.FP_THROUGH_HOLE else ('post_reflow_smd_connector_hand_solder' if ref in hand_smd_connectors else 'top_smd_reflow')))
    population.append({'ref':ref,'value':f.GetValue(),'mpn':f.GetFieldsText().get('Candidate_MPN',''),'footprint':f.GetFPIDAsString(),'group':group,'side':b.GetLayerName(f.GetLayer()),'xy_mm':xy(f.GetPosition()),'native_rotation_deg':f.GetOrientationDegrees(),'dnp':f.IsDNP(),'excluded_bom':f.IsExcludedFromBOM(),'excluded_position':f.IsExcludedFromPosFiles()})
groups={g:[x['ref'] for x in population if x['group']==g] for g in sorted({x['group'] for x in population})}
antenna=[{'bbox_mm':list(poly(z.Outline()).bounds),'layers':[b.GetLayerName(l) for l in layer_ids if z.IsOnLayer(l)],'no_tracks':z.GetDoNotAllowTracks(),'no_vias':z.GetDoNotAllowVias(),'no_pads':z.GetDoNotAllowPads(),'no_zone_fill':z.GetDoNotAllowZoneFills(),'no_footprints':z.GetDoNotAllowFootprints()} for z in fps['U301'].Zones() if z.GetIsRuleArea()]
after=sha(SRC)
if before!=after: raise ValueError('Formal PCB changed while reading')
report={'date':'2026-11-11','status':'PASS_GEOMETRY_WITH_ASSEMBLY_CONDITIONS','scope':'Read-only frozen r8 mechanical geometry and manual stencil/reflow preparation; no fabricated sample or cable inspected. Not a general fabrication/power-up approval.','source_board':str(SRC.relative_to(ROOT)),'source_board_sha256_before':before,'source_board_sha256_after':after,'source_unchanged':before==after,'board':{'outline_valid':outline_valid,'extent_mm':list(board.bounds),'size_mm':[rnd(board.bounds[2]-board.bounds[0]),rnd(board.bounds[3]-board.bounds[1])],'outline_area_mm2':rnd(board.area),'outline_count':outline.OutlineCount(),'outline_internal_cutouts':sum(outline.HoleCount(i) for i in range(outline.OutlineCount())),'copper_layers':len(layer_ids),'native_board_thickness_mm':mm(b.GetDesignSettings().GetBoardThickness()),'auxiliary_origin_mm':xy(b.GetDesignSettings().GetAuxOrigin()),'grid_origin_mm':xy(b.GetDesignSettings().GetGridOrigin())},'footprints_count':len(fps),'courtyard':{'method':'Native BuildCourtyardCaches + polygon intersection. KiCad cache boundaries can be 0.005 mm inward from graphic centreline. Values are planar courtyard geometry, not hand-access qualification.','missing':[r for r,s in courts.items() if s.is_empty],'pairs_tested':len(fps)*(len(fps)-1)//2,'overlaps':overlaps,'minimum_pair_distance':minimum,'outside_board':sorted(outside,key=lambda x:x['ref']),'minimum_inside_edge_distances':sorted(edge_distances,key=lambda x:x['distance_mm'])[:10]},'mounts':mounts,'connectors':connectors,'insertion_corridors':corridors,'silkscreen_polarity':silk,'antenna':antenna,'mic':{'ref':'U803','part':'DMM-4026-B-I2S-R','mount_side':'F.Cu','sound_entry_side':'B.Cu underside through board NPTH','hole_xy_mm':xy(mic_holes[0].GetPosition()),'hole_drill_mm':xy(mic_holes[0].GetDrillSize()),'keepout_bbox_mm':list(acoustic.bounds),'keepout_layers':[b.GetLayerName(l) for l in layer_ids if mic_zones[0].IsOnLayer(l)],'copper_intrusions':mic_intrusions,'case_opening':'No case designed; do not tape, glue, place foam or rest board directly against the underside acoustic opening.'},'population_group_counts':{k:len(v) for k,v in groups.items()},'population_groups':groups,'fitted_electrical_count':sum(x['group'] in ['top_smd_reflow','post_reflow_tht_hand_solder','post_reflow_smd_connector_hand_solder'] for x in population),'dnp_stencil_requirement':'DNP must be absent from both physical population and all final stencil apertures; a KiCad DNP flag by itself does not suppress plotted paste. Native paste remediation is audited separately.','manual_connector_stencil_requirement':'J501/J701/J601/J406 are fitted SMD connectors but excluded from the default stencil under user-selected manual connector soldering. Their SH apertures must also be absent; THT connectors/switches are hand-soldered after reflow.','module_paste_note':'U301 perimeter contacts reflow; central EPAD not printed under the selected optional-EPAD assembly profile. This is not a DNP module. Confirm actual thermal performance later.','position_notes':'Native footprint anchors and angles are recorded for manual assembly lookup only. No pick-and-place format conversion or outsourced PCBA submission was requested. Native auxiliary origin is (0,0); CAD coordinates are not package-centroid positions by definition.','conditions':['Use exact MPN/footprint; generic 0.5 mm FPC sockets and generic 1.25 mm wire housings are not interchangeable.','Existing passive 24P/6P extension is the accepted interface basis; verify full pin mapping and exposed-conductor face with power disconnected before first plug-in. No photo/model request is needed to continue board design.','GCT USB4105-GF-A shell stakes are 0.95±0.15 mm, nominal PCB 1.6 mm: they do not emerge from bottom. Inspect top-side shell-slot solder and retention after assembly; normal bottom-side protruding-pin solder practice is not sufficient.','Use insulating standoffs under H1-H4 for bench work; steel screw/washer envelope is not frozen. Screen, battery and speaker are external, not mounted by the PCB mechanical holes.','Observe mic bottom sound port and MCU antenna keep-clear volume during bench setup.']}
(OUT/'mechanical-review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
(OUT/'mechanical-population.json').write_text(json.dumps({'source_board_sha256':before,'groups':groups,'components':population},ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'source_unchanged':before==after,'courtyard_overlap_count':len(overlaps),'outside':[x['ref'] for x in outside],'corridor_collisions':{r:v['other_footprint_obstructions'] for r,v in corridors.items() if v['other_footprint_obstructions']},'mic_intrusions':mic_intrusions,'groups':{k:len(v) for k,v in groups.items()},'minimum_pair_distance':minimum,'mounts':mounts},ensure_ascii=False,indent=2))

#!/usr/bin/env python3
"""Independent exact object/geometry delta review for r10; never writes the PCB.

Requires system pcbnew and Shapely. Native serialized geometry is compared by
UUID with numeric normalization (not file hashes alone). Refilled plane changes
are geometrically bounded to moved via clearances. The contract is a reviewed
scope, not an imported routing-generator implementation.
"""
from pathlib import Path
import argparse, collections, csv, hashlib, json, math, re
from decimal import Decimal
import pcbnew as P
from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union

ROOT = next(p for p in Path(__file__).resolve().parents if (p/'hardware/devboard-r0').is_dir())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def uid(o): return o.m_Uuid.AsString()
def nm(p): return [p.x,p.y]
def mmxy(p): return [P.ToMM(p.x),P.ToMM(p.y)]
def parse(path):
    tokens = re.findall(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+', path.read_text())
    stack=[]; root=None
    for token in tokens:
        if token=='(':
            v=[]
            if stack: stack[-1].append(v)
            else: root=v
            stack.append(v)
        elif token==')': stack.pop()
        else:
            if token.startswith('"'): value=json.loads(token)
            else:
                try: value=Decimal(token)
                except Exception: value=token
            stack[-1].append(value)
    if stack or root[0]!='kicad_pcb': raise ValueError('Malformed native PCB')
    return root
def tag(v): return v[0] if isinstance(v,list) and v else None
def child(v,name): return next((x for x in v[1:] if tag(x)==name),None)
def oid(v):
    x=child(v,'uuid'); return x[1] if x else None
def stripped(v,keys): return [x for x in v if not(isinstance(x,list) and tag(x) in keys)]
def indexed(tree,kinds): return {oid(v):v for v in tree[1:] if tag(v) in kinds}
def firstdiff(a,b,path=''):
    if type(a)!=type(b): return {'path':path,'before':str(a)[:150],'after':str(b)[:150]}
    if isinstance(a,list):
        if len(a)!=len(b): return {'path':path,'before_length':len(a),'after_length':len(b)}
        for i,(x,y) in enumerate(zip(a,b)):
            if x!=y: return firstdiff(x,y,f'{path}/{tag(x) or i}')
    elif a!=b: return {'path':path,'before':str(a),'after':str(b)}
    return None
def polyset(ps):
    shapes=[]
    for i in range(ps.OutlineCount()):
        line=ps.COutline(i);outer=[mmxy(line.CPoint(j)) for j in range(line.PointCount())]
        holes=[]
        for h in range(ps.HoleCount(i)):
            line=ps.CHole(i,h);holes.append([mmxy(line.CPoint(j)) for j in range(line.PointCount())])
        shapes.append(Polygon(outer,holes).buffer(0))
    return unary_union(shapes)
def returns(board):
    vias=[t for t in board.GetTracks() if isinstance(t,P.PCB_VIA)]
    gnd=[t for t in vias if t.GetNetname()=='GND'];rows={}
    for t in vias:
        if t.GetNetname()=='GND':continue
        near=min(gnd,key=lambda v:math.dist(nm(t.GetPosition()),nm(v.GetPosition())))
        rows[uid(t)]={'net':t.GetNetname(),'position_mm':mmxy(t.GetPosition()),'nearest_GND_uuid':uid(near),
                     'nearest_GND_position_mm':mmxy(near.GetPosition()),'distance_mm':math.dist(nm(t.GetPosition()),nm(near.GetPosition()))/1e6}
    return rows
def compare_fill_geometry(before,after,allowed):
    delta=before.symmetric_difference(after);outside=delta.difference(allowed)
    polygons=[outside] if outside.geom_type=='Polygon' else list(getattr(outside,'geoms',[]))
    pts=[]
    for p in polygons:
        if p.geom_type=='Polygon':
            pts.extend(p.exterior.coords)
            for ring in p.interiors:pts.extend(ring.coords)
    displacement=max((max(before.boundary.distance(Point(q)),after.boundary.distance(Point(q))) for q in pts),default=0.)
    return {'changed_area_mm2':delta.area,'outside_allowed_region_mm2':outside.area,
            'outside_max_distance_to_fill_boundaries_mm':displacement,
            'rounding_allowance_area_mm2':1e-6,'rounding_allowance_distance_mm':.000002,
            'pass':outside.area<=1e-6 and displacement<=.000002}
def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--baseline',type=Path,default=ROOT/'build/dfm-r10/intake/ESPaperPlay_Devboard.kicad_pcb')
    ap.add_argument('--candidate',type=Path,required=True)
    ap.add_argument('--contract',type=Path,default=Path(__file__).with_name('r10-delta-contract.json'))
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args(); c=json.loads(args.contract.read_text()); errors=[]
    def check(ok,kind,**detail):
        if not ok:errors.append({'kind':kind,**detail})
    check(sha(args.baseline)==c['baseline_sha256'],'baseline_hash')
    before_sha,after_sha=sha(args.baseline),sha(args.candidate)
    a=P.LoadBoard(str(args.baseline));b=P.LoadBoard(str(args.candidate))
    sa,sb=parse(args.baseline),parse(args.candidate)
    # Full footprint subtrees cover pads, masks/paste, holes, nets, graphics,
    # fields/attributes, UUIDs, footprint zones and placements, not just centers.
    fa,fb=indexed(sa,{'footprint'}),indexed(sb,{'footprint'})
    check(fa.keys()==fb.keys(),'footprint_inventory')
    for i in fa.keys()&fb.keys():check(fa[i]==fb[i],'footprint_semantic_geometry_or_attribute',uuid=i,difference=firstdiff(fa[i],fb[i]))
    ta,tb=indexed(sa,{'via','segment','arc'}),indexed(sb,{'via','segment','arc'})
    na={uid(t):t for t in a.GetTracks()};nb={uid(t):t for t in b.GetTracks()}
    for filename,wanted in c['protected_design_files_sha256'].items():
        check(sha(ROOT/filename)==wanted,'protected_schematic_project_or_library_file',path=filename)
    for i in c['protected_thermal_via_uuids']:
        check(i in ta and i in tb and ta[i]==tb[i],'protected_IC_thermal_via',uuid=i)
    pa={uid(p):p for fp in a.GetFootprints() for p in fp.Pads()}
    pb={uid(p):p for fp in b.GetFootprints() for p in fp.Pads()}
    for i in c['protected_module_PTH_uuids']:
        check(i in pa and i in pb and pa[i].GetDrillSize()==pb[i].GetDrillSize() and pa[i].GetPosition()==pb[i].GetPosition(),'protected_module_thermal_PTH',uuid=i)
    targets=set(c['allowed_vias']);check(len(targets)==64,'target_count')
    attach=set()
    for i in targets:
        check(i in na and i in nb,'missing_target',uuid=i)
        if i not in na or i not in nb:continue
        v=na[i];rec=c['allowed_vias'][i]
        check(v.GetClass()=='PCB_VIA' and v.GetNetname()==rec['net'] and nm(v.GetPosition())==rec['before_nm'],'target_baseline',uuid=i)
        for j,t in na.items():
            if t.GetClass()!='PCB_VIA' and t.GetNetname()==v.GetNetname() and (t.GetStart()==v.GetPosition() or t.GetEnd()==v.GetPosition()):attach.add(j)
    removed=set(ta)-set(tb);added=set(tb)-set(ta)
    check(not removed,'removed_route_objects',uuids=sorted(removed))
    check(len(added)<=c['limits']['maximum_added_GND_segments'],'too_many_added_routes')
    for i in added:
        t=nb[i]
        check(t.GetClass()=='PCB_TRACK' and t.GetNetname()=='GND','added_non_GND_segment',uuid=i)
        check(t.GetLength()/1e6<=c['limits']['added_GND_segment_max_length_mm'],'added_segment_too_long',uuid=i)
        local=min(min(math.dist(nm(t.GetStart()),nm(nb[j].GetPosition())),math.dist(nm(t.GetEnd()),nm(nb[j].GetPosition()))) for j in targets if nb[j].GetNetname()=='GND')/1e6
        check(local<=.001,'added_segment_not_attached_to_moved_GND_via',uuid=i)
    changed=[i for i in ta.keys()&tb.keys() if ta[i]!=tb[i]];details=[]
    resized={v['uuid']:v for v in c['resized_vias']}
    for i in changed:
        before,after=ta[i],tb[i];t0,t1=na[i],nb[i]
        check(i in targets|attach,'unapproved_copper_change',uuid=i)
        if i in targets:
            permit={'at'}
            if i in resized:
                permit|={'size','drill'};s=resized[i]
                check(t0.GetWidth(P.F_Cu)==s['before_size_nm'] and t0.GetDrillValue()==s['before_drill_nm'] and t1.GetWidth(P.F_Cu)==s['after_size_nm'] and t1.GetDrillValue()==s['after_drill_nm'],'resized_via_dimensions')
            check(stripped(before,permit)==stripped(after,permit),'target_via_nonposition_change',uuid=i,difference=firstdiff(stripped(before,permit),stripped(after,permit)))
        elif i in attach:
            check(stripped(before,{'start','end'})==stripped(after,{'start','end'}),'attached_segment_other_property',uuid=i)
            for label,getter in [('start','GetStart'),('end','GetEnd')]:
                p0,p1=getattr(t0,getter)(),getattr(t1,getter)()
                if p0==p1:continue
                owners=[j for j in targets if na[j].GetPosition()==p0 and na[j].GetNetname()==t0.GetNetname()]
                check(bool(owners) and any(nb[j].GetPosition()==p1 for j in owners),'endpoint_not_following_target_via',uuid=i,endpoint=label,before_nm=nm(p0),after_nm=nm(p1))
        details.append({'uuid':i,'kind':tag(before),'net':t0.GetNetname(),'before_start_mm':mmxy(t0.GetStart()),'before_end_mm':mmxy(t0.GetEnd()),'after_start_mm':mmxy(t1.GetStart()),'after_end_mm':mmxy(t1.GetEnd())})
    check(set(i for i in changed if tag(ta[i])=='via')==targets,'changed_via_set')
    # Keep all other board constructs exact; allow only documented title/text.
    da,db=indexed(sa,{'gr_text'}),indexed(sb,{'gr_text'})
    check(da.keys()==db.keys(),'board_text_inventory');text_changes=[]
    for i in da.keys()&db.keys():
        if da[i]==db[i]:continue
        check(i in c['allowed_board_text'] and db[i][1]==c['allowed_board_text'].get(i) and da[i][2:]==db[i][2:],'board_text_change',uuid=i)
        text_changes.append({'uuid':i,'before':da[i][1],'after':db[i][1]})
    titlea=child(sa,'title_block');titleb=child(sb,'title_block')
    if titlea!=titleb:
        expected=json.loads(json.dumps(titlea,default=str))
        for x in expected[1:]:
            if x[0] in ('title','date','rev'):x[1]=c['title_block'][x[0]]
            if x[0]=='comment' and str(x[1])=='1':x[1]=Decimal(1);x[2]=c['title_block']['comment_1']
            elif x[0]=='comment':x[1]=Decimal(x[1])
        check(expected==titleb,'title_block_change',difference=firstdiff(expected,titleb))
    za,zb=indexed(sa,{'zone'}),indexed(sb,{'zone'})
    check(za.keys()==zb.keys(),'zone_inventory')
    for i in za.keys()&zb.keys():check(stripped(za[i],{'filled_polygon'})==stripped(zb[i],{'filled_polygon'}),'zone_settings_or_outline_change',uuid=i)
    ignored={'footprint','segment','arc','via','zone','gr_text','title_block'}
    check(stripped(sa,ignored)==stripped(sb,ignored),'other_board_geometry_or_settings',difference=firstdiff(stripped(sa,ignored),stripped(sb,ignored)))
    # Native exact plane geometry: changed fill must stay near reviewed vias.
    zone_changes=[]
    az={uid(z):z for z in a.Zones()};bz={uid(z):z for z in b.Zones()}
    for i in az:
        for layer in az[i].GetLayerSet().Seq():
            # Include clearance and a 2*minimum-fill-thickness local merging
            # neighborhood. This bounds local antipad neck re-polygonization;
            # it does not permit an arbitrary plane change elsewhere.
            clearance=bz[i].GetLocalClearance()/1e6
            minthickness=bz[i].GetMinThickness()/1e6
            regions=[Point(mmxy(m[j].GetPosition())).buffer(m[j].GetWidth(layer)/2e6+clearance+2*minthickness)
                     for j in targets for m in (na,nb)]
            p0=polyset(az[i].GetFilledPolysList(layer));p1=polyset(bz[i].GetFilledPolysList(layer))
            geometry=compare_fill_geometry(p0,p1,unary_union(regions))
            check(geometry['pass'],'unexpected_plane_fill_change',uuid=i,layer=b.GetLayerName(layer),**geometry)
            zone_changes.append({'uuid':i,'layer':b.GetLayerName(layer),'before_area_mm2':p0.area,'after_area_mm2':p1.area,
                                 'zone_clearance_mm':clearance,'zone_min_thickness_mm':minthickness,
                                 'allowed_region':'Union of old/new target via disks: radius=via copper radius+zone clearance+2*zone minimum fill thickness',**geometry})
    # Negative control specifically proves that the rounding/locality allowance
    # does not accept a 0.1x0.1mm unrelated plane void.
    mock=box(0,0,10,10);negative=compare_fill_geometry(mock,mock.difference(box(8,8,8.1,8.1)),Point(1,1).buffer(.5))
    check(not negative['pass'],'plane_negative_control_did_not_reject_unrelated_void')
    r0,r1=returns(a),returns(b);check(r0.keys()==r1.keys(),'signal_via_inventory')
    rr=[]
    for i in sorted(r0.keys()&r1.keys()):
        x,y=r0[i],r1[i];rr.append({'uuid':i,'net':x['net'],'before':x,'after':y,'distance_change_mm':y['distance_mm']-x['distance_mm'],'newly_above_2mm':x['distance_mm']<=2 and y['distance_mm']>2,'after_above_2mm':y['distance_mm']>2})
    new_over=[x for x in rr if x['newly_above_2mm']]
    check(not new_over,'new_return_via_distance_above_2mm',uuids=[x['uuid'] for x in new_over])
    check(sha(args.baseline)==before_sha and sha(args.candidate)==after_sha,'source_changed_during_check')
    report={'status':'PASS' if not errors else 'FAIL','method':'Exact parsed native objects by UUID with numeric normalization; native plane polygon symmetric differences and native return-via geometry. No generator imported.','source':str(args.baseline),'source_sha256':before_sha,'candidate':str(args.candidate),'candidate_sha256':after_sha,'contract_sha256':sha(args.contract),'checker_sha256':sha(Path(__file__)),'footprints_compared':len(fa),'footprints_exact_semantic_geometry_fields_and_UUIDs_unchanged':fa==fb,'route_objects_before':len(ta),'route_objects_after':len(tb),'approved_via_count':len(targets),'attached_segments_derived_from_baseline':len(attach),'changed_via_count':sum(tag(ta[i])=='via' for i in changed),'changed_segment_count':sum(tag(ta[i]) in ('segment','arc') for i in changed),'added_route_count':len(added),'removed_route_count':len(removed),'changes':sorted(details,key=lambda x:x['uuid']),'board_text_changes':text_changes,'title_changed':titlea!=titleb,'zone_fill_geometry':zone_changes,'unrelated_plane_void_negative_control':negative,'return_via_review':{'criterion_mm':2,'criterion_is_internal_geometry_target_not_impedance_guarantee':True,'all_signal_vias_checked':len(rr),'newly_above_target':new_over,'all_after_above_target':[x for x in rr if x['after_above_2mm']],'all_records':rr},'errors':errors}
    report['protected_IC_thermal_via_count']=len(c['protected_thermal_via_uuids'])
    report['protected_module_PTH_count']=len(c['protected_module_PTH_uuids'])
    report['protected_schematic_project_library_file_count']=len(c['protected_design_files_sha256'])
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ['status','footprints_compared','changed_via_count','changed_segment_count','added_route_count','removed_route_count','errors']},ensure_ascii=False,indent=2));print('Newly above 2mm:',len(new_over))
    return bool(errors)
if __name__=='__main__':raise SystemExit(main())

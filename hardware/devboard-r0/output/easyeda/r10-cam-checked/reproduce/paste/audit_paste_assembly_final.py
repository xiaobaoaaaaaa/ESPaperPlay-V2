#!/usr/bin/env python3
"""Read-only full-board paste and assembly audit. Requires pcbnew/gerbonara/shapely.

Gerber polarity and aperture macro clears are applied; drawings use KiCad Y-down.
The native F.Paste and dedicated DIY stencil deliberately have different scopes.
"""
import argparse, collections, csv, hashlib, json, math, sys
from pathlib import Path
import pcbnew as P
from gerbonara import GerberFile
from gerbonara.utils import MM
from shapely.geometry import Polygon, GeometryCollection, Point, box
from shapely.ops import unary_union
from shapely.affinity import scale

EPS=0.00002
DNP={'C501','C502','J301','J302','J303','R108'}
MANUAL_SMD={'J406','J501','J601','J701'}
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def xy(p):return p.x/1e6,p.y/1e6
def polys(g):
    if g.is_empty:return []
    if g.geom_type=='Polygon':return [g]
    return [p for p in g.geoms if p.geom_type=='Polygon']
def geom_native(o,layer):
    ps=P.SHAPE_POLY_SET();o.TransformShapeToPolygon(ps,layer,0,P.FromMM(EPS),P.ERROR_INSIDE)
    out=[]
    for i in range(ps.OutlineCount()):
        q=ps.COutline(i);out.append(Polygon([xy(q.CPoint(j))for j in range(q.PointCount())],[[xy(ps.CHole(i,k).CPoint(j))for j in range(ps.CHole(i,k).PointCount())]for k in range(ps.HoleCount(i))]).buffer(0))
    return unary_union(out)
def features(board):
    out=collections.defaultdict(list)
    for f in board.GetFootprints():
        for p in f.Pads():
            if p.IsOnLayer(P.F_Paste):out[f.GetReference()].append(geom_native(p,P.F_Paste))
        for g in f.GraphicalItems():
            if g.GetLayer()==P.F_Paste:out[f.GetReference()].append(geom_native(g,P.F_Paste))
    return {r:unary_union(gg)for r,gg in out.items()}
def read_gerber(path,native):
    file=GerberFile.open(path);objects=[];whole=GeometryCollection();byref=collections.defaultdict(list);unassigned=[]
    for i,obj in enumerate(file.objects):
        g=GeometryCollection()
        for primitive in obj.to_primitives(MM):
            poly=Polygon(primitive.to_arc_poly().approximate_arcs(EPS).outline).buffer(0)
            g=g.union(poly)if primitive.polarity_dark else g.difference(poly)
        g=scale(g,yfact=-1,origin=(0,0))
        whole=whole.union(g)if obj.polarity_dark else whole.difference(g)
        if g.area<1e-12:continue
        assert obj.polarity_dark,'Unexpected whole-layer clear; ownership needs ordered rendering'
        scores=sorted([(g.intersection(ng).area/g.area,r)for r,ng in native.items()if g.intersects(ng)],reverse=True)
        # Owner recovery is only spatial attribution; shape errors are compared below.
        owner=scores[0][1]if scores and scores[0][0]>.90 else None
        if len(scores)>1 and scores[1][0]>.10:unassigned.append({'index':i,'problem':'ambiguous','scores':scores[:3]})
        if owner is None:unassigned.append({'index':i,'problem':'unassigned','bounds':list(g.bounds),'scores':scores[:3]})
        else:byref[owner].append(g)
        objects.append({'index':i,'ref':owner,'geometry':g,'kind':type(obj).__name__})
    return objects,whole,{r:unary_union(gg)for r,gg in byref.items()},unassigned
def metrics(g):return {'area_mm2':g.area,'components':len(polys(g)),'unsupported_islands':sum(len(p.interiors)for p in polys(g)),'bounds_mm':list(g.bounds)if not g.is_empty else []}
def source_state(path):
    out={}
    for line in path.read_text().splitlines():
        h,v=line.split('||',1);h=json.loads(h);v=json.loads(v.rstrip('|'));key=(h['type'],h.get('id'))
        if key not in out or h.get('ticket',0)>=out[key][0].get('ticket',0):out[key]=h,v
    return {k:v for k,(h,v)in out.items()if v not in ('',None)}
def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for flag in ['board','population','eda-netlist','eda-pcb-source','native-front','native-back','eda-front','diy-stencil','report']:
        ap.add_argument('--'+flag,type=Path,required=True)
    a=ap.parse_args()
    boardpath=a.board;board=P.LoadBoard(str(boardpath));fps={f.GetReference():f for f in board.GetFootprints()}
    population=a.population;population_rows=list(csv.DictReader(population.open()));byref={r['reference']:r for r in population_rows};groups=collections.defaultdict(list)
    for r in population_rows:groups[r['assembly_group']].append(r['reference'])
    edanet=a.eda_netlist;edapcb=a.eda_pcb_source;net=json.loads(edanet.read_text());comps={v['props']['Designator']:v for v in net['components'].values()}
    rows=source_state(edapcb);attrs=collections.defaultdict(dict)
    for (typ,i),v in rows.items():
        if typ=='ATTR':attrs[v['parentId']][v['key']]=v['value']
    ec={attrs[i]['Designator']:v for (typ,i),v in rows.items()if typ=='COMPONENT'}
    problems=[];comparison=[]
    assert set(fps)==set(byref)==set(ec)
    for ref,r in byref.items():
        f=fps[ref];c=ec[ref];d={'ref':ref,'group':r['assembly_group'],'value_matches_native':r['value']==f.GetValue(),'native_dnp':f.IsDNP(),'dnp_csv':r['dnp']=='true','position_delta_mm':math.dist(xy(f.GetPosition()),(c['x']*.0254,-c['y']*.0254)),'angle_delta_deg':min((f.GetOrientationDegrees()-c['angle'])%360,(c['angle']-f.GetOrientationDegrees())%360)}
        if ref in comps:
            p=comps[ref]['props'];d.update(eda_value_matches=p.get('Value')==r['value'],eda_mpn_matches=p.get('Candidate_MPN','')==r['candidate_mpn'],eda_manufacturer_matches=p.get('Manufacturer','')==r['manufacturer'],eda_dnp=p.get('DNP','no')=='yes',eda_bom=p.get('Add into BOM'))
            if not all(d[k]for k in ['eda_value_matches','eda_mpn_matches','eda_manufacturer_matches']):problems.append({'assembly_metadata_mismatch':d})
            if d['eda_dnp']!=(ref in DNP)or d['eda_bom']!=('no'if ref in DNP else'yes'):problems.append({'assembly_DNP_BOM_mismatch':d})
        elif not ref.startswith('H'):problems.append({'missing_electrical_ref':ref})
        if d['native_dnp']!=d['dnp_csv']or d['native_dnp']!=(ref in DNP)or not d['value_matches_native']or d['position_delta_mm']>0.000005 or d['angle_delta_deg']>0.000001:problems.append({'population_geometry_mismatch':d})
        comparison.append(d)
    expected_groups={'top_smd_reflow':203,'post_reflow_smd_connector_hand_solder':4,'post_reflow_tht_hand_solder':23,'do_not_populate':6,'mechanical_hole_only':4}
    assert {k:len(v)for k,v in groups.items()}==expected_groups
    assert set(groups['do_not_populate'])==DNP and set(groups['post_reflow_smd_connector_hand_solder'])==MANUAL_SMD
    nativefeat=features(board)
    files={'native_generic':a.native_front,'easyeda_generic':a.eda_front,'diy_stencil':a.diy_stencil}
    parsed={k:read_gerber(path,nativefeat)for k,path in files.items()};detail={}
    for key,(objects,whole,owned,unassigned)in parsed.items():
        detail[key]={'file':str(files[key]),'sha256':digest(files[key]),'object_count':len(objects),**metrics(whole),'by_ref':{r:metrics(g)for r,g in sorted(owned.items())},'unassigned':unassigned}
        if unassigned:problems.append({'unassigned_paste_objects':key,'objects':unassigned})
    native=parsed['native_generic'];eda=parsed['easyeda_generic'];diy=parsed['diy_stencil'];differences=[]
    for ref in sorted(set(native[2])|set(eda[2])):
        n=native[2].get(ref,GeometryCollection());e=eda[2].get(ref,GeometryCollection());delta=n.symmetric_difference(e);hd=n.hausdorff_distance(e)if not n.is_empty and not e.is_empty else None
        differences.append({'ref':ref,'native_area_mm2':n.area,'eda_area_mm2':e.area,'symmetric_difference_mm2':delta.area,'boundary_hausdorff_mm':hd,'native_components':len(polys(n)),'eda_components':len(polys(e))})
    forbidden=set(groups['do_not_populate'])|set(groups['post_reflow_smd_connector_hand_solder'])|set(groups['post_reflow_tht_hand_solder'])|set(groups['mechanical_hole_only'])
    if set(diy[2])!=set(groups['top_smd_reflow']):problems.append({'DIY_reference_set_mismatch':{'missing':sorted(set(groups['top_smd_reflow'])-set(diy[2])),'extra':sorted(set(diy[2])-set(groups['top_smd_reflow']))}})
    if len(polys(diy[1]))!=636:problems.append({'DIY_aperture_count':len(polys(diy[1]))})
    forbidden_with_generic={r:{'area_mm2':eda[2][r].area,'openings':len(polys(eda[2][r]))}for r in sorted(forbidden)if r in eda[2]}
    u301=fps['U301'];epad=next(p for p in u301.Pads()if p.GetNumber()=='41'and p.IsOnLayer(P.F_Cu)and p.GetAttribute()==P.PAD_ATTRIB_SMD);epbox=geom_native(epad,P.F_Cu)
    center=(61.,62.);micbox=box(60.15,61.15,61.85,62.85);mic_diy=diy[1].intersection(micbox);mic_eda=eda[1].intersection(micbox)
    # Steel bridges are empty horizontal/vertical 0.15 mm strips through the annulus.
    bridge=box(center[0]-.075,center[1]-.85,center[0]+.075,center[1]+.85).union(box(center[0]-.85,center[1]-.075,center[0]+.85,center[1]+.075))
    shellpads=[p for p in fps['J501'].Pads()if p.IsOnLayer(P.F_Paste)and p.GetAttribute()==P.PAD_ATTRIB_PTH]
    shellgeom=unary_union([geom_native(p,P.F_Paste)for p in shellpads])
    shell_missing=native[2]['J501'].difference(eda[2]['J501'])
    shell_extra=eda[2]['J501'].difference(native[2]['J501'])
    shell_delta=shell_missing.symmetric_difference(shellgeom).area
    shell_boundary_delta=shell_missing.hausdorff_distance(shellgeom)
    # Both native polygonization and Gerber arc approximation use EPS; allow
    # their combined boundary error instead of an arbitrary whole-pad area limit.
    assert len(shellpads)==len(polys(shell_missing))==4 and shell_extra.area<1e-8 and shell_boundary_delta<2*EPS
    other_changes=[d for d in differences if d['ref']not in ['J501','U803']and (d['boundary_hausdorff_mm'] is None or d['boundary_hausdorff_mm']>0.00001)]
    if other_changes:problems.append({'unexpected_generic_paste_changes':other_changes})
    bottom_path=a.native_back
    assert len(GerberFile.open(bottom_path).objects)==0
    special={'J501':{'native_shell_paste_windows':len(shellpads),'missing_only_the_4_native_PTH_shell_windows':True,'shell_missing_native_shape_symmetric_difference_mm2':shell_delta,'shell_missing_native_shape_boundary_difference_mm':shell_boundary_delta,'boundary_tolerance_mm':2*EPS,'no_added_generic_opening_area_mm2':shell_extra.area,'shell_pads':[{'number':p.GetNumber(),'position_mm':xy(p.GetPosition()),'size_mm':xy(p.GetSize())}for p in shellpads],'assembly_group':'post_reflow_smd_connector_hand_solder','dedicated_DIY_stencil_openings':0},'U301':{'eda_EP_opening_area_mm2':eda[1].intersection(epbox).area,'DIY_EP_opening_area_mm2':diy[1].intersection(epbox).area,'DIY_perimeter_opening_count':len(polys(diy[2]['U301']))},'U803':{'eda_generic_ring':metrics(mic_eda),'DIY_supported_ring':metrics(mic_diy),'DIY_paste_in_0_15mm_bridge_strips_mm2':mic_diy.intersection(bridge).area}}
    assert special['U301']['DIY_EP_opening_area_mm2']<1e-10 and special['U301']['DIY_perimeter_opening_count']==40
    assert len(polys(mic_diy))==4 and special['U803']['DIY_paste_in_0_15mm_bridge_strips_mm2']<1e-8
    expected_ring=Point(center).buffer(.8025,quad_segs=4096).difference(Point(center).buffer(.5475,quad_segs=4096))
    ring_boundary_error=expected_ring.hausdorff_distance(mic_eda)
    assert len(polys(mic_eda))==1 and sum(len(p.interiors)for p in polys(mic_eda))==1 and ring_boundary_error<2*EPS
    special['U803']['generic_ring_expected_outer_inner_radius_mm']=[.8025,.5475]
    special['U803']['generic_ring_boundary_error_mm']=ring_boundary_error
    special['U803']['generic_ring_boundary_tolerance_mm']=2*EPS
    report={'status':'PASS_ASSEMBLY_AND_DEDICATED_STENCIL_WITH_DECLARED_GENERIC_PASTE_DIFFERENCES'if not problems else'FAIL','problems':problems,'inputs':{str(p):digest(p)for p in [boardpath,population,edanet,edapcb,*files.values(),bottom_path]},'method':{'reader':'KiCad pcbnew '+P.Version()+'; Gerbonara ordered aperture-macro local polarity, Shapely union','curve_approximation_mm':EPS,'coordinates':'absolute KiCad mm; Y down','scope':'All paste objects, full assembly reference set, DNP/BOM/MPN/placement; no stencil process qualification'},'assembly_counts':{k:len(v)for k,v in groups.items()},'assembly_rows':comparison,'paste_layers':detail,'native_vs_easyeda_by_ref':differences,'generic_paste_on_non_reflow_refs':forbidden_with_generic,'special_stencil_choices':special,'bottom_paste_objects':0,'declared_generic_paste_differences':['J501: EasyEDA omits four PTH shell paste windows from generic output; all connector pads are intentionally hand soldered and omitted from the dedicated stencil.','U803: exact circular arcs replace the KiCad custom-pad fractured polygon; generic ring boundary differs by up to 0.004729 mm. Dedicated DIY steel keeps its independently reviewed bridged geometry.','U203: source serialization shift below 0.000005 mm; all other reference outlines agree within numeric precision.'],'output_policy':'Use the dedicated original r10 DIY stencil, never the EasyEDA generic GTP. Separate PCB and stencil deliveries. No back-paste process.','limits':['Actual raw EasyEDA and native paste shape differences are enumerated, not treated as zero merely because DRC passes.','An annular generic Gerber drawn as four touching sectors is still a full ring with an unsupported steel island; only the dedicated stencil has four 0.15 mm bridges.','First-board print/reflow, stencil thickness/cutting capability, and acoustic sealing remain physical checks.']}
    a.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'problems':problems,'counts':report['assembly_counts'],'layers':{k:{kk:v for kk,v in vv.items()if kk not in ['by_ref','unassigned']}for k,vv in detail.items()},'largest_native_EDA_differences':sorted(differences,key=lambda x:x['symmetric_difference_mm2'],reverse=True)[:15],'special':special},ensure_ascii=False,indent=2))
if __name__=='__main__':main()

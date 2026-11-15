#!/usr/bin/env python3
"""Independent read-only KiCad placement/electrical/manufacturing audit.

No layout generator is imported. This is a placement check, not routing or
factory acceptance. pcbnew and Shapely are required. Coordinates are KiCad mm.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, math
from pathlib import Path
import xml.etree.ElementTree as ET
import pcbnew as P
from shapely.geometry import Polygon, GeometryCollection, Point
from shapely.ops import unary_union

MM=1e6
HOLES={'H1','H2','H3','H4'}
def xy(p):return [round(p.x/MM,6),round(p.y/MM,6)]
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def polyset(ps):
    polygons=[]
    for i in range(ps.OutlineCount()):
        q=ps.COutline(i)
        pts=[xy(q.CPoint(j))for j in range(q.PointCount())]
        holes=[]
        for h in range(ps.HoleCount(i)):
            qh=ps.CHole(i,h);holes.append([xy(qh.CPoint(j))for j in range(qh.PointCount())])
        if len(pts)>=3:polygons.append(Polygon(pts,holes))
    return unary_union(polygons)if polygons else GeometryCollection()
def canonical_fp(fp):
    f=P.Cast_to_FOOTPRINT(fp.Duplicate(False));f.SetOrientationDegrees(0);f.SetPosition(P.VECTOR2I(0,0));return f

def pad_record(p):
    custom=None
    if p.GetShape()==P.PAD_SHAPE_CUSTOM:
        custom=pad_geom(p).normalize().wkt
    return {'number':p.GetNumber(),'position':xy(p.GetPosition()),'size':xy(p.GetSize()),
      'angle':round(p.GetOrientationDegrees()%360,6),'shape':int(p.GetShape()),'attribute':int(p.GetAttribute()),
      'drill':xy(p.GetDrillSize()),'drill_shape':int(p.GetDrillShape()),'offset':xy(p.GetOffset()),
      'layers':p.GetLayerSet().FmtHex(),'roundrect_ratio':round(p.GetRoundRectRadiusRatio(),8),
      'chamfer_ratio':round(p.GetChamferRectRatio(),8),'chamfer_positions':p.GetChamferPositions(),
      'net':p.GetNetname(),'mask_margin':p.GetLocalSolderMaskMargin(),
      'paste_margin':p.GetLocalSolderPasteMargin(),'paste_ratio':p.GetLocalSolderPasteMarginRatio(),
      'zone_connection':int(p.GetLocalZoneConnection()),'custom_primitives':custom}
def zone_record(z):
    return {'layers':sorted(int(x)for x in z.GetLayerSet().Seq()),'rule_area':z.GetIsRuleArea(),
      'block_tracks':z.GetDoNotAllowTracks(),'block_vias':z.GetDoNotAllowVias(),'block_pads':z.GetDoNotAllowPads(),
      'block_zones':z.GetDoNotAllowZoneFills(),'block_footprints':z.GetDoNotAllowFootprints(),
      'geometry':polyset(z.Outline())}
def comparable(x):return json.dumps(x,sort_keys=True,separators=(',',':'))
def pad_geom(p):
    ps=P.SHAPE_POLY_SET();p.TransformShapeToPolygon(ps,P.F_Cu,0,P.FromMM(.00005),P.ERROR_INSIDE)
    return polyset(ps)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for k in ['board','baseline','netlist','report']:ap.add_argument('--'+k,type=Path,required=True)
    ap.add_argument('--project',type=Path,help='Default: board filename with .kicad_pro')
    ap.add_argument('--footprint-library',type=Path,help='Default: board directory/ESPaperPlay.pretty; U301 custom library geometry checked against placed footprint')
    ap.add_argument('--approved-pad-changes',type=Path,help='Optional list {ref,number,position,changes:{field:{before,after}},reason}; exact values, relative mm positions.')
    args=ap.parse_args();problems=[];warnings=[]
    def check(ok,kind,**details):
        if not ok:problems.append({'kind':kind,**details})
        return bool(ok)
    if not args.board.exists():raise SystemExit('Board not created yet: '+str(args.board))
    initial_inputs={str(p):digest(p) for p in [args.board,args.baseline,args.netlist,args.project or args.board.with_suffix('.kicad_pro'),args.board.with_suffix('.kicad_dru')] if p.exists()}
    b=P.LoadBoard(str(args.board));base=P.LoadBoard(str(args.baseline));root=ET.parse(args.netlist).getroot()
    fplists=collections.defaultdict(list)
    for f in b.GetFootprints():fplists[f.GetReference()].append(f)
    check(all(len(x)==1 for x in fplists.values()),'duplicate_refs',refs=[k for k,v in fplists.items()if len(v)!=1])
    fps={k:v[0]for k,v in fplists.items()};old={f.GetReference():f for f in base.GetFootprints()}
    refs={c.get('ref'):c for c in root.findall('components/comp')}
    pins={}
    for n in root.findall('nets/net'):
        for node in n.findall('node'):
            key=node.get('ref'),node.get('pin');check(key not in pins,'duplicate_XML_pin',key=key);pins[key]=n.get('name')
    check(len(refs)==236 and len(pins)==774 and len(root.findall('nets/net'))==181,'source_netlist_inventory',components=len(refs),pins=len(pins),nets=len(root.findall('nets/net')))
    check(set(fps)==set(old)==set(refs)|HOLES,'component_inventory',new=sorted(fps),baseline_count=len(old))
    check(b.GetCopperLayerCount()==4,'copper_layers',actual=b.GetCopperLayerCount())
    check(set(b.GetEnabledLayers().CuStack())=={P.F_Cu,P.In1_Cu,P.In2_Cu,P.B_Cu},'copper_layer_order')
    check(all(f.GetLayer()==P.F_Cu for f in fps.values()),'component_side',back=[r for r,f in fps.items()if f.GetLayer()!=P.F_Cu])
    check(len(b.GetTracks())==0,'placement_only_no_routing',count=len(b.GetTracks()))
    check(not any(not z.GetIsRuleArea()for z in b.Zones()),'placement_only_no_copper_pours',count=sum(not z.GetIsRuleArea()for z in b.Zones()))
    outline=P.SHAPE_POLY_SET();check(b.GetBoardPolygonOutlines(outline,False),'valid_outline')
    board_poly=polyset(outline);bb=board_poly.bounds
    check(outline.OutlineCount()==1 and outline.HoleCount(0)==0,'outline_topology')
    check(len(bb)==4 and abs(bb[2]-bb[0]-99)<.00001 and abs(bb[3]-bb[1]-99)<.00001,'dimensions_99mm',bounds=bb)
    project=args.project or args.board.with_suffix('.kicad_pro');rules={};netclasses={}
    if check(project.exists(),'project_file_missing',path=str(project)):
        pro=json.loads(project.read_text());ds=pro['board']['design_settings'];rules=ds['rules'];netclasses=pro.get('net_settings',{}).get('classes',[])
        check(rules.get('min_through_hole_diameter',0)>=.3-1e-9,'minimum_drill_rule',actual=rules.get('min_through_hole_diameter'))
        check(rules.get('min_via_diameter',0)>=.6-1e-9,'minimum_via_outer_rule',actual=rules.get('min_via_diameter'))
        check(rules.get('min_clearance',0)>=.15 and rules.get('min_track_width',0)>=.15,'track_clearance_rules',rules=rules)
        check(rules.get('min_copper_edge_clearance',0)>=.3,'copper_edge_rule')
        check(not ds.get('drc_exclusions'),'no_new_DRC_exclusions',actual=ds.get('drc_exclusions'))
        check(ds.get('rule_severities',{}).get('unconnected_items')!='ignore','unconnected_DRC_not_disabled')
        for v in ds.get('via_dimensions',[]):check(v.get('drill',0)>=.3 and v.get('diameter',0)>=.6,'via_preset',preset=v)
        for n in netclasses:
            if 'via_drill'in n:check(n['via_drill']>=.3,'netclass_drill',netclass=n.get('name'),drill=n['via_drill'])
    dru=args.board.with_suffix('.kicad_dru')
    if check(dru.exists(),'custom_rule_file_missing'):
        rule_text=dru.read_text()
        check("A.Type == 'Via' && A.Via_Type != 'Through'"in rule_text and '(constraint disallow via)'in rule_text,'through_only_rule_declared')
    check('(dielectric_constraints no)'in args.board.read_text(),'uncontrolled_dielectric_constraint')
    base_pro=args.baseline.with_suffix('.kicad_pro')
    if check(base_pro.exists(),'baseline_project_missing'):
        before_classes=json.loads(base_pro.read_text()).get('net_settings',{}).get('classes',[])
        def non_via_classes(classes):return {x['name']:{k:v for k,v in x.items()if k not in {'microvia_diameter','microvia_drill','via_diameter','via_drill'}}for x in classes}
        check(non_via_classes(netclasses)==non_via_classes(before_classes),'netclass_non_via_fields_preserved')
    approved=json.loads(args.approved_pad_changes.read_text())if args.approved_pad_changes else []
    approved=approved.get('changes',[])if isinstance(approved,dict)else approved
    used=set();pad_changes=[];pads_checked=0;drills=[];courtyards={};zones={};net_pin_set={};fp_checks=[];pad_beyond=[];pad_edge_too_close=[];library_checks=[]
    for ref,fp in fps.items():
        if ref not in old:continue
        of=old[ref];n=canonical_fp(fp);o=canonical_fp(of)
        np={original.m_Uuid.AsString():cloned for original,cloned in zip(fp.Pads(),n.Pads())};op={original.m_Uuid.AsString():cloned for original,cloned in zip(of.Pads(),o.Pads())}
        # Pad UUID identity avoids ambiguity among the repeated EPAD pin41 holes.
        check(np.keys()==op.keys(),'physical_pad_UUID_inventory',ref=ref,old=len(op),new=len(np))
        allowed_fpid='ESPaperPlay:ESP32-S3-WROOM-1_030mm_PTH'
        check(fp.GetFPIDAsString()==of.GetFPIDAsString()or(ref=='U301'and fp.GetFPIDAsString()==allowed_fpid),'footprint_ID',ref=ref,baseline=of.GetFPIDAsString(),current=fp.GetFPIDAsString())
        check(fp.GetValue()==of.GetValue(),'Value',ref=ref,old=of.GetValue(),new=fp.GetValue())
        check(fp.IsDNP()==of.IsDNP(),'DNP',ref=ref)
        check(fp.GetPath().AsString()==of.GetPath().AsString(),'schematic_UUID_path',ref=ref)
        check(fp.GetSheetname()==of.GetSheetname(),'schematic_sheet',ref=ref)
        for key in ['Manufacturer','Candidate_MPN','BOM_Review','BOM_Review_Record','Candidate_Source']:
            check(fp.GetFieldsText().get(key,'')==of.GetFieldsText().get(key,''),'BOM_field',ref=ref,field=key)
        if ref in refs:
            check(fp.GetValue()==refs[ref].findtext('value'),'XML_Value',ref=ref)
            check(fp.GetFPIDAsString()==refs[ref].findtext('footprint'),'XML_footprint_ID',ref=ref,board=fp.GetFPIDAsString(),netlist=refs[ref].findtext('footprint'))
        for uid,p in np.items():
            if uid not in op:continue
            x=pad_record(op[uid]);y=pad_record(p);ds={k:{'before':x[k],'after':y[k]}for k in x if x[k]!=y[k]}
            if ds:
                accepted=False;reason=''
                # Only the explicitly discussed embedded module drill change is implicit.
                if ref=='U301' and x['number']=='41'and x['attribute']==P.PAD_ATTRIB_PTH and ds=={'drill':{'before':[.2,.2],'after':[.3,.3]}}:
                    accepted=True;reason='coupon minimum-hole change: module EPAD drill0.20→0.30mm, all other fields unchanged'
                for i,r in enumerate(approved):
                    if r['ref']==ref and str(r['number'])==x['number']and r['position']==x['position']and r['changes']==ds:
                        accepted=True;used.add(i);reason=r['reason']
                check(accepted,'unapproved_pad_change',ref=ref,uuid=uid,number=x['number'],position=x['position'],changes=ds)
                pad_changes.append({'ref':ref,'number':x['number'],'uuid':uid,'position':x['position'],'changes':ds,'approved':accepted,'reason':reason})
            pads_checked+=1
        oz=[zone_record(z)for z in o.Zones()];nz=[zone_record(z)for z in n.Zones()]
        check(len(oz)==len(nz),'rule_area_count',ref=ref,old=len(oz),new=len(nz))
        for za,zb in zip(oz,nz):
            ga=za.pop('geometry');gb=zb.pop('geometry');check(za==zb and ga.hausdorff_distance(gb)<.00001,'rule_area_geometry_or_flags',ref=ref)
        zones[ref]=[(z,polyset(z.Outline()))for z in fp.Zones()if z.GetIsRuleArea()]
        c=polyset(fp.GetCourtyard(P.F_CrtYd));check(not c.is_empty,'missing_courtyard',ref=ref);check(c.is_valid,'invalid_courtyard',ref=ref);courtyards[ref]=c
        for p in fp.Pads():
            if p.GetNumber():net_pin_set.setdefault((ref,p.GetNumber()),set()).add(p.GetNetname())
            else:check(p.GetNetCode()==0,'unnumbered_pad_has_net',ref=ref)
            d=xy(p.GetDrillSize())
            if max(d)>0:
                check(min(d)>=.3-1e-9,'small_physical_hole',ref=ref,pin=p.GetNumber(),diameters=d)
                drills.append({'ref':ref,'pin':p.GetNumber(),'position':xy(p.GetPosition()),'diameter_mm':d,'plated':p.GetAttribute()!=P.PAD_ATTRIB_NPTH})
            if p.IsOnLayer(P.F_Cu):
                g=pad_geom(p)
                if not board_poly.buffer(.00001).covers(g):pad_beyond.append({'ref':ref,'pin':p.GetNumber(),'position':xy(p.GetPosition()),'outside_area_mm2':g.difference(board_poly).area})
                edge_gap=g.distance(board_poly.boundary)
                if edge_gap<.3-.0001:pad_edge_too_close.append({'ref':ref,'pin':p.GetNumber(),'position':xy(p.GetPosition()),'gap_mm':edge_gap})
        if ref=='U301':
            libdir=args.footprint_library or args.board.parent/'ESPaperPlay.pretty';libpath=libdir/'ESP32-S3-WROOM-1_030mm_PTH.kicad_mod'
            if fp.GetFPIDAsString()==allowed_fpid and check(libpath.exists(),'local_module_library_missing',path=str(libpath)):
                lf=P.FootprintLoad(str(libdir),'ESP32-S3-WROOM-1_030mm_PTH');ln=canonical_fp(lf)
                def library_pad_signature(p):
                    rec=pad_record(p);rec.pop('net');return comparable(rec)
                pads_match=collections.Counter(library_pad_signature(p)for p in n.Pads())==collections.Counter(library_pad_signature(p)for p in ln.Pads())
                check(pads_match,'placed_module_vs_local_library_pads',ref=ref)
                zz=[zone_record(z)for z in ln.Zones()];bz=[zone_record(z)for z in n.Zones()];zone_match=len(zz)==len(bz)
                active=set(int(x)for x in b.GetEnabledLayers().CuStack())
                for za,zb in zip(zz,bz):
                    ga=za.pop('geometry');gb=zb.pop('geometry');za['layers']=[x for x in za['layers']if x in active];zb['layers']=[x for x in zb['layers']if x in active]
                    zone_match=zone_match and za==zb and ga.hausdorff_distance(gb)<.00001
                check(zone_match,'placed_module_vs_local_library_keepout',ref=ref)
                library_checks.append({'ref':ref,'path':str(libpath),'sha256':digest(libpath),'pad_geometry_match':pads_match,'keepout_match':zone_match})
        fp_checks.append({'ref':ref,'position_mm':xy(fp.GetPosition()),'angle_deg':fp.GetOrientationDegrees(),'courtyard_bounds_mm':list(c.bounds),'courtyard_area_mm2':c.area})
    check(len(used)==len(approved),'unused_approved_changes',indices=sorted(set(range(len(approved)))-used))
    check(all(len(v)==1 for v in net_pin_set.values()),'repeated_pad_number_net_conflict')
    actual={k:next(iter(v))for k,v in net_pin_set.items()}
    check(actual==pins,'pin_net_connections',missing=[str(k)for k in pins.keys()-actual.keys()],extra=[str(k)for k in actual.keys()-pins.keys()],mismatch=[{'pin':k,'expected':pins[k],'actual':actual[k]}for k in actual.keys()&pins.keys()if actual[k]!=pins[k]])
    check(not pad_beyond,'copper_pads_outside_board',pads=pad_beyond)
    check(not pad_edge_too_close,'copper_pads_below_0_30mm_edge_clearance',pads=pad_edge_too_close)
    overlaps=[];near=[];cr=list(courtyards)
    for i,ra in enumerate(cr):
        for rb in cr[i+1:]:
            ga=courtyards[ra];gb=courtyards[rb]
            if ga.is_empty or gb.is_empty:continue
            area=ga.intersection(gb).area
            if area>1e-6:overlaps.append({'a':ra,'b':rb,'area_mm2':area})
            else:
                d=ga.distance(gb)
                if d<.20:near.append({'a':ra,'b':rb,'gap_mm':d})
    check(not overlaps,'courtyard_overlaps',pairs=overlaps)
    if near:warnings.append({'kind':'courtyard_gaps_below_0_20mm_review','pairs':near})
    courtyard_beyond=[]
    # Exposed connector courtyards may legitimately straddle an edge; list them.
    for ref,g in courtyards.items():
        outside=g.difference(board_poly).area
        if outside>1e-6:
            courtyard_beyond.append({'ref':ref,'outside_area_mm2':outside,'bounds_mm':list(g.bounds)})
            check(ref in {'U301','J501','J601','J701','J406'},'unexpected_courtyard_outside_board',ref=ref,area=outside)
    keepout_conflicts=[]
    for ref,zs in zones.items():
        for z,geom in zs:
            if not z.GetDoNotAllowPads():continue
            for rr,f in fps.items():
                if rr==ref:continue
                for p in f.Pads():
                    if p.IsOnLayer(P.F_Cu)and geom.intersection(pad_geom(p)).area>1e-7:keepout_conflicts.append({'keepout_owner':ref,'pad_owner':rr,'pin':p.GetNumber()})
    check(not keepout_conflicts,'footprint_keepout_pad_conflicts',conflicts=keepout_conflicts)
    antennarec={}
    if 'U301'in fps:
        f=fps['U301'];g=courtyards['U301'];antennarec={'courtyard_outside_area_mm2':g.difference(board_poly).area,'rule_area_count':len(zones['U301']),'courtyard_bounds_mm':list(g.bounds),'module_reference_mm':xy(f.GetPosition())}
        check(len(zones['U301'])==1,'antenna_keepout_preserved')
        check(g.difference(board_poly).area>900,'antenna_edge_overhang_assumption',actual_outside_area=antennarec['courtyard_outside_area_mm2'])
    distances=[]
    for ra,pa,rb,pb,limit in [('C301','1','U301','2',5),('C302','1','U301','2',3),('C303','1','U301','3',5),('R503','2','U301','14',6),('R504','2','U301','13',6),('U501','1','J501','A6',7),('U501','2','J501','A7',7)]:
        aa=[p.GetPosition()for p in fps[ra].Pads()if p.GetNumber()==pa];bbp=[p.GetPosition()for p in fps[rb].Pads()if p.GetNumber()==pb]
        if aa and bbp:
            d=min(math.hypot(x.x-y.x,x.y-y.y)/MM for x in aa for y in bbp);item={'a':ra+'.'+pa,'b':rb+'.'+pb,'mm':d,'review_limit_mm':limit};distances.append(item)
            if d>limit:warnings.append({'kind':'critical_pad_distance_review',**item})
    check(all(Path(p).exists() and digest(Path(p))==h for p,h in initial_inputs.items()),'inputs_changed_during_audit')
    report={'status':'PASS_PLACEMENT_SCOPE'if not problems else'FAIL','stage':'unrouted placement; no claim of finished routing, thermal performance, CAM readiness or free-coupon acceptance','board':str(args.board),'outline_mm':list(board_poly.bounds),'size_mm':[board_poly.bounds[2]-board_poly.bounds[0],board_poly.bounds[3]-board_poly.bounds[1]],'electrical_components':len(refs),'physical_components':len(fps),'logical_pins':len(actual),'net_count':len(set(actual.values())),'physical_pads_checked':pads_checked,'approved_pad_changes':pad_changes,'local_library_checks':library_checks,'all_components_front':all(f.GetLayer()==P.F_Cu for f in fps.values()),'tracks_and_vias':len(b.GetTracks()),'physical_drills':drills,'project_rules':rules,'courtyard_pairs_overlapping':overlaps,'courtyards_outside_board':courtyard_beyond,'courtyard_area_on_board_mm2':unary_union(list(courtyards.values())).intersection(board_poly).area,'antenna':antennarec,'critical_pad_distances':distances,'placements':fp_checks,'errors':problems,'warnings':warnings,'connector_access_scope':'Courtyard/board-edge and actual pad checks only. Mating cable, plug clearance, FPC latch and card ejection require explicit mechanical envelopes and visual review.','inputs':{str(p):digest(p)for p in [args.board,args.baseline,args.netlist,project,dru,base_pro,Path(__file__)]if p.exists()}}
    args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:report[k]for k in ['status','size_mm','physical_components','logical_pins','net_count','physical_pads_checked','tracks_and_vias','errors','warnings']},ensure_ascii=False,indent=2));return 1 if problems else 0
if __name__=='__main__':raise SystemExit(main())

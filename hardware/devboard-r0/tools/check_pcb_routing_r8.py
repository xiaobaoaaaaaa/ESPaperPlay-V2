#!/usr/bin/env python3
"""Independent r8 routing structure check: XML + libraries + original identities vs native PCB.
Does not import or execute the layout generator. Does not modify the board.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
import pcbnew as P

ROOT=next(p for p in Path(__file__).resolve().parents if (p/'hardware/devboard-r0').is_dir())
PROJECT=ROOT/'hardware/devboard-r0'

def digest(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def mm(v): return round(P.ToMM(v),5)
def xy(p): return (mm(p.x),mm(p.y))
def norm_angle(a): return round(a%360,5)
def bbox(box): return [mm(box.GetX()),mm(box.GetY()),mm(box.GetWidth()),mm(box.GetHeight())]

def pad_signature(p):
    return (p.GetNumber(),xy(p.GetFPRelativePosition()),xy(p.GetSize()),
            norm_angle(p.GetFPRelativeOrientation().AsDegrees()),p.GetShape(),
            p.GetAttribute(),xy(p.GetDrillSize()),p.GetDrillShape(),xy(p.GetOffset()),
            p.GetLayerSet().FmtHex(),round(p.GetRoundRectRadiusRatio(),7),
            round(p.GetChamferRectRatio(),7),p.GetChamferPositions())

def zone_signature(z, copper_layers):
    # A footprint loaded from a library can name all 32 copper layers while a
    # placed board retains only its enabled layers. Compare the active scope.
    layers=tuple(l for l in z.GetLayerSet().Seq() if l in copper_layers)
    poly=z.Outline()
    contours=[]
    for i in range(poly.OutlineCount()):
        line=poly.COutline(i)
        contours.append(tuple(sorted(xy(line.CPoint(j)) for j in range(line.PointCount()))))
    return (layers,z.GetIsRuleArea(),z.GetDoNotAllowTracks(),z.GetDoNotAllowVias(),
            z.GetDoNotAllowPads(),z.GetDoNotAllowZoneFills(),z.GetDoNotAllowFootprints(),
            tuple(sorted(contours)),sum(poly.HoleCount(i) for i in range(poly.OutlineCount())))

def footprint_geometry(fp,copper_layers):
    clone=P.Cast_to_FOOTPRINT(fp.Duplicate(False))
    clone.SetOrientationDegrees(0)
    clone.SetPosition(P.VECTOR2I(0,0))
    return Counter(pad_signature(p) for p in clone.Pads()),Counter(zone_signature(z,copper_layers) for z in clone.Zones())

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--board',type=Path,default=PROJECT/'ESPaperPlay_Devboard.kicad_pcb')
    ap.add_argument('--netlist',type=Path,default=PROJECT/'output/validation/peripheral-r6.net.xml')
    ap.add_argument('--output',type=Path,default=PROJECT/'review-r8/independent-board-check.json')
    ap.add_argument('--identity',type=Path,default=(PROJECT/'review-r8/layout-r7-identity.json' if (PROJECT/'review-r8/layout-r7-identity.json').exists() else ROOT/'build/pcb-r8/layout-r7-identity.json'),help='Frozen r7 footprint/pad UUID and net identities; coordinate changes are allowed.')
    ap.add_argument('--drc',type=Path,help='Optional fresh native KiCad DRC JSON; when given, require no errors, unconnected items or parity failures.')
    a=ap.parse_args()
    errors=[]; warnings=[]
    def check(ok,kind,**detail):
        if not ok: errors.append(dict(kind=kind,**detail))
        return ok
    if not a.board.exists():
        print(json.dumps({'status':'WAITING_FOR_BOARD','board':str(a.board)})); return 2
    r=ET.parse(a.netlist).getroot()
    comps={c.get('ref'):c for c in r.findall('./components/comp')}
    expected_nets={}; pin_types={}
    for net in r.findall('./nets/net'):
        for node in net.findall('node'):
            key=(node.get('ref'),node.get('pin'))
            check(key not in expected_nets,'duplicate_xml_pin',ref=key[0],pin=key[1])
            expected_nets[key]=net.get('name'); pin_types[key]=node.get('pintype')
    check(len(comps)==236,'baseline_components',actual=len(comps))
    check(len(expected_nets)==774,'baseline_pin_connections',actual=len(expected_nets))
    b=P.LoadBoard(str(a.board))
    copper_layers=set(b.GetEnabledLayers().CuStack())
    check(b.GetCopperLayerCount()==4,'copper_layers',actual=b.GetCopperLayerCount())
    check(copper_layers=={P.F_Cu,P.In1_Cu,P.In2_Cu,P.B_Cu},'copper_layer_ids',actual=sorted(copper_layers))
    route_items=list(b.GetTracks())
    vias=[t for t in route_items if t.GetClass()=='PCB_VIA']
    traces=[t for t in route_items if t.GetClass() in ('PCB_TRACK','PCB_ARC')]
    check(bool(traces),'routing_missing',tracks=len(traces))
    check(bool(vias),'vias_missing',vias=len(vias))
    check(len(traces)+len(vias)==len(route_items),'unexpected_route_item_type',types=sorted({t.GetClass() for t in route_items}))
    inner_tracks=[{'net':t.GetNetname(),'layer':b.GetLayerName(t.GetLayer()),'start_mm':xy(t.GetStart()),'end_mm':xy(t.GetEnd())} for t in traces if t.GetLayer() not in (P.F_Cu,P.B_Cu)]
    check(not inner_tracks,'tracks_on_reserved_inner_ground_layers',items=inner_tracks)
    check(all(v.GetViaType()==P.VIATYPE_THROUGH and set(v.GetLayerSet().Seq())&copper_layers==copper_layers for v in vias),'non_through_or_incomplete_stack_via')
    identity=json.loads(a.identity.read_text()) if a.identity.exists() else {'footprints':{}}
    check(a.identity.exists(),'missing_frozen_layout_identity',path=str(a.identity))
    refs=defaultdict(list)
    for fp in b.GetFootprints(): refs[fp.GetReference()].append(fp)
    check(set(refs)==set(comps)|{'H1','H2','H3','H4'},'component_inventory',missing=sorted(set(comps)-set(refs)),unexpected=sorted(set(refs)-set(comps)-{'H1','H2','H3','H4'}))
    check(all(len(v)==1 for v in refs.values()),'duplicate_refs',duplicates={k:len(v) for k,v in refs.items() if len(v)!=1})
    fps={ref:arr[0] for ref,arr in refs.items() if len(arr)==1}
    check(set(fps)==set(identity['footprints']),'frozen_identity_inventory')
    for ref,fp in fps.items():
        original=identity['footprints'].get(ref)
        if original is None: continue
        check(fp.m_Uuid.AsString()==original['uuid'],'footprint_uuid',ref=ref)
        actual_pads=sorted([p.m_Uuid.AsString(),p.GetNumber(),p.GetNetname()] for p in fp.Pads())
        check(actual_pads==original['pad_identities'],'pad_uuid_number_or_net',ref=ref)
        check(fp.GetLayer()==P.F_Cu,'component_side_changed',ref=ref,layer=b.GetLayerName(fp.GetLayer()))
    libs={}; libhashes={}; dnp=[]; numbered=0; empty_copper=[]; netpad_counts=Counter(); positions={}; rulecounts={}
    candidate_fields=('Design_Note','Manufacturer','Candidate_MPN','BOM_Review','BOM_Review_Record','Candidate_Source')
    for ref,c in comps.items():
        if ref not in fps: continue
        fp=fps[ref]
        fid=c.findtext('footprint'); value=c.findtext('value')
        check(fp.GetValue()==value,'value',ref=ref,expected=value,actual=fp.GetValue())
        check(fp.GetFPIDAsString()==fid,'footprint_id',ref=ref,expected=fid,actual=fp.GetFPIDAsString())
        expected_path=c.find('sheetpath').get('tstamps')+c.findtext('tstamps')
        check(fp.GetPath().AsString()==expected_path,'schematic_path',ref=ref,expected=expected_path,actual=fp.GetPath().AsString())
        check(fp.GetSheetname()==c.find("property[@name='Sheetname']").get('value'),'sheetname',ref=ref,actual=fp.GetSheetname())
        check(fp.GetSheetfile()==c.find("property[@name='Sheetfile']").get('value'),'sheetfile',ref=ref,actual=fp.GetSheetfile())
        expected_dnp=c.find("property[@name='dnp']") is not None
        check(fp.IsDNP()==expected_dnp,'dnp',ref=ref,expected=expected_dnp,actual=fp.IsDNP())
        if fp.IsDNP(): dnp.append(ref)
        fields=fp.GetFieldsText()
        for name in candidate_fields:
            e=c.findtext(f"fields/field[@name='{name}']",'') or ''
            check(fields.get(name,'')==e,'candidate_field',ref=ref,field=name,expected=e,actual=fields.get(name,''))
        if fid not in libs:
            lib,name=fid.split(':',1)
            folder=PROJECT/'ESPaperPlay.pretty' if lib=='ESPaperPlay' else Path('/usr/share/kicad/footprints')/(lib+'.pretty')
            path=folder/(name+'.kicad_mod')
            lf=P.FootprintLoad(str(folder),name)
            check(lf is not None,'library_load',footprint=fid)
            if lf is not None:
                libs[fid]=footprint_geometry(lf,copper_layers)
                libhashes[str(path)]=digest(path)
        if fid in libs:
            pads,zones=footprint_geometry(fp,copper_layers)
            lp,lz=libs[fid]
            check(pads==lp,'library_pad_geometry',ref=ref,removed=[str(x) for x in (lp-pads)],added=[str(x) for x in (pads-lp)])
            check(zones==lz,'library_rule_areas',ref=ref,expected=[str(x) for x in lz],actual=[str(x) for x in zones])
        rulecounts[ref]=len(fp.Zones())
        seen=set()
        for pad in fp.Pads():
            num=pad.GetNumber()
            if not num:
                if pad.GetNetCode()!=0: empty_copper.append(ref)
                continue
            numbered+=1; seen.add(num)
            key=(ref,num)
            expected=expected_nets.get(key)
            actual=pad.GetNetname()
            check(expected is not None,'extra_numbered_pad',ref=ref,pin=num,actual=actual)
            check(actual==expected,'pad_net',ref=ref,pin=num,expected=expected,actual=actual)
            netpad_counts[actual]+=1
        desired={pin for rr,pin in expected_nets if rr==ref}
        check(seen==desired,'numbered_pin_inventory',ref=ref,missing=sorted(desired-seen),extra=sorted(seen-desired))
        positions[ref]={'xy_mm':xy(fp.GetPosition()),'rotation_deg':fp.GetOrientationDegrees(),'bbox_mm':bbox(fp.GetBoundingBox(False,False))}
    check(not empty_copper,'unnumbered_pad_has_net',refs=empty_copper)
    check(numbered==804,'physical_numbered_pad_count',actual=numbered)
    expected_netnames={n.get('name') for n in r.findall('./nets/net')}
    actual_netnames={net.GetNetname() for code,net in b.GetNetsByNetcode().items() if code!=0}
    check(len(expected_netnames)==181,'baseline_net_count',actual=len(expected_netnames))
    invalid_route_nets=[{'kind':t.GetClass(),'net':t.GetNetname()} for t in route_items if t.GetNetname() not in expected_netnames or t.GetNetCode()==0]
    check(not invalid_route_nets,'invalid_route_net',items=invalid_route_nets)
    check(actual_netnames==expected_netnames,'net_inventory',missing=sorted(expected_netnames-actual_netnames),extra=sorted(actual_netnames-expected_netnames))
    for ref in ('H1','H2','H3','H4'):
        if ref not in fps: continue
        ps=list(fps[ref].Pads())
        check(bool(ps) and all(p.GetAttribute()==P.PAD_ATTRIB_NPTH and p.GetNetCode()==0 for p in ps),'mount_not_npth',ref=ref)
        check(all(p.GetDrillSizeX()>=P.FromMM(3.0) for p in ps),'mount_small_drill',ref=ref)
    poly=P.SHAPE_POLY_SET()
    valid_outline=b.GetBoardPolygonOutlines(poly,False)
    check(valid_outline,'board_outline_invalid')
    check(poly.OutlineCount()==1 and sum(poly.HoleCount(i) for i in range(poly.OutlineCount()))==0,'outline_topology',outlines=poly.OutlineCount(),holes=sum(poly.HoleCount(i) for i in range(poly.OutlineCount())))
    edge=b.GetBoardEdgesBoundingBox()
    contour_points=[poly.COutline(i).CPoint(j) for i in range(poly.OutlineCount()) for j in range(poly.COutline(i).PointCount())]
    extents=[min(p.x for p in contour_points),min(p.y for p in contour_points),max(p.x for p in contour_points),max(p.y for p in contour_points)] if contour_points else [0,0,0,0]
    outline_bbox=[mm(extents[0]),mm(extents[1]),mm(extents[2]-extents[0]),mm(extents[3]-extents[1])]
    check(abs(outline_bbox[2]-160)<=0.01 and abs(outline_bbox[3]-110)<=0.01,'board_dimensions',bbox_mm=outline_bbox)
    # Inner layers must be continuous filled GND planes, with no signal tracks.
    # A single filled outline is a connected copper region; holes/antipads remain legal.
    board_area_mm2=abs(poly.Area())/1e12
    plane_review={}
    for layer in (P.In1_Cu,P.In2_Cu):
        layer_name=b.GetLayerName(layer)
        zones=[z for z in b.Zones() if not z.GetIsRuleArea() and layer in set(z.GetLayerSet().Seq())]
        check(len(zones)==1,'inner_ground_zone_count',layer=layer_name,actual=len(zones))
        entries=[]
        for z in zones:
            has_fill=z.HasFilledPolysForLayer(layer)
            filled=z.GetFilledPolysList(layer) if has_fill else None
            outlines=filled.OutlineCount() if filled is not None else 0
            filled_area_mm2=abs(filled.Area())/1e12 if filled is not None else 0
            coverage=filled_area_mm2/board_area_mm2 if board_area_mm2 else 0
            entry={'net':z.GetNetname(),'is_filled':z.IsFilled(),'needs_refill':z.NeedRefill(),'filled_connected_regions':outlines,'filled_area_mm2':round(filled_area_mm2,4),'board_area_fraction':round(coverage,6)}
            entries.append(entry)
            check(z.GetNetname()=='GND','inner_zone_non_ground',layer=layer_name,net=z.GetNetname())
            check(has_fill and z.IsFilled() and not z.NeedRefill(),'inner_zone_unfilled_or_stale',layer=layer_name)
            check(outlines==1,'inner_ground_plane_disconnected',layer=layer_name,regions=outlines)
            check(coverage>=.85,'inner_ground_plane_insufficient_coverage',layer=layer_name,actual_fraction=coverage,minimum_fraction=.85)
        plane_review[layer_name]=entries
    drc_review={'checked':False,'note':'Run native KiCad DRC/parity separately; structural PASS does not certify zero unconnected routes.'}
    if a.drc:
        if check(a.drc.exists(),'missing_drc_report',path=str(a.drc)):
            drc=json.loads(a.drc.read_text())
            check({'violations','unconnected_items','schematic_parity','source','included_severities'} <= set(drc),'native_drc_report_fields_missing')
            check(Path(str(drc.get('source',''))).name==a.board.name,'native_drc_source_mismatch',reported_source=drc.get('source'),board=a.board.name)
            errors_in_drc=[v for v in drc.get('violations',[]) if v.get('severity')=='error']
            drc_review={'checked':True,'report':str(a.drc),'sha256':digest(a.drc),'errors':len(errors_in_drc),'warnings':sum(v.get('severity')=='warning' for v in drc.get('violations',[])),'unconnected_items':len(drc.get('unconnected_items',[])),'schematic_parity':len(drc.get('schematic_parity',[]))}
            check(not errors_in_drc,'native_drc_errors',count=len(errors_in_drc))
            check(not drc.get('unconnected_items',[]),'native_unconnected_items',count=drc_review['unconnected_items'])
            check(not drc.get('schematic_parity',[]),'native_schematic_parity',count=drc_review['schematic_parity'])
    check(rulecounts.get('U301')==1,'antenna_rule_count',actual=rulecounts.get('U301'))
    check(rulecounts.get('J701')==5,'sd_rule_count',actual=rulecounts.get('J701'))
    check(rulecounts.get('U803')==1,'mic_rule_count',actual=rulecounts.get('U803'))
    # Critical distances are pad-centre distances, recorded as review indicators.
    def pinpos(ref,num):
        return [p.GetPosition() for p in fps[ref].Pads() if p.GetNumber()==num]
    distances=[]
    pairs=[('C301','1','U301','2',5),('C302','1','U301','2',3),('C303','1','U301','3',5),('R503','2','U301','14',6),('R504','2','U301','13',6),('U501','1','J501','A6',7),('U501','2','J501','A7',7)]
    for ra,pa,rb,pb,limit in pairs:
        if ra not in fps or rb not in fps: continue
        aa=pinpos(ra,pa);bb=pinpos(rb,pb)
        if not aa or not bb: continue
        d=min(math.hypot(x.x-y.x,x.y-y.y)/1e6 for x in aa for y in bb)
        item={'from':ra+'.'+pa,'to':rb+'.'+pb,'pad_distance_mm':round(d,4),'review_target_mm':limit}
        distances.append(item)
        if d>limit: warnings.append(dict(kind='placement_distance_review',**item))
    out={'status':'PASS' if not errors else 'FAIL','stage':'r8 structural routing/electrical identity audit; see native_drc for separate completion checks','electrical_components_checked':len(comps),'mechanical_components_expected':4,'nets_checked':len(expected_netnames),'logical_pin_connections_checked':len(expected_nets),'physical_numbered_pads_checked':numbered,'candidate_fields_checked':list(candidate_fields),'dnp':sorted(dnp),'local_and_standard_footprints_checked':len(libs),'board_outline_bbox_mm':outline_bbox,'copper_layers':len(copper_layers),'tracks':len(traces),'vias':len(vias),'internal_layer_tracks':inner_tracks,'inner_ground_planes':plane_review,'native_drc':drc_review,'original_footprint_and_pad_uuid_identities_checked':len(identity['footprints']),'critical_footprint_rule_counts':{k:rulecounts.get(k) for k in ['U301','J701','U803']},'critical_pad_distances':distances,'errors':errors,'warnings':warnings,'inputs':{'netlist':str(a.netlist),'netlist_sha256':digest(a.netlist),'board':str(a.board),'board_sha256':digest(a.board),'checker_sha256':digest(__file__),'frozen_identity':str(a.identity),'frozen_identity_sha256':digest(a.identity) if a.identity.exists() else None},'footprint_library_sha256':libhashes}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in out.items() if k not in ('footprint_library_sha256','candidate_fields_checked')},ensure_ascii=False,indent=2))
    return 0 if not errors else 1

if __name__=='__main__': sys.exit(main())

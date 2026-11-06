#!/usr/bin/env python3
"""Independent placement-stage check: XML + installed/local libraries vs native PCB.
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
    ap.add_argument('--output',type=Path,default=PROJECT/'review-r7/independent-board-check.json')
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
    check(len(b.GetTracks())==0,'placement_must_not_claim_routing',tracks=len(b.GetTracks()))
    refs=defaultdict(list)
    for fp in b.GetFootprints(): refs[fp.GetReference()].append(fp)
    check(set(refs)==set(comps)|{'H1','H2','H3','H4'},'component_inventory',missing=sorted(set(comps)-set(refs)),unexpected=sorted(set(refs)-set(comps)-{'H1','H2','H3','H4'}))
    check(all(len(v)==1 for v in refs.values()),'duplicate_refs',duplicates={k:len(v) for k,v in refs.items() if len(v)!=1})
    fps={ref:arr[0] for ref,arr in refs.items() if len(arr)==1}
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
    expected_netnames={n.get('name') for n in r.findall('./nets/net')}
    actual_netnames={net.GetNetname() for code,net in b.GetNetsByNetcode().items() if code!=0}
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
    out={'status':'PASS' if not errors else 'FAIL','stage':'placement only; zero tracks required, routing DRC not represented as passed','electrical_components_checked':len(comps),'mechanical_components_expected':4,'nets_checked':len(expected_netnames),'logical_pin_connections_checked':len(expected_nets),'physical_numbered_pads_checked':numbered,'candidate_fields_checked':list(candidate_fields),'dnp':sorted(dnp),'local_and_standard_footprints_checked':len(libs),'board_outline_bbox_mm':outline_bbox,'copper_layers':len(copper_layers),'tracks':len(b.GetTracks()),'critical_footprint_rule_counts':{k:rulecounts.get(k) for k in ['U301','J701','U803']},'critical_pad_distances':distances,'errors':errors,'warnings':warnings,'inputs':{'netlist':str(a.netlist),'netlist_sha256':digest(a.netlist),'board':str(a.board),'board_sha256':digest(a.board),'checker_sha256':digest(__file__)},'footprint_library_sha256':libhashes}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in out.items() if k not in ('footprint_library_sha256','candidate_fields_checked')},ensure_ascii=False,indent=2))
    return 0 if not errors else 1

if __name__=='__main__': sys.exit(main())

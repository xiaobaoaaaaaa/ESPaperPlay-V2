#!/usr/bin/env python3
"""Read-only U101/U203/U802/U301/U803 native final-layout Gerber checks.

Requires Gerbonara/Shapely; --zip and --state are required, --report optional.
This is layout/footprint CAM verification, not routing signoff or reflow qualification.
"""
import argparse
import json
import math
import tempfile
from pathlib import Path
from native_cam_geometry import *

HERE=Path(__file__).resolve().parent


def json_finite(value):
    if isinstance(value,float) and not math.isfinite(value):return None
    if isinstance(value,dict):return {k:json_finite(v) for k,v in value.items()}
    if isinstance(value,list):return [json_finite(v) for v in value]
    return value


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--zip',type=Path,required=True);ap.add_argument('--state',type=Path,required=True)
    ap.add_argument('--report',type=Path,default=HERE/'native-special-cam-check.json')
    args=ap.parse_args()
    if not args.zip.exists() or not args.state.exists():
        print(json.dumps({'status':'WAITING_FOR_CAM_AND_MATCHING_NATIVE_POSES','zip_exists':args.zip.exists(),'state_exists':args.state.exists()}));return 2
    hashes={str(args.zip):sha(args.zip),str(args.state):sha(args.state)}
    pp=poses(args.state);checks={};routing={};measurement={}
    plan101=json.loads((HERE/'u101-native-fix.json').read_text())
    plan_other=json.loads((HERE/'u802-u203-native-fix.json').read_text())['parts']
    plan_mic=json.loads((HERE/'u301-u803-native-fix.json').read_text())
    def check(name,ok,**detail):checks[name]={'pass':bool(ok),**detail}
    def checkdetail(name,d):checks[name]=d
    def drills_at(cam,ref,centers,roi,diameter,plated):
        rows=cam.local_drills(pp[ref],roi);unused=list(rows);errors=[]
        for p in centers:
            near=[d for d in unused if Point(d['center_local_mm']).distance(Point(p))<.0001]
            if len(near)!=1:errors.append({'expected_center_mm':p,'matches':len(near)});continue
            found=near[0];unused.remove(found)
            if found['plated']!=plated or abs(found['diameter_measured_mm']-diameter)>.0001:errors.append(serial_drills([found])[0])
        check(ref+'_drills',not errors and not unused and len(rows)==len(centers),actual=serial_drills(rows),expected_count=len(centers),unmatched=len(unused),errors=errors)
        return rows
    with tempfile.TemporaryDirectory(prefix='native-cam-read-') as td:
        cam=Cam(args.zip,td)
        # U101 independently expected TI perimeter + EP rounded geometry.
        ref='U101';p=pp[ref];roi=box(-2.2,-2.2,2.2,2.2)
        g={};r={}
        for L in LAYERS:g[L],r[L]=cam.roi(L,p,roi)
        actualpads={}
        for spec in [*plan101['peripheral_pads'],plan101['exposed_pad']]:
            xy=spec['center_local_mm'];wh=spec['size_xy_mm'];expected=rounded_rect(*xy,*wh,spec['corner_radius_mm'])
            detail,actual=match_objects(r['F.Cu'],expected);checkdetail(ref+'_pad_'+spec['number'],detail);actualpads[spec['number']]=actual
        ep=rounded_rect(0,0,1.68,1.68,.05)
        cpaste=g['F.Paste'].intersection(box(-.9,-.9,.9,.9));wantpaste=Polygon(plan101['paste']['central_vertices_local_mm'])
        checkdetail('U101_central_paste_exact',exact_union_metrics(cpaste,wantpaste))
        check('U101_central_paste_one_region_no_island',len(polygons(cpaste))==1 and sum(len(q.interiors) for q in polygons(cpaste))==0)
        check('U101_bottom_paste_empty',g['B.Paste'].area<1e-9,area_mm2=g['B.Paste'].area)
        for spec in plan101['peripheral_pads']:
            checkdetail('U101_peripheral_paste_'+spec['number'],match_objects(r['F.Paste'],rounded_rect(*spec['center_local_mm'],*spec['size_xy_mm'],.05))[0])
        centers=[v['center_local_mm'] for v in plan101['thermal_vias']]
        for i,c in enumerate(centers,1):
            checkdetail('U101_via_land_'+str(i),match_objects(r['F.Cu'],Point(c).buffer(.3,quad_segs=512))[0])
        ds=drills_at(cam,ref,centers,box(-1,-1,1,1),.3,True)
        hole=unary_union([d['geom'] for d in ds]);sec=1/math.cos(math.pi/(4*512))
        worst=unary_union([box(x-.105,y-.105,x+.105,y+.105).buffer(.215*sec,quad_segs=512) for x,y in centers])
        grown=cpaste.buffer(.02*sec,quad_segs=512);gap=grown.distance(worst)
        check('U101_continuous_paste_hole_tolerance',gap>=.0199 and grown.intersection(worst).area<1e-9,gap_mm=gap,overlap_mm2=grown.intersection(worst).area,analysis_target_mm=.02,numeric_comparison_allowance_mm=.0001)
        env=extrude(extrude(grown,.03,0),0,.03)
        check('U101_continuous_print_within_EP',env.difference(ep).area<1e-6,outside_mm2=env.difference(ep).area)
        masks=polygons(g['F.Mask']);central=next((q for q in masks if q.covers(Point(0,0))),GeometryCollection())
        bridges=[]
        for spec in plan101['peripheral_pads']:
            m=next((q for q in masks if q.covers(Point(spec['center_local_mm']))),GeometryCollection())
            bridges.append(central.distance(m) if not central.is_empty and not m.is_empty else -1)
        check('U101_top_mask_bridge',min(bridges)>=.1-.00003,min_mm=min(bridges),all_gaps_mm=bridges)
        top_expected=ep.buffer(.05,quad_segs=512).union(unary_union([Point(c).buffer(.32,quad_segs=512) for c in centers]))
        checkdetail('U101_top_central_mask_exact',exact_union_metrics(central,top_expected))
        bot_expected=unary_union([Point(c).buffer(.35,quad_segs=512) for c in centers])
        checkdetail('U101_bottom_via_mask_exact',exact_union_metrics(g['B.Mask'].intersection(box(-1,-1,1,1)),bot_expected))
        for L in ['F.Mask','B.Mask']:check('U101_open_holes_'+L,g[L].buffer(GEOMETRY_TOL).covers(hole),uncovered_mm2=hole.difference(g[L]).area)
        copper=polygons(g['F.Cu']);epcomp=next((q for q in copper if q.covers(Point(0,0))),GeometryCollection())
        foreign=[actualpads[q['number']] for q in plan101['peripheral_pads'] if q['net']!='GND' and not actualpads[q['number']].is_empty]
        mingap=min((epcomp.distance(q) for q in foreign),default=-1)
        check('U101_central_copper_to_foreign_pad_min015',mingap>=.15-.00003,min_mm=mingap)
        check('U101_EP_four_via_lands_connected',not epcomp.is_empty and all(epcomp.buffer(GEOMETRY_TOL).covers(Point(c).buffer(.3,quad_segs=256)) for c in centers))
        routing['U101_VSS8_connected_in_current_CAM']=not epcomp.is_empty and epcomp.covers(Point(.75,-1.4))
        measurement['U101']={'central_paste_area_mm2':cpaste.area,'EP_coverage_percent':cpaste.area/ep.area*100,'nominal_paste_hole_gap_mm':cpaste.distance(hole),'central_paste_area_ratio_at_010mm':cpaste.area/(cpaste.length*.1) if cpaste.length else None}
        # U802/U203: each actual pad flash + independent EP window union.
        for ref,spec in plan_other.items():
            p=pp[ref];roi=box(-3,-3,3,3);cu,cuobj=cam.roi('F.Cu',p,roi);paste,pasteobj=cam.roi('F.Paste',p,roi)
            epnum=str(max(int(q['number']) for q in spec['pad_corrections']));epgeom=None
            for pad in spec['pad_corrections']:
                t=pad['target'];want=rounded_rect(*t['center_mm'],t['width_mm'],t['height_mm'])
                checkdetail(ref+'_pad_'+pad['number'],match_objects(cuobj,want)[0])
                if pad['number']==epnum:epgeom=want
                else:checkdetail(ref+'_peripheral_paste_'+pad['number'],match_objects(pasteobj,want)[0])
            windows=unary_union([rounded_rect(*w['center_mm'],w['width_mm'],w['height_mm']) for w in spec['ep_paste_windows']])
            central=paste.intersection(epgeom.buffer(.02))
            checkdetail(ref+'_EP_paste_windows_exact',exact_union_metrics(central,windows))
            check(ref+'_EP_window_count',len(polygons(central))==len(spec['ep_paste_windows']),actual=len(polygons(central)),expected=len(spec['ep_paste_windows']))
            centers=[v['center_mm'] for v in spec['thermal_vias']]
            for i,c in enumerate(centers,1):
                checkdetail(ref+'_via_land_'+str(i),match_objects(cuobj,Point(c).buffer(.3,quad_segs=512))[0])
            ds=drills_at(cam,ref,centers,roi,.3,True)
            check(ref+'_paste_avoids_vias',paste.intersection(unary_union([d['geom'] for d in ds])).area<1e-9)
            measurement[ref]={'EP_paste_area_mm2':central.area,'coverage_percent':central.area/epgeom.area*100}
        # U301 no central paste; twelve ordinary thermal holes and solid EP.
        ref='U301';spec=plan_mic[ref];cx,cy=spec['central_copper']['center_mm'];ep=rounded_rect(cx,cy,3.9,3.9);roi=ep.buffer(.2)
        cu,cuobj=cam.roi('F.Cu',pp[ref],roi);paste,_=cam.roi('F.Paste',pp[ref],roi)
        check('U301_central_zero_paste',paste.area<1e-9,area_mm2=paste.area)
        check('U301_continuous_central_copper',ep.difference(cu.buffer(GEOMETRY_TOL)).area<1e-8 and len(polygons(cu))==1,missing_mm2=ep.difference(cu).area,components=len(polygons(cu)))
        drills_at(cam,ref,spec['thermal_vias']['centers_mm'],roi,.3,True)
        for i,c in enumerate(spec['thermal_vias']['centers_mm'],1):
            checkdetail('U301_via_land_'+str(i),match_objects(cuobj,Point(c).buffer(.3,quad_segs=512))[0])
        # U803 sealing land: continuous copper ring, four paste quadrants, unique NPTH.
        ref='U803';spec=plan_mic[ref];p=pp[ref];cx,cy=spec['port_center_mm'];roi=box(-1.6,cy-1.0,1.6,2)
        cu,cuobj=cam.roi('F.Cu',p,roi);paste,pasteobj=cam.roi('F.Paste',p,roi)
        disk=Point(cx,cy);ring=disk.buffer(.825,quad_segs=512).difference(disk.buffer(.525,quad_segs=512))
        ringroi=disk.buffer(.9,quad_segs=512);actualring=cu.intersection(ringroi)
        checkdetail('U803_continuous_ring_dimensions',exact_union_metrics(actualring,ring))
        check('U803_copper_ring_single_component_and_hole',len(polygons(actualring))==1 and sum(len(q.interiors) for q in polygons(actualring))==1,components=len(polygons(actualring)),holes=sum(len(q.interiors) for q in polygons(actualring)))
        cuts=unary_union([box(cx-.075,cy-1,cx+.075,cy+1),box(cx-1,cy-.075,cx+1,cy+.075)])
        expectedpaste=disk.buffer(.8025,quad_segs=512).difference(disk.buffer(.5475,quad_segs=512)).difference(cuts)
        ringpaste=paste.intersection(ringroi)
        checkdetail('U803_four_ring_paste_shapes_exact',exact_union_metrics(ringpaste,expectedpaste))
        check('U803_four_paste_segments',len(polygons(ringpaste))==4,components=len(polygons(ringpaste)))
        check('U803_ten_total_paste_apertures',len(polygons(paste))==10,components=len(polygons(paste)))
        for q in spec['existing']['signals']:
            xy=q['center_mm'];checkdetail('U803_signal_copper_'+q['number'],match_objects(cuobj,rounded_rect(*xy,.6,.4))[0])
            checkdetail('U803_signal_paste_'+q['number'],match_objects(pasteobj,rounded_rect(*xy,.51,.34))[0])
        ds=drills_at(cam,ref,[[cx,cy]],roi,.6,False)
        check('U803_paste_clear_sound_hole',paste.intersection(unary_union([d['geom'] for d in ds])).area<1e-9)
        for L in ['F.Cu','In1.Cu','In2.Cu','B.Cu']:
            gg,_=cam.roi(L,p,ringroi)
            check('U803_sound_channel_clear_'+L,gg.intersection(disk.buffer(.5-GEOMETRY_TOL,quad_segs=512)).area<1e-9,intersection_mm2=gg.intersection(disk.buffer(.5-GEOMETRY_TOL,quad_segs=512)).area)
        measurement['U803']={'ring_paste_area_mm2':ringpaste.area,'ring_coverage_percent':ringpaste.area/ring.area*100}
        check('inputs_byte_unchanged',all(sha(Path(k))==v for k,v in hashes.items()))
        errors=[k for k,v in checks.items() if not v['pass']]
        result={'status':'PASS_NATIVE_SPECIAL_FOOTPRINT_LAYOUT_CAM' if not errors else 'FAIL_NATIVE_SPECIAL_FOOTPRINT_LAYOUT_CAM',
                'scope':'Actual native Gerber/Excellon geometry for five corrected footprint regions; not routed connectivity or manufacture/assembly qualification.',
                'input_hashes':hashes,'script_sha256':sha(Path(__file__)),'helper_sha256':sha(Path(__file__).with_name('native_cam_geometry.py')),
                'coordinate_frame':'Native/Gerber +X right, +Y up, mm; inverse actual component rotation/translation. No KiCad geometry or Y inversion.',
                'poses':{ref:pp[ref].detail() for ref in ['U101','U203','U802','U301','U803']},
                'curve_error_mm':ARC_ERROR,'comparison_tolerance_mm':GEOMETRY_TOL,'checks':checks,'errors':errors,'measurements':measurement,
                'routing_observations_not_layout_release_checks':routing,'CAM_files':cam.files,'CAM_layer_stats':cam.stats,
                'Excellon_in_memory_normalization':cam.drill_normalizations,
                'duplicate_Excellon_subsidiary_views':cam.duplicate_drill_views,
                'limitations':['No claim of completed routing, GND plane connectivity, board-wide DRC or complete manufacturing release.',
                               'U101 .03mm manual print registration, .02mm aperture-edge error and conservative .43mm/.075mm-hole scenario remain conditional assumptions; annular-ring and mask registration capability not established.',
                               'Open-via wicking, paste transfer, reflow voids, joint/thermal performance and microphone acoustic seal require first-board validation.']}
    result=json_finite(result)
    args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'status':result['status'],'checks':len(checks),'errors':errors,'report':str(args.report)},ensure_ascii=False,indent=2))
    return bool(errors)


if __name__=='__main__':raise SystemExit(main())

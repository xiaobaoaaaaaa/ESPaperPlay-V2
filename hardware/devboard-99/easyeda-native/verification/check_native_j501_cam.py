#!/usr/bin/env python3
"""Read-only, routing-aware J501 GCT USB4105-GF-A native CAM verification.

Uses frozen independent land/slot/paste targets, actual source-bound pad nets,
CAM primitive matching plus final-polarity copper coverage, and exact attribution
of additional routed holes. No KiCad geometry, live API, or ignored build imports.
"""
import argparse,json,math,tempfile
from pathlib import Path
from shapely.geometry import Point,LineString,box
from shapely.ops import unary_union
from native_cam_geometry import (Cam,poses,sha,polygons,exact_union_metrics,
                                 match_objects,GerberFile,MM,GEOMETRY_TOL)
from native_source_geometry import native_polygon
from native_routed_cam_context import RoutedContext
HERE=Path(__file__).resolve().parent
ROI=box(-5,-5.2,5,3.3)
COPPER={1:'F.Cu',2:'B.Cu',15:'In1.Cu',16:'In2.Cu'}

def oblong(x,y,width,height):
 return LineString([(x,y-(height-width)/2),(x,y+(height-width)/2)]).buffer(width/2,quad_segs=2048)

def targets(plan):
 pads={};slots={}
 for p in plan['pads']:
  x,y=p['x_mm'],p['y_mm'];d=p.get('defaultPad')
  if d:
   w,h=p['nominal_size_mm']
   g=native_polygon(d['path'])if d['padType']=='POLYGON'else box(x-w/2,y-h/2,x+w/2,y+h/2)
  else:
   g=oblong(x,y,*p['copper_size_mm']);slots[p['num']]=oblong(x,y,*p['PTH_slot_mm'])
  pads[p['num']]=g
 return pads,slots,[native_polygon(p['path'])for p in plan['paste']]

def verify_features(plan,pads,slots,paste_targets,data):
 """Pure geometry/net checks; also exercised with real-CAM negative mutations."""
 checks={};actualpads={}
 def add(name,passed,**details):checks[name]={'pass':bool(passed),**details}
 pin_nets=data['pin_nets'];wanted=plan['expected_pin_nets']
 add('J501_20_pin_names_and_correct_nets',pin_nets==wanted,expected=wanted,actual=pin_nets)
 for num,g in pads.items():
  for layer in (list(COPPER.values())if num in slots else ['F.Cu']):
   detail,actual=match_objects(data['records'][layer],g);checks[f'J501_{num}_{layer}_pad_primitive']=detail
   # A later clear-polarity aperture must not erase a matched flash/region.
   missing=g.difference(data['geometry'][layer]).area
   add(f'J501_{num}_{layer}_final_copper_retained',missing<=g.length*GEOMETRY_TOL,missing_area_mm2=missing)
   if layer=='F.Cu':actualpads[num]=actual
 expected=unary_union(list(pads.values()));actual_lands=unary_union(list(actualpads.values()))
 mask=data['geometry']['F.Mask'];mm=exact_union_metrics(mask,expected.buffer(.025,quad_segs=2048))
 mm['ideal_offset_exact_match']=mm['pass'];mm['acceptance']='20um <= opening margin <=30um, target25um; 16 physical opening components'
 # Compare to footprint lands, not the subsequently connected copper traces.
 mm['minimum_20um_envelope_missing_area_mm2']=actual_lands.buffer(.020,quad_segs=128).difference(mask).area
 mm['maximum_30um_envelope_excess_area_mm2']=mask.difference(actual_lands.buffer(.030,quad_segs=128)).area
 mm['pass']=mask.covers(actual_lands)and len(polygons(mask))==16 and mm['minimum_20um_envelope_missing_area_mm2']<1e-9 and mm['maximum_30um_envelope_excess_area_mm2']<1e-9
 checks['J501_F_Mask']=mm
 bottom_mask=data['geometry']['B.Mask'];bottom_lands=unary_union([actualpads[n]for n in slots])
 bm=exact_union_metrics(bottom_mask,bottom_lands.buffer(.025,quad_segs=2048));bm['ideal_offset_exact_match']=bm['pass']
 bm['pass']=bottom_mask.covers(bottom_lands)and len(polygons(bottom_mask))==4 and bottom_lands.buffer(.020,quad_segs=128).difference(bottom_mask).area<1e-9 and bottom_mask.difference(bottom_lands.buffer(.030,quad_segs=128)).area<1e-9
 checks['J501_B_Mask_four_shell_openings']=bm
 pm=exact_union_metrics(data['geometry']['F.Paste'],unary_union(paste_targets));pm['pass'] &= pm['components']==12;pm['expected_physical_apertures']=12
 checks['J501_F_Paste_12_exact_windows_no_shell_paste']=pm
 checks['J501_B_Paste_empty']={'pass':data['geometry']['B.Paste'].is_empty}
 drills=data['drills'];matched=[]
 desired=[(f'NPTH_{i+1}',Point(p).buffer(plan['npth']['diameter_mm']/2,quad_segs=2048),False)for i,p in enumerate(plan['npth']['centres_mm'])]+[(f'shell_{n}',g,True)for n,g in slots.items()]
 for name,g,plated in desired:
  near=[d for d in drills if d['geom'].centroid.distance(g.centroid)<.0001]
  if len(near)!=1:add('J501_'+name+'_drill',False,reason='Expected unique actual drill at nominal center',matches=len(near));continue
  d=near[0];matched.append(d);m=exact_union_metrics(d['geom'],g);m['pass'] &= d['plated']==plated;m['actual_plated']=d['plated'];m['expected_plated']=plated
  if plated:
   num=name.removeprefix('shell_');m['nominal_land_minimum_measured_annulus_mm']=actualpads[num].boundary.distance(d['geom'].boundary)
   m['pass'] &= m['nominal_land_minimum_measured_annulus_mm']>.1999
  checks['J501_'+name+'_drill']=m
 for l in COPPER.values():
  for name,g,plated in desired:
   if plated:continue
   # Actual matched holes, never substitute nominal shape for bad CAM drill.
   near=[d for d in matched if not d['plated']and d['geom'].centroid.distance(g.centroid)<.0001]
   gap=data['geometry'][l].distance(near[0]['geom'])if len(near)==1 else -1
   add('J501_'+l+'_'+name+'_global_clearance',gap>=.30,actual_gap_mm=gap,minimum_mm=.30,rule='Existing project global NPTH rule; the .31mm target belongs to the footprint heel relief')
   if len(near)==1:
    localgap=actual_lands.distance(near[0]['geom'])
    pastegap=data['geometry']['F.Paste'].distance(near[0]['geom'])
    add('J501_'+name+'_footprint_land_relief',localgap>=.3099,actual_gap_mm=localgap,minimum_mm=.3099,design_mm=.31)
    add('J501_'+name+'_footprint_paste_relief',pastegap>=.3099,actual_gap_mm=pastegap,minimum_mm=.3099,design_mm=.31)
 # Explicit source conductors provide net labels to actual local copper
 # polygons. This catches a wrong-net incoming trace, including a same-shape
 # source/state change that an independent expected pin map alone cannot see.
 for layer,rows in data['source_items'].items():
  for index,g in enumerate(polygons(data['geometry'][layer])):
   nets=set()
   for item in rows:
    if g.intersection(item['g']).area>1e-8:nets.add(item['net'])
   add(f'J501_{layer}_local_copper_{index}_no_mixed_net',len(nets)<=1,nets=sorted(nets))
 return checks

def negative_tests(plan,pads,slots,paste_targets,data):
 """Mutate only in-memory test observations; never CAD/source/CAM files."""
 base=verify_features(plan,pads,slots,paste_targets,data)
 assert all(v['pass']for v in base.values()),'Negative tests require passing actual CAM features'
 tests=[]
 def test(name,edit,required):
  altered={**data,'pin_nets':dict(data['pin_nets']),'geometry':dict(data['geometry']),
           'records':{l:list(rs)for l,rs in data['records'].items()},'drills':[dict(d)for d in data['drills']],
           'source_items':{l:list(rs)for l,rs in data['source_items'].items()}}
  edit(altered);result=verify_features(plan,pads,slots,paste_targets,altered)
  failed=[k for k,v in result.items()if not v['pass']]
  assert any(required in k for k in failed),(name,failed)
  tests.append({'case':name,'pass':True,'detected_checks':failed})
 n='A6';obj=base[f'J501_{n}_F.Cu_pad_primitive']['CAM_object']
 test('Missing data pad primitive despite neighboring routed copper',lambda d:d['records'].__setitem__('F.Cu',[r for r in d['records']['F.Cu']if r['index']!=obj]),f'{n}_F.Cu_pad_primitive')
 test('Clear polarity erases part of previously matched copper pad',lambda d:d['geometry'].__setitem__('F.Cu',d['geometry']['F.Cu'].difference(pads[n].buffer(-.04))),f'{n}_F.Cu_final_copper_retained')
 test('Missing stencil window',lambda d:d['geometry'].__setitem__('F.Paste',d['geometry']['F.Paste'].difference(paste_targets[0].buffer(.001))),'F_Paste')
 test('Unexpected shell paste',lambda d:d['geometry'].__setitem__('F.Paste',d['geometry']['F.Paste'].union(pads['1'])),'F_Paste')
 test('Missing mask opening',lambda d:d['geometry'].__setitem__('F.Mask',d['geometry']['F.Mask'].difference(pads[n])),'F_Mask')
 def remove_hole(d,g):d['drills']=[r for r in d['drills']if r['geom'].centroid.distance(g.centroid)>.0001]
 test('Missing plated slot',lambda d:remove_hole(d,slots['1']),'shell_1_drill')
 test('Missing mechanical NPTH',lambda d:remove_hole(d,Point(plan['npth']['centres_mm'][0])),'NPTH_1_drill')
 def change_plating(d):
  row=next(r for r in d['drills']if r['geom'].centroid.distance(slots['1'].centroid)<.0001);row['plated']=False
 test('Plated slot incorrectly marked nonplated',change_plating,'shell_1_drill')
 test('Wrong native pin network',lambda d:d['pin_nets'].__setitem__('A6','USB_DM_PORT'),'20_pin_names_and_correct_nets')
 test('NC SBU incorrectly assigned a network',lambda d:d['pin_nets'].__setitem__('A8','GND'),'20_pin_names_and_correct_nets')
 test('Incoming copper carries wrong source net',lambda d:d['source_items']['F.Cu'].append({'g':pads[n],'net':'WRONG_NET'}),'no_mixed_net')
 test('Actual CAM copper bridge between different data nets',lambda d:d['geometry'].__setitem__('F.Cu',d['geometry']['F.Cu'].union(LineString([pads['A6'].centroid,pads['A7'].centroid]).buffer(.05))),'no_mixed_net')
 test('Inner-plane NPTH relief missing',lambda d:d['geometry'].__setitem__('In1.Cu',d['geometry']['In1.Cu'].union(Point(plan['npth']['centres_mm'][0]).buffer(.5))),'In1.Cu_NPTH_1_global_clearance')
 return tests

def run(args):
 target=HERE/'j501-cam-target.json';plan=json.loads(target.read_text());pads,slots,paste_targets=targets(plan)
 context=RoutedContext(args.source,args.state,args.archive);pose=poses(args.state)['J501'];c=next(c for c in context.state if c['ref']=='J501')
 with tempfile.TemporaryDirectory(prefix='native-j501-cam-')as td:
  cam=Cam(args.zip,td);geometries={};records={}
  for layer in [*COPPER.values(),'F.Mask','B.Mask','F.Paste','B.Paste']:geometries[layer],records[layer]=cam.roi(layer,pose,ROI)
  rows=cam.local_drills(pose,ROI);source_items={}
  for l,name in COPPER.items():
   source_items[name]=[{'g':pose.local(i['g']).intersection(ROI),'net':i.get('net')or'NC_'+i['id']}for i in context.items if l in i['layers']and i['g'].intersects(pose.world(ROI))]
  data={'pin_nets':{p['n']:p.get('net','')for p in c['pins']},'geometry':geometries,'records':records,'drills':rows,'source_items':source_items}
  checks=verify_features(plan,pads,slots,paste_targets,data)
  # Existing shell slots/NPTH are planned features; additional vias must match
  # the exact native source and retain the established no-new-via-in-pad rule.
  centers=plan['npth']['centres_mm']+[[g.centroid.x,g.centroid.y]for g in slots.values()]
  attribution=context.match_roi_drills(pose,ROI,rows,centers)
  checks['J501_every_ROI_drill_matches_exact_native_source']=attribution
  outlines=[Path(td)/name for name in cam.files if Path(name).suffix.upper()=='.GKO'];segments=[]
  for path in outlines:
   for obj in GerberFile.open(path).objects:
    for p in obj.to_primitives(MM):
     if all(hasattr(p,k)for k in['x1','y1','x2','y2']):segments.append([p.x1,p.y1,p.x2,p.y2])
  front=[pose.world(Point(x,plan['body_mm']['front_edge_y']))for x in[-4.47,4.47]]
  error=max(abs(p.y)for p in front)
  checks['J501_front_edge_matches_99mm_board_datum']={'pass':len(outlines)==1 and error<.00006 and[0.,0.,99.,0.]in segments,'maximum_edge_y_error_mm':error,'outline_segments_mm':segments}
  negative=negative_tests(plan,pads,slots,paste_targets,data)if args.negative_tests else[]
  failures=[k for k,v in checks.items()if not v['pass']]
  return {'status':'PASS_J501_ROUTED_CAM'if not failures else'FAIL_J501_ROUTED_CAM','inputs':{str(p):sha(p)for p in[args.source,args.state,args.archive,args.zip,target]},'pose':pose.detail(),'checks':checks,'failures':failures,'negative_tests':negative,'CAM_files':cam.files,
   'NPTH_clearance_rule_basis':plan['NPTH_clearance_rules'],'scope':'Frozen GCT/approved-relief targets:20 native pads/16 joined lands,12 paste windows,2 NPTH and4 plated shell slots, all-layer NPTH clearance, source-authoritative additional routed drills, independent pin nets and local actual-copper mixed-net detection. Additional routed copper does not replace required pad primitives.',
   'limits':['This local check does not prove global net connectivity, source/SCH equivalence, full-board clearance or continuous high-speed reference planes; run corresponding independent checks.','Curve/tessellation tolerances unchanged from the historical J501 CAM review. Source hole attribution uses exact library geometry, not known-inaccurate API hole sizes.','Copper/paste heel relief is the documented manufacturing adaptation; physical sample fit, soldering, plating and circuit operation remain untested. No fabrication release.']}

def json_finite(value):
 if isinstance(value,float)and not math.isfinite(value):return None
 if isinstance(value,dict):return {k:json_finite(v)for k,v in value.items()}
 if isinstance(value,list):return [json_finite(v)for v in value]
 return value

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for key in['source','state','archive','zip','output']:p.add_argument('--'+key,type=Path,required=True)
 p.add_argument('--negative-tests',action='store_true');a=p.parse_args();r=run(a);a.output.write_text(json.dumps(json_finite(r),indent=2,allow_nan=False)+'\n');print(r['status'],len(r['checks']),'checks',len(r['negative_tests']),'negative tests',r['failures']);return bool(r['failures'])
if __name__=='__main__':raise SystemExit(main())

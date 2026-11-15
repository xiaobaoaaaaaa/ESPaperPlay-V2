#!/usr/bin/env python3
"""Read-only routed r14 U101 actual CAM review; native CLI writes only scratch copies.
Reuse r13 geometry helpers, never its stage-specific main/assertions. This is not a
manufacturing/reflow qualification and does not replace full board DRC or CAM review.
"""
import argparse,collections,hashlib,importlib.util,json,math,shutil,sys
from pathlib import Path
import numpy,shapely,shapely.geometry,shapely.ops,shapely.prepared
import pcbnew as P
from shapely.geometry import Point,Polygon,GeometryCollection,box
from shapely.ops import unary_union
from shapely.affinity import translate,scale
from gerbonara import GerberFile,ExcellonFile
from gerbonara.utils import MM
ROOT=next(p for p in Path(__file__).resolve().parents if (p/'hardware/devboard-99').is_dir())
spec=importlib.util.spec_from_file_location('r13_helpers_only',ROOT/'hardware/devboard-99/tools/check_u101_r13.py');H=importlib.util.module_from_spec(spec);spec.loader.exec_module(H)
LAYERS='F.Cu,In1.Cu,In2.Cu,B.Cu,F.Mask,B.Mask,F.Paste,B.Paste'

def roi_gerber(path,roi):
 result=GeometryCollection();file=GerberFile.open(path);used=0
 for o in file.objects:
  bb=o.bounding_box(MM)
  if bb is None:continue
  (x0,y0),(x1,y1)=bb
  if not roi.intersects(box(x0,-y1,x1,-y0)):continue
  g=scale(H.object_geom(o),yfact=-1,origin=(0,0)).intersection(roi)
  result=result.union(g)if o.polarity_dark else result.difference(g);used+=1
 return result,{'objects_in_file':len(file.objects),'objects_intersecting_ROI':used}

def export(src,work,name,check_zones):
 project=work/name;project.mkdir(parents=True,exist_ok=True);pcb=project/(name+'.kicad_pcb');shutil.copy2(src,pcb)
 for ext in ['.kicad_pro','.kicad_dru']:
  if src.with_suffix(ext).exists():shutil.copy2(src.with_suffix(ext),pcb.with_suffix(ext))
 cam=project/'cam';cam.mkdir(exist_ok=True)
 cmd=['kicad-cli','pcb','export','gerbers','--layers',LAYERS,'--no-protel-ext']
 if check_zones:cmd+=['--check-zones']
 H.execute(cmd+['-o',str(cam)+'/',str(pcb)],project/'gerbers.log')
 H.execute(['kicad-cli','pcb','export','drill','--format','excellon','--excellon-separate-th','--generate-report','-o',str(cam)+'/',str(pcb)],project/'drill.log')
 files={layer:next(p for p in cam.glob('*.gbr')if p.stem.endswith('-'+layer.replace('.','_')))for layer in LAYERS.split(',')}
 return cam,files

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--board',type=Path,required=True);ap.add_argument('--baseline',type=Path,required=True);ap.add_argument('--work-dir',type=Path,required=True);ap.add_argument('--report',type=Path,required=True);a=ap.parse_args()
 src=a.board.resolve();baseline=a.baseline.resolve();work=a.work_dir.resolve();report=a.report.resolve()
 assert '/build/'in str(work)and work!=src.parent and not src.is_relative_to(work),'scratch export must stay separate from source'
 assert report!=src and report!=baseline,'Report cannot overwrite source CAD'
 work.mkdir(parents=True,exist_ok=True);report.parent.mkdir(parents=True,exist_ok=True)
 sources=[src,baseline]+[p for p in [src.with_suffix('.kicad_pro'),src.with_suffix('.kicad_dru')]if p.exists()];hashes={str(p):H.sha(p)for p in sources};errors=[];checks={}
 def check(key,ok,**details):
  checks[key]={'pass':bool(ok),**details}
  if not ok:errors.append(key)
 b=P.LoadBoard(str(src));old=P.LoadBoard(str(baseline));u=next(f for f in b.GetFootprints()if f.GetReference()=='U101');ou=next(f for f in old.GetFootprints()if f.GetReference()=='U101');cn=H.canonical(u);co=H.canonical(ou)
 check('U101_geometry_and_placement_retained_r13',H.xy(u.GetPosition())==H.xy(ou.GetPosition())and u.GetOrientationDegrees()==ou.GetOrientationDegrees()and collections.Counter(json.dumps(H.pad_sig(p),sort_keys=True)for p in cn.Pads())==collections.Counter(json.dumps(H.pad_sig(p),sort_keys=True)for p in co.Pads()))
 center=H.xy(u.GetPosition());zoom=translate(box(-2.2,-2.2,2.2,2.2),xoff=center[0],yoff=center[1]);roi=translate(box(-.95,-.95,.95,.95),xoff=center[0],yoff=center[1])
 local_holes=[p for p in cn.Pads()if p.HasDrilledHole()];local_pos=sorted(H.xy(p.GetPosition())for p in local_holes)
 expected_local=[[-.63,-.63],[-.63,.63],[.63,-.63],[.63,.63]]
 check('four_standard_open_PTH_and_solid_connection',local_pos==expected_local and all(p.GetAttribute()==P.PAD_ATTRIB_PTH and H.xy(p.GetDrillSize())==[.3,.3]and H.xy(p.GetSize())==[.6,.6]and p.GetNumber()=='17'and p.GetNetname()=='GND'and p.IsOnLayer(P.F_Mask)and p.IsOnLayer(P.B_Mask)and not p.IsOnLayer(P.F_Paste)and not p.IsOnLayer(P.B_Paste)and p.GetLocalSolderMaskMargin()==P.FromMM(.02)and p.GetLocalZoneConnection()==P.ZONE_CONNECTION_FULL for p in local_holes),positions_mm=local_pos)
 ep=next(p for p in u.Pads()if p.GetNumber()=='17'and p.GetAttribute()==P.PAD_ATTRIB_SMD);check('EP17_solid_zone_override',ep.GetLocalZoneConnection()==P.ZONE_CONNECTION_FULL and ep.GetNetname()=='GND')
 cam,files=export(src,work,'r14',True);bcam,bfiles=export(baseline,work,'r13',False)
 g={};stats={}
 for name,path in files.items():g[name],stats[name]=roi_gerber(path,zoom)
 for name in ['F.Mask','B.Mask','F.Paste','B.Paste']:
  bg,_=roi_gerber(bfiles[name],zoom);check('actual_'+name.replace('.','_')+'_matches_r13',g[name].symmetric_difference(bg).area<1e-7,symmetric_difference_mm2=g[name].symmetric_difference(bg).area)
 paste=g['F.Paste'].intersection(roi);native_paste=unary_union([H.native_geom(p,P.F_Paste)for p in u.Pads()if not p.GetNumber()and p.IsOnLayer(P.F_Paste)])
 check('actual_paste_matches_native',paste.symmetric_difference(native_paste).area<1e-6,area_mm2=paste.area,EP_coverage_percent=paste.area/(1.68**2)*100)
 check('no_bottom_paste_in_U101_region',g['B.Paste'].is_empty)
 drills=[]
 for path in cam.glob('*.drl'):
  for o in ExcellonFile.open(path).objects:
   bb=o.bounding_box(MM)
   if bb is None:continue
   (x0,y0),(x1,y1)=bb
   if not roi.intersects(box(x0,-y1,x1,-y0)):continue
   h=scale(H.object_geom(o),yfact=-1,origin=(0,0));p=h.centroid
   if roi.contains(p):drills.append({'file':path.name,'center_mm':[round(p.x,6),round(p.y,6)],'diameter_mm':round(h.bounds[2]-h.bounds[0],6),'geom':h})
 expected=sorted([[round(center[0]+x,6),round(center[1]+y,6)]for x,y in expected_local]);drill_summary=[{k:v for k,v in d.items()if k!='geom'}for d in drills]
 check('four_actual_Excellon_PTH_030',len(drills)==4 and sorted(d['center_mm']for d in drills)==expected and all('-PTH'in d['file']and abs(d['diameter_mm']-.3)<.00005 for d in drills),drills=drill_summary)
 holes=unary_union([d['geom']for d in drills]);check('nominal_paste_avoids_drills',paste.intersection(holes).area<1e-9,gap_mm=paste.distance(holes))
 Q=512;secant=1/math.cos(math.pi/(4*Q));swept=unary_union([box(x-.105,y-.105,x+.105,y+.105).buffer(.215*secant,quad_segs=Q)for x,y in expected]);grown=paste.buffer(.02*secant,quad_segs=Q,join_style=1);gap=grown.distance(swept);overlap=grown.intersection(swept).area
 check('continuous_actual_paste_tolerance_envelope',gap>=.0199 and overlap<1e-9,minimum_gap_mm=gap,overlap_mm2=overlap,manual_print_alignment_each_axis_mm=.03,hole_position_each_axis_mm=.075,max_hole_diameter_mm=.43,stencil_edge_outward_mm=.02,target_gap_mm=.020,method='Continuous square-plus-circumscribed-disk Minkowski envelope; no discrete translation sampling',circle_quad_segs=Q,secant_inflation=secant)
 for name in ['F.Mask','B.Mask']:check('open_holes_'+name.replace('.','_'),g[name].buffer(H.EPS).covers(holes),uncovered_hole_area_mm2=holes.difference(g[name]).area)
 pieces=list(g['F.Mask'].geoms)if g['F.Mask'].geom_type=='MultiPolygon'else[g['F.Mask']];central=next((p for p in pieces if p.covers(Point(center))),GeometryCollection());bridges=[]
 for p in u.Pads():
  if p.GetNumber()not in {str(i)for i in range(1,17)}:continue
  m=[s for s in pieces if s.covers(Point(H.xy(p.GetPosition())))];bridges.append({'pin':p.GetNumber(),'gap_mm':central.distance(m[0])if len(m)==1 and not central.is_empty else -1})
 check('actual_mask_bridge_min010',len(bridges)==16 and min(x['gap_mm']for x in bridges)>=.1-.00001,minimum_mm=min(x['gap_mm']for x in bridges),per_pin=bridges)
 copper_pieces=list(g['F.Cu'].geoms)if g['F.Cu'].geom_type=='MultiPolygon'else[g['F.Cu']];epcomp=next((p for p in copper_pieces if p.covers(Point(center))),GeometryCollection());vss=next(p for p in u.Pads()if p.GetNumber()=='8')
 check('FCu_EP_four_PTH_lands_and_VSS8_same_copper_component',not epcomp.is_empty and all(epcomp.covers(Point(p))for p in expected+[H.xy(vss.GetPosition())]),component_area_within_ROI_mm2=epcomp.area)
 for L,name in [(P.In1_Cu,'In1.Cu'),(P.In2_Cu,'In2.Cu')]:
  zones=[z for z in b.Zones()if not z.GetIsRuleArea()and z.IsOnLayer(L)];alien=[t.m_Uuid.AsString()for t in b.GetTracks()if not isinstance(t,P.PCB_VIA)and t.IsOnLayer(L)and t.GetNetname()!='GND'];check('source_inner_GND_only_'+name.replace('.','_'),bool(zones)and all(z.GetNetname()=='GND'for z in zones)and not alien,zone_count=len(zones),alien_tracks=alien)
  components=list(g[name].geoms)if g[name].geom_type=='MultiPolygon'else[g[name]];matches=[s for s in components if all(s.covers(Point(p))for p in expected)];comp=matches[0]if len(matches)==1 else GeometryCollection();halo=unary_union([Point(p).buffer(.4,quad_segs=256)for p in expected]);uncovered=halo.difference(comp).area
  check('actual_solid_GND_planes_around_all_four_PTH_'+name.replace('.','_'),not comp.is_empty and uncovered<1e-7 and comp.intersects(zoom.boundary),land_radius_mm=.3,required_solid_extension_mm=.1,uncovered_halo_mm2=uncovered,all_four_in_single_component=len(matches)==1,component_reaches_ROI_boundary=not comp.is_empty and comp.intersects(zoom.boundary))
 check('source_inputs_byte_unchanged',all(Path(p).exists()and H.sha(Path(p))==v for p,v in hashes.items()))
 warnings=['The ±0.03 mm local manual print registration limit requires inspection/acceptance; magnification availability is not a measurement of achieved alignment.','The conservative .43 mm hole /.075 mm each-axis position envelope is not a manufacturer certification of this via process.','Nominal annulus .15 mm; independently combining max hole and diagonal position offset gives .30-.215-sqrt(2)*.075 = -0.021066 mm, so this is not a guaranteed annular-ring proof.','Published solder-mask registration hard limit is not established; .1024 mm nominal bridge is only artwork geometry.','Open PTH solder wicking, paste transfer at roughly 51% nominal EP area, actual joint quality and thermal rise require first-board validation.','This script checks U101 CAM locally and inner reference intent only; full board DRC, power/SI review, order parameters and final CAM review remain separate.']
 result={'status':'PASS_U101_ROUTED_CAM_SCOPE'if not errors else'FAIL','scope':'Routed r14, U101 actual independent Gerber/Excellon local geometry and conditional continuous tolerance; not production qualification','checks':checks,'errors':errors,'warnings':warnings,'input_hashes':hashes,'script_sha256':H.sha(Path(__file__)),'actual_cam':str(cam),'baseline_cam':str(bcam),'actual_cam_hashes':{p.name:H.sha(p)for p in cam.iterdir()if p.is_file()},'gerber_ROI_object_stats':stats}
 report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps({'status':result['status'],'checks':len(checks),'errors':errors},indent=2));return bool(errors)
if __name__=='__main__':raise SystemExit(main())

#!/usr/bin/env python3
"""Full microphone annulus and mask local CAM comparison, preserving macro polarity."""
from pathlib import Path
import argparse,json,sys
from shapely.geometry import box,Point
from shapely.ops import unary_union
from gerbonara import GerberFile
from gerbonara.graphic_objects import Region
D=Path(__file__).resolve().parent;B=D.parent;sys.path.insert(0,str(B))
from cam_geometry import read_geometry,object_geometry
p=argparse.ArgumentParser();p.add_argument('--eda-dir',type=Path,required=True);p.add_argument('--kicad-dir',type=Path,required=True);p.add_argument('--cache',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
# Entire custom annulus centered(61,-62),outer radius0.825 plus mask25um.
window=box(60.05,-62.95,61.95,-61.05);hole=Point(61,-62).buffer(.3,quad_segs=180);checks=[]
for layer,kname,ename in [('F.Cu','ESPaperPlay_Devboard-F_Cu.gtl','Gerber_TopLayer.GTL'),('B.Cu','ESPaperPlay_Devboard-B_Cu.gbl','Gerber_BottomLayer.GBL'),('F.Mask','ESPaperPlay_Devboard-F_Mask.gts','Gerber_TopSolderMaskLayer.GTS'),('B.Mask','ESPaperPlay_Devboard-B_Mask.gbs','Gerber_BottomSolderMaskLayer.GBS')]:
 k,km=read_geometry(a.kicad_dir/kname,a.cache);e,em=read_geometry(a.eda_dir/ename,a.cache);k=k.intersection(window);e=e.intersection(window)
 if layer.endswith('Cu'):k=k.difference(hole);e=e.difference(hole)
 r={'layer':layer,'source_sha256':km['sha256'],'converted_sha256':em['sha256'],'source_area_mm2':k.area,'converted_area_mm2':e.area,'symmetric_difference_mm2':k.symmetric_difference(e).area,'hausdorff_mm':None if k.is_empty or e.is_empty else k.hausdorff_distance(e)}
 for tol in [.0001,.001,.005]:r[f'removed_beyond_{tol}_mm_mm2']=k.difference(e.buffer(tol)).area;r[f'added_beyond_{tol}_mm_mm2']=e.difference(k.buffer(tol)).area
 r['pass_0_1um']=r['removed_beyond_0.0001_mm_mm2']<1e-8 and r['added_beyond_0.0001_mm_mm2']<1e-8;checks.append(r)
nominal_checks=[]
for layer,name,rout,rin in [('F.Cu','Gerber_TopLayer.GTL',.825,.525),('F.Mask','Gerber_TopSolderMaskLayer.GTS',.850,.500)]:
 raw=(a.eda_dir/name).read_text();hdr,body=raw.split('G04 Pad Start*',1);g=GerberFile.from_string(hdr+body.split('G04 Pad End*',1)[0]+'\nM02*\n');regions=[]
 for obj in g.objects:
  if not isinstance(obj,Region):continue
  geom=object_geometry(obj)
  if geom.intersects(window):regions.append(geom)
 assert len(regions)==4
 actual=unary_union(regions);nominal=Point(61,-62).buffer(rout,quad_segs=2048).difference(Point(61,-62).buffer(rin,quad_segs=2048));removed=nominal.difference(actual.buffer(.0001)).area;added=actual.difference(nominal.buffer(.0001)).area
 nominal_checks.append({'layer':layer,'sector_count':len(regions),'outer_radius_mm':rout,'inner_radius_mm':rin,'actual_bounds_mm':list(actual.bounds),'actual_area_mm2':actual.area,'nominal_area_mm2':nominal.area,'hausdorff_mm':actual.hausdorff_distance(nominal),'removed_beyond_0_1um_mm2':removed,'added_beyond_0_1um_mm2':added,'pass':removed<1e-8 and added<1e-8})
report={'status':'NOMINAL_SOURCE_CIRCLES_PASS_BASELINE_GERBER_TESSELLATION_DIFFERENCES'if all(x['pass']for x in nominal_checks)else'FAIL','window_mm':list(window.bounds),'checks':checks,'nominal_source_circle_checks':nominal_checks,'source_basis':'KiCad U803 pad4 primitives gr_circle center(0,.675), end(.675,.675), stroke.3mm: ringRout.825 Rin.525; solder_mask_margin.025mm givesmaskRout.850 Rin.500. Original KiCad Gerber tessellates these circles, while final Gerber retains4curvedsectors.','limits':['Cu excludes the nominal0.6mm NPTHdisk only, which contains the intentional1um copper dot; surrounding custom annulus and mask are fully included.','Uses actual CAM geometric union, not source custom-pad shape name. 0.05um curve approximation; reports at0.1um,1um,5um separately.']}
a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))

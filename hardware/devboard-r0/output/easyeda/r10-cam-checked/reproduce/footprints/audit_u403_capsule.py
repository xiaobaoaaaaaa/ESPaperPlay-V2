#!/usr/bin/env python3
"""Physical copper union in U403 pin1 local window, independent of primitive type."""
import argparse,json,sys
from pathlib import Path
from shapely.geometry import box
D=Path(__file__).resolve().parent;B=D.parent;sys.path.insert(0,str(B))
from cam_geometry import read_geometry
p=argparse.ArgumentParser();p.add_argument('--eda-dir',type=Path,default=B/'repaired1-gerber');p.add_argument('--kicad-dir',type=Path,default=B/'kicad');p.add_argument('--cache',type=Path);p.add_argument('--output',type=Path,default=D/'repaired1-u403-capsule-audit.json');a=p.parse_args()
k,km=read_geometry(a.kicad_dir/'ESPaperPlay_Devboard-F_Cu.gtl',a.cache);e,em=read_geometry(a.eda_dir/'Gerber_TopLayer.GTL',a.cache)
window=box(176.2,-100.65,178.15,-99.45);k=k.intersection(window);e=e.intersection(window);tol=.0001
r={'status':'PASS','window_mm':list(window.bounds),'comparison_tolerance_mm':tol,'source_sha256':km['sha256'],'converted_sha256':em['sha256'],'source_area_mm2':k.area,'converted_area_mm2':e.area,'removed_beyond_tolerance_mm2':k.difference(e.buffer(tol)).area,'added_beyond_tolerance_mm2':e.difference(k.buffer(tol)).area,'symmetric_difference_mm2':k.symmetric_difference(e).area,'finding':'Includes source pad, retained adjacent routing and two duplicate 0.0005mm x0.8mm track cap copper. Compare union so duplicate tracks cannot double-count area.'}
r['status']='PASS'if r['removed_beyond_tolerance_mm2']<1e-8 and r['added_beyond_tolerance_mm2']<1e-8 else'FAIL';a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))

#!/usr/bin/env python3
from pathlib import Path
import argparse,json
from gerbonara import ExcellonFile
from shapely.ops import unary_union
from shapely.geometry import Point
from cam_geometry import read_geometry,object_geometry,comparison

def main():
 p=argparse.ArgumentParser();p.add_argument('--source-dir',type=Path,required=True);p.add_argument('--eda-dir',type=Path,required=True);p.add_argument('--cache',type=Path);p.add_argument('--pcb-source',type=Path,required=True);p.add_argument('--fill-cap-csv',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
 holes=unary_union([object_geometry(o)for name in ['Drill_PTH_Through.DRL','Drill_NPTH_Through.DRL']for o in ExcellonFile.open(a.eda_dir/name).objects]);report={'layers':[]}
 for kn,en,drilled in [('F_Cu.gtl','TopLayer.GTL',True),('B_Cu.gbl','BottomLayer.GBL',True),('F_Mask.gts','TopSolderMaskLayer.GTS',False),('B_Mask.gbs','BottomSolderMaskLayer.GBS',False)]:
  k,km=read_geometry(a.source_dir/('ESPaperPlay_Devboard-'+kn),a.cache);e,em=read_geometry(a.eda_dir/('Gerber_'+en),a.cache)
  if drilled:k=k.difference(holes);e=e.difference(holes)
  c=comparison(k,e);assert c['removed_beyond_5um_mm2']<1e-8 and c['added_beyond_5um_mm2']<1e-8,(kn,c)
  report['layers'].append({'layer':kn,'postdrill':drilled,'source':km,'final':em,'comparison':c})
 import csv
 caps=list(csv.DictReader(a.fill_cap_csv.open()));print('caps fields',list(caps[0]))
 # Explicit drill-to-mask check uses 11 designated thermal exceptions only.
 capids={r['EasyEDA_primitive_id']for r in caps}
 masks=[read_geometry(a.eda_dir/n,a.cache)[0]for n in ['Gerber_TopSolderMaskLayer.GTS','Gerber_BottomSolderMaskLayer.GBS']]
 checks=[]
 for l in a.pcb_source.read_text().splitlines():
  h,v=l.split('||',1);h=json.loads(h);v=json.loads(v[:-1]if v.endswith('|')else v)
  if h['type']!='VIA':continue
  if h['id']in capids:continue
  pt=Point(v['centerX']*.0254,v['centerY']*.0254);r=v['holeDiameter']*.0254/2
  ds=[pt.distance(m)-r for m in masks];checks.append({'id':h['id'],'clearances_mm':ds})
 assert len(checks)==538 and len(capids)==11
 minimum=min(d for c in checks for d in c['clearances_mm']);assert minimum>=.2-.00002,minimum
 report.update(status='PASS',normal_via_mask_check={'count':538,'designated_fill_cap_exceptions':11,'minimum_actual_nominal_drill_edge_to_mask_mm':minimum,'checks':checks},limits='5um whole-layer comparison accommodates tessellated vs analytic curves; actual pad masks separately checked at0.1um. No claim of bit-identical copper or factory registration tolerance.')
 a.report.write_text(json.dumps(report,indent=2)+'\n');print('PASS outer copper/mask; minimum via-mask',minimum)
if __name__=='__main__':main()

#!/usr/bin/env python3
"""Actual Gerber mask aperture comparison for every standard physical pad."""
from pathlib import Path
import json,sys,math,collections,argparse
from gerbonara import GerberFile
from gerbonara.graphic_objects import Flash
from shapely.ops import unary_union
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cam_geometry import object_geometry
B=Path(__file__).resolve().parents[1];D=Path(__file__).resolve().parent
ap=argparse.ArgumentParser();ap.add_argument('--eda-dir',type=Path,default=B/'eda');ap.add_argument('--kicad-dir',type=Path,default=B/'kicad');ap.add_argument('--pad-audit',type=Path,default=D/'footprint-audit.json');ap.add_argument('--output',type=Path,default=D/'mask-flash-audit.json');args=ap.parse_args()
pads=json.loads(args.pad_audit.read_text())['pads'];report={'checks':[],'status':'PENDING','curve_tolerance_mm':.00005,'comparison_margin_mm':.0001,'limits':'Standard pad mask flash apertures only. U803 annular mask needs region/whole-layer comparison; source CAD geometry and source-excluded underside openings are independently checked.'}
for side,ks,es in [('F.Mask','ESPaperPlay_Devboard-F_Mask.gts','Gerber_TopSolderMaskLayer.GTS'),('B.Mask','ESPaperPlay_Devboard-B_Mask.gbs','Gerber_BottomSolderMaskLayer.GBS')]:
 k=GerberFile.open(args.kicad_dir/ks);e=GerberFile.open(args.eda_dir/es);kf=[o for o in k.objects if isinstance(o,Flash)];ef=[o for o in e.objects if isinstance(o,Flash)]
 for pad in pads:
  ref=pad['ref'];x,y=pad['source_center_mm'];y=-y;expected=next(m for m in pad['mask']if m['layer']==side)['source_present'];kmatch=[o for o in kf if o.attrs.get('.C')==(ref,)and math.hypot(o.x-x,o.y-y)<2e-5];ematch=[o for o in ef if math.hypot(o.x-x,o.y-y)<2e-5]
  item={'ref':ref,'pin':pad['number'],'pad_id':pad['converted_id'],'side':side,'center_mm':[x,y],'source_expected':expected,'source_flash_count':len(kmatch),'converted_flash_count':len(ematch)}
  if not expected:
   item['pass']=not kmatch and not ematch
   if ematch:item['finding']='Unexpected underside mask opening'
  elif len(kmatch)==len(ematch) and len(kmatch)>0:
   a=unary_union([object_geometry(o)for o in kmatch]);b=unary_union([object_geometry(o)for o in ematch]);delta=a.symmetric_difference(b).area
   area_removed=a.difference(b.buffer(.0001)).area;area_added=b.difference(a.buffer(.0001)).area
   item.update(source_bounds_mm=list(a.bounds),converted_bounds_mm=list(b.bounds),source_area_mm2=a.area,converted_area_mm2=b.area,symmetric_difference_mm2=delta,removed_beyond_0_1um_mm2=area_removed,added_beyond_0_1um_mm2=area_added)
   item['pass']=area_removed<1e-8 and area_added<1e-8
   if not item['pass']:item['finding']='Mask aperture geometry mismatch'
  else:item.update({'pass':False,'finding':'Unexpected flash multiplicity'})
  report['checks'].append(item)
report['failures']=[x for x in report['checks']if not x['pass']];report['counts']={'checked_pad_layer_pairs':len(report['checks']),'matched':sum(x['pass']for x in report['checks']),'failed':len(report['failures']),'finding_types':dict(collections.Counter(x['finding']for x in report['failures']))};report['status']='PASS'if not report['failures']else'FAIL';args.output.write_text(json.dumps(report,indent=2)+'\n');print(report['counts']);print([(x['ref'],x['pin'],x['side'],x.get('source_bounds_mm'),x.get('converted_bounds_mm'),x.get('finding'))for x in report['failures']][:15])

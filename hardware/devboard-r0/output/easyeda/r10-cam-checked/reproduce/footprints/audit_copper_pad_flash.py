#!/usr/bin/env python3
"""Compare actual outer-layer pad flashes, excluding traces and vias."""
from pathlib import Path
import json,sys,math,argparse
from gerbonara import GerberFile
from gerbonara.graphic_objects import Flash
from shapely.ops import unary_union
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cam_geometry import object_geometry
B=Path(__file__).resolve().parents[1];D=Path(__file__).resolve().parent
ap=argparse.ArgumentParser();ap.add_argument('--eda-dir',type=Path,default=B/'eda');ap.add_argument('--kicad-dir',type=Path,default=B/'kicad');ap.add_argument('--pad-audit',type=Path,default=D/'footprint-audit.json');ap.add_argument('--output',type=Path,default=D/'copper-pad-flash-audit.json');args=ap.parse_args();pads=json.loads(args.pad_audit.read_text())['pads'];checks=[]
for side,kn,en in [('F.Cu','ESPaperPlay_Devboard-F_Cu.gtl','Gerber_TopLayer.GTL'),('B.Cu','ESPaperPlay_Devboard-B_Cu.gbl','Gerber_BottomLayer.GBL')]:
 k=GerberFile.open(args.kicad_dir/kn);raw=(args.eda_dir/en).read_text();header,body=raw.split('G04 Pad Start*',1);body=body.split('G04 Pad End*')[0];e=GerberFile.from_string(header+body+'\nM02*\n');kf=[o for o in k.objects if isinstance(o,Flash)];ef=[o for o in e.objects if isinstance(o,Flash)]
 for p in pads:
  if side not in p['layers']:continue
  ref=p['ref'];num=p['number'];x,y=p['source_center_mm'];y=-y;item={'ref':ref,'number':num,'side':side,'center_mm':[x,y]}
  ematch=[o for o in ef if math.hypot(o.x-x,o.y-y)<2e-5];kmatch=[o for o in kf if o.attrs.get('.P',())[:2]==(ref,num) and math.hypot(o.x-x,o.y-y)<2e-5]
  item.update(source_flash_count=len(kmatch),converted_flash_count=len(ematch))
  if num=='':
   assert not kmatch and len(ematch)==1
   geom=object_geometry(ematch[0]);w=p['source_drill_mm'][0];h=p['source_drill_mm'][1];b=geom.bounds;diameter=getattr(ematch[0].aperture,'diameter',None);exception=p.get('intentional_npth_copper_exception');target=exception['target_diameter_mm']if exception else w;ok=diameter is not None and abs(diameter-target)<1e-8 and (not exception or diameter<min(w,h))
   item.update(pass_flag=ok,kind='NPTH bounded1um copper dot inside nominal drill'if exception else'NPTH nominal copper flash disk equals nominal drill disk',flash_bounds_mm=list(b),flash_diameter_mm=diameter,drill_mm=[w,h])
  elif kmatch and ematch:
   a=unary_union([object_geometry(o)for o in kmatch]);b=unary_union([object_geometry(o)for o in ematch]);removed=a.difference(b.buffer(.0001)).area;added=b.difference(a.buffer(.0001)).area
   item.update(pass_flag=removed<1e-8 and added<1e-8,kind='standard copper pad',source_bounds_mm=list(a.bounds),converted_bounds_mm=list(b.bounds),removed_beyond_0_1um_mm2=removed,added_beyond_0_1um_mm2=added)
  else:item.update(pass_flag=False,kind='unmatched copper pad flash')
  checks.append(item)
failures=[x for x in checks if not x['pass_flag']];report={'status':'PASS'if not failures else'FAIL','checked_outer_layer_pad_pairs':len(checks),'npth_pre_drill_flash_pairs':sum(x['kind'].startswith('NPTH')for x in checks),'failures':failures,'checks':checks,'limits':['Only standard pad outer-layer apertures; source pad geometry and inner copper connectivity audited separately.','U803 custom ring excluded here; independent annular sector/Gerber audit applies.','0.00005mm arc approximation; 0.0001mm comparison allowance.']};args.output.write_text(json.dumps(report,indent=2)+'\n');print({k:v for k,v in report.items()if k!='checks'})

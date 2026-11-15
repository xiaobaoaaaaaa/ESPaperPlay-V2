#!/usr/bin/env python3
"""Verify all NPTH drill, tiny copper flashes and compensated mask openings analytically."""
import argparse,hashlib,json,math,warnings
from pathlib import Path
from gerbonara import GerberFile,ExcellonFile
from gerbonara.graphic_objects import Flash
from gerbonara.utils import MM
p=argparse.ArgumentParser();p.add_argument('--eda-dir',type=Path,required=True);p.add_argument('--pad-audit',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
pads=[x for x in json.loads(a.pad_audit.read_text())['pads']if x.get('intentional_npth_copper_exception')];assert len(pads)==7
files={};hashes={};checks=[]
for label,name in [('F.Cu','Gerber_TopLayer.GTL'),('In1.Cu','Gerber_InnerLayer1.G1'),('In2.Cu','Gerber_InnerLayer2.G2'),('B.Cu','Gerber_BottomLayer.GBL'),('F.Mask','Gerber_TopSolderMaskLayer.GTS'),('B.Mask','Gerber_BottomSolderMaskLayer.GBS')]:
 path=a.eda_dir/name;raw=path.read_text();hashes[name]=hashlib.sha256(path.read_bytes()).hexdigest()
 if label.endswith('Cu'):
  header,body=raw.split('G04 Pad Start*',1);raw=header+body.split('G04 Pad End*',1)[0]+'\nM02*\n'
 files[label]=[x.converted(MM)for x in GerberFile.from_string(raw).objects if isinstance(x,Flash)]
path=a.eda_dir/'Drill_NPTH_Through.DRL';hashes[path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
with warnings.catch_warnings(record=True)as caught:
 warnings.simplefilter('always');drill=ExcellonFile.open(path)
dobjects=[x.converted(MM)for x in drill.objects];assert len(dobjects)==7
for pad in pads:
 x,y=pad['source_center_mm'];y=-y;expected_d=pad['source_drill_mm'][0]
 def match(objects):return[o for o in objects if isinstance(o,Flash)and math.hypot(o.x-x,o.y-y)<2e-5]
 ds=match(dobjects);drill_ok=len(ds)==1 and abs(ds[0].aperture.diameter-expected_d)<1e-8 and ds[0].aperture.plated==False
 entry={'ref':pad['ref'],'pad_id':pad['converted_id'],'center_mm':[x,y],'expected_drill_diameter_mm':expected_d,'drill_ok':drill_ok,'copper':[],'mask':[]}
 for label,objects in files.items():
  found=match(objects);r={'layer':label,'flash_count':len(found),'pass':False}
  if len(found)==1:
   o=found[0];d=getattr(o.aperture,'diameter',None);r['diameter_mm']=d;r['center_error_mm']=math.hypot(o.x-x,o.y-y)
   if d is not None:
    if label.endswith('Cu'):
     r['radial_margin_to_actual_drill_mm']=(ds[0].aperture.diameter-d)/2-math.hypot(o.x-ds[0].x,o.y-ds[0].y)if ds else None
     r['pass']=drill_ok and abs(d-.001)<1e-8 and r['radial_margin_to_actual_drill_mm']>=.29949
    else:
     m=next(z for z in pad['mask']if z['layer']==label);expected=pad['source_size_mm'][0]+2*m['source_margin_mm'];r['expected_mask_diameter_mm']=expected;r['pass']=abs(d-expected)<1e-8
  entry['copper'if label.endswith('Cu')else'mask'].append(r)
 entry['pass']=drill_ok and all(z['pass']for z in entry['copper']+entry['mask']);checks.append(entry)
r={'status':'PASS'if all(z['pass']for z in checks)else'FAIL','checks':checks,'counts':{'npth_holes':len(dobjects),'copper_flashes':sum(len(x['copper'])for x in checks),'mask_apertures':sum(len(x['mask'])for x in checks),'passed_holes':sum(z['pass']for z in checks)},'input_hashes':hashes,'warnings':[str(w.message)for w in caught],'method':'Analytic circle diameters/centers, not polygonized bounding boxes. Compare each copper pad flash on all4layers and each mask flash to a matched NPTH Excellon drill. Nominal physical containment is not a factory drill-tolerance guarantee.'}
a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items()if k not in ['checks','input_hashes']}))

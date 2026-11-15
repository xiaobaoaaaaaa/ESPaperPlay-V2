#!/usr/bin/env python3
"""Read-only saved-source and final-CAM closure for the inner layer repairs."""
import json,hashlib,sys,math,argparse
from pathlib import Path
from shapely import wkb
from shapely.geometry import Point,box
from compare_repaired_inner import components
ap=argparse.ArgumentParser(description='Verify saved thermal/pour metadata and CAM repair witnesses; run compare_repaired_inner.py first to regenerate the referenced WKB files.')
for name in ['source-footprints','current-footprints','pcb-source','thermal-requests','pour-requests','comparison-report','witnesses','output']:
 ap.add_argument('--'+name,type=Path,required=True)
args=ap.parse_args()
def geometry_path(layer,label):
 return args.comparison_report.with_name(args.comparison_report.stem+f'-inner{layer}-{label}.wkb')

def rows(text):
 result={}
 for line in text.splitlines():
  if not line.strip():continue
  h,v=line.split('||',1);h=json.loads(h);v=json.loads(v.rstrip('|'));k=(h['type'],h.get('id'))
  if k not in result or h.get('ticket',0)>=result[k][0].get('ticket',0):result[k]=(h,v)
 return result
oldfp={x['uuid']:rows(x['source'])for x in json.loads(args.source_footprints.read_text())['result']}
newfile=args.current_footprints;newfp={x['uuid']:rows(x['source'])for x in json.loads(newfile.read_text())['result']}
req=json.loads(args.thermal_requests.read_text());matches=[];fail=[]
for r in req['requests']:
 key=('PAD',r['pad_id']);v=newfp[r['footprint_uuid']][key][1];old=oldfp[r['footprint_uuid']][key][1]
 diff={k:[old.get(k),v.get(k)]for k in old.keys()|v.keys()if old.get(k)!=v.get(k)}
 fields=[]
 for k,expected in r['set'].items():
  actual=v.get(k);ok=abs(expected-actual)<=.000051 if isinstance(expected,(int,float))and isinstance(actual,(int,float))else expected==actual
  fields.append({'field':k,'expected':expected,'actual':actual,'pass':ok})
 # Pad geometry must be unchanged. Only authorized thermal fields or solder metadata may change.
 geometry_changed={k:d for k,d in diff.items()if k not in ['connectMode','spokeSpace','spokeWidth','spokeAngle','topSolderExpansion','bottomSolderExpansion']}
 rec={'footprint_uuid':r['footprint_uuid'],'pad_id':r['pad_id'],'source_instances':len(r['source_instances']),'fields':fields,'geometry_changed':geometry_changed}
 matches.append(rec)
 if not all(f['pass']for f in fields)or geometry_changed:fail.append(rec)
unchanged=[]
for r in req['unchanged_angle90_evidence']:
 key=('PAD',r['pad_id']);v=newfp[r['footprint_uuid']][key][1];old=oldfp[r['footprint_uuid']][key][1]
 ok=all(v.get(k)==old.get(k)for k in ['connectMode','spokeSpace','spokeWidth','spokeAngle'])
 unchanged.append({'ref':r['ref'],'pin':r['pin'],'pass':ok})
 if not ok:fail.append(unchanged[-1])
source=rows(args.pcb_source.read_text());pours=[]
for r in json.loads(args.pour_requests.read_text())['requests']:
 v=source[('POUR',r['primitive_id'])][1];ok=v['pourType']==r['set']['pourType']and all(v[k]==x for k,x in r['keep_unchanged'].items());pours.append({'primitive_id':r['primitive_id'],'pass':ok,'actual':v})
 if not ok:fail.append(pours[-1])
geo=[]
for num in(1,2):
 a=wkb.loads(geometry_path(num,'source').read_bytes());b=wkb.loads(geometry_path(num,'current').read_bytes());old=wkb.loads(geometry_path(num,'previous').read_bytes())
 significant10={'removed_mm2':a.difference(b.buffer(.010)).area,'added_mm2':b.difference(a.buffer(.010)).area}
 significant15={'removed_mm2':a.difference(b.buffer(.015)).area,'added_mm2':b.difference(a.buffer(.015)).area}
 witnesses=[]
 for r in json.loads(args.witnesses.read_text()):
  p=Point(r['midpoint_cam']);witnesses.append({'midpoint_cam':r['midpoint_cam'],'source_copper':a.contains(p),'before_copper':old.contains(p),'after_copper':b.contains(p),'after_distance_to_copper_mm':b.distance(p)})
 # This bounding box encloses the U301 12 PTH EPAD matrix and its former thermal cutouts.
 region=box(156.45,-61.25,160.55,-57.15)
 u301={'source_copper_mm2':a.intersection(region).area,'before_removed_beyond5um_mm2':a.intersection(region).difference(old.buffer(.005)).area,'after_removed_beyond5um_mm2':a.intersection(region).difference(b.buffer(.005)).area,'after_added_beyond5um_mm2':b.intersection(region).difference(a.buffer(.005)).area}
 geo.append({'layer':num,'source_component_count':len(components(a)),'after_component_count':len(components(b)),'beyond10um':significant10,'beyond15um':significant15,'witnesses':witnesses,'U301_EP_through_hole_matrix':u301})
 if any(x['after_copper']for x in witnesses)or u301['after_removed_beyond5um_mm2']>1e-8:fail.append({'layer':num,'reason':'repair witness not closed'})
 if any(value>1e-9 for value in significant15.values())or len(components(a))!=len(components(b)):fail.append({'layer':num,'reason':'residual beyond15um or polygon component count differs'})
report={'status':'PASS_SOURCE_SEMANTICS_AND_CAM_REPAIR_WITNESSES'if not fail else'FAIL','saved_footprints_sha256':hashlib.sha256(newfile.read_bytes()).hexdigest(),'inputs_sha256':{str(v):hashlib.sha256(v.read_bytes()).hexdigest()for k,v in vars(args).items()if k!='output'},'metadata_numeric_tolerance_mil':.000051,'metadata_tolerance_note':'Current client saves thermal gap/width to4 decimals in mil; allowed rounding is at most1.2954nm in mm. Geometry fields are compared without tolerance.','thermal_request_count':len(matches),'thermal_matches':matches,'unchanged_angle90':unchanged,'pours':pours,'geometry':geo,'failures':fail,'limits':'PASS closes the enumerated migration defects; absolute cross-tool Gerber equivalence is not claimed. All remaining changes need interpretation against tolerances and manufacturing limits.'}
args.output.parent.mkdir(parents=True,exist_ok=True)
args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'status':report['status'],'metadata_count':len(matches),'failures':fail,'geometry':geo},ensure_ascii=False,indent=2))

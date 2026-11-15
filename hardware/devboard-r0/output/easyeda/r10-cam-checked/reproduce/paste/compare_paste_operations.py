#!/usr/bin/python3
"""Compare emitted Gerber drawing operations, resolving aperture numbers.
Ignores timestamps, unused aperture definitions and selection order. Compares
line/arc strokes, flashes, region contours, aperture macros and polarity.
Not a general RS-274X renderer or polygon-equivalence checker.
"""
import argparse,collections,hashlib,json,re,zipfile
from pathlib import Path

def sha(data):return hashlib.sha256(data if isinstance(data,bytes)else data.encode()).hexdigest()
def fingerprint(data):return sha(json.dumps(data,sort_keys=True,separators=(',',':')))
def canon(text):
 assert '%FSLAX45Y45*%'in text and '%MOMM*%'in text
 apertures={m[1]:(m[2],m[3]or'')for m in re.finditer(r'%ADD(\d+)([A-Za-z][A-Za-z0-9_]*)(?:,([^*]+))?\*%',text)}
 macros=re.findall(r'%AM.*?\*%',text,re.S)
 regions=[];ops=[];region=None;pos=None;active=None;polarity='D';interpolation=1
 for line in text.splitlines():
  line=line.strip()
  if line=='G36*':assert region is None;region=[];continue
  if line=='G37*':assert region is not None;regions.append({'polarity':polarity,'path':region});region=None;continue
  m=re.fullmatch(r'%LP([DC])\*%',line)
  if m:polarity=m[1];continue
  m=re.fullmatch(r'G54D(\d+)\*',line)
  if m:active=m[1];continue
  m=re.fullmatch(r'(?:G0([123]))?X(-?\d+)Y(-?\d+)(?:I(-?\d+)J(-?\d+))?D0([123])\*',line)
  if m:
   g=int(m[1])if m[1]else interpolation;interpolation=g;end=[int(m[2]),int(m[3])];action=int(m[6]);ij=[int(m[4]),int(m[5])]if m[4]else None
   if region is not None:region.append({'g':g,'end':end,'ij':ij,'action':action})
   elif action in [1,3]:
    assert active in apertures, (text[:80],line,active,list(apertures.items())[:10])
    op={'kind':'flash'if action==3 else 'stroke','polarity':polarity,'aperture':apertures[active],'end':end}
    if action==1:assert pos is not None;op.update({'g':g,'start':pos,'ij':ij})
    ops.append(op)
   pos=end;continue
  if 'D01*'in line or 'D03*'in line:raise AssertionError('Unsupported drawing command: '+line)
 assert region is None
 # Ordered regions and operations are retained: no assumptions about overlap ordering.
 return {'macro_definitions':macros,'regions':regions,'operations':ops}
def counts(seq):return collections.Counter(json.dumps(x,sort_keys=True,separators=(',',':'))for x in seq)
def remove_zero_length_region_edges(document):
 removed=0;result=json.loads(json.dumps(document))
 for region in result['regions']:
  previous=None;path=[]
  for command in region['path']:
   # A G01 edge with identical endpoints inside a filled region contributes no
   # area. Never remove arcs (same endpoints may mean a full circle) or strokes.
   if command['action']==1 and command['g']==1 and command['end']==previous:
    removed+=1;continue
   path.append(command);previous=command['end']
  region['path']=path
 return result,removed
def compare(a,b):
 da,db=canon(a),canon(b);ca,cb=counts(da['operations']),counts(db['operations']);removed=[json.loads(x)for x in (ca-cb).elements()];added=[json.loads(x)for x in(cb-ca).elements()]
 return {'before_geometry_sha256':fingerprint(da),'after_geometry_sha256':fingerprint(db),'geometry_equal':da==db,'regions_equal':da['regions']==db['regions'],'macro_definitions_equal':da['macro_definitions']==db['macro_definitions'],'before_operation_count':len(da['operations']),'after_operation_count':len(db['operations']),'removed_operations':removed,'added_operations':added}

def main():
    ap=argparse.ArgumentParser(description="Exact drawing-operation comparison for this absolute-MM Gerber subset")
    ap.add_argument('--before',type=Path,required=True)
    ap.add_argument('--after',type=Path,required=True)
    ap.add_argument('--report',type=Path,required=True)
    ap.add_argument('--ignore-zero-length-region-edges',action='store_true',help='Normalize only degenerate G01 edges inside filled regions; preserve all arcs and strokes')
    a=ap.parse_args()
    result=compare(a.before.read_text(),a.after.read_text())
    if a.ignore_zero_length_region_edges:
        before,n1=remove_zero_length_region_edges(canon(a.before.read_text()))
        after,n2=remove_zero_length_region_edges(canon(a.after.read_text()))
        result['strict_geometry_equal']=result['geometry_equal']
        result['geometry_equal']=before==after
        result['normalization']='Only G01 region edges with identical endpoints removed; exact geometric identity, no coordinate tolerance'
        result['zero_length_region_edges_removed']={'before':n1,'after':n2}
        result['normalized_before_geometry_sha256']=fingerprint(before)
        result['normalized_after_geometry_sha256']=fingerprint(after)
    result.update(before=str(a.before),after=str(a.after),before_raw_sha256=sha(a.before.read_bytes()),after_raw_sha256=sha(a.after.read_bytes()),method='Exact ordered strokes/flashes, regions, macro definitions and polarity; used aperture numbers resolved, unused definitions and generation comments omitted')
    a.report.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items()if k not in ['removed_operations','added_operations']},indent=2))
    if not result['geometry_equal']:raise SystemExit(1)
if __name__=='__main__':main()

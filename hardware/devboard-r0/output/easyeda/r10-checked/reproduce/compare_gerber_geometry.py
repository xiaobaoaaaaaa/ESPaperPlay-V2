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
def compare(a,b):
 da,db=canon(a),canon(b);ca,cb=counts(da['operations']),counts(db['operations']);removed=[json.loads(x)for x in (ca-cb).elements()];added=[json.loads(x)for x in(cb-ca).elements()]
 return {'before_geometry_sha256':fingerprint(da),'after_geometry_sha256':fingerprint(db),'geometry_equal':da==db,'regions_equal':da['regions']==db['regions'],'macro_definitions_equal':da['macro_definitions']==db['macro_definitions'],'before_operation_count':len(da['operations']),'after_operation_count':len(db['operations']),'removed_operations':removed,'added_operations':added}
p=argparse.ArgumentParser();p.add_argument('before',type=Path);p.add_argument('after',type=Path);p.add_argument('--report',type=Path);a=p.parse_args();results=[]
with zipfile.ZipFile(a.before)as z1,zipfile.ZipFile(a.after)as z2:
 assert set(z1.namelist())==set(z2.namelist())
 for n in z1.namelist():
  x,y=z1.read(n),z2.read(n);d={'file':n,'before_raw_sha256':sha(x),'after_raw_sha256':sha(y),'raw_equal':x==y}
  if n.startswith('Gerber_'):
   d.update(compare(x.decode(),y.decode()))
  elif n.endswith('.DRL'):
   norm=lambda s:'\n'.join(l for l in s.splitlines()if not l.startswith(';EasyEDA Pro v'))
   xx,yy=norm(x.decode()),norm(y.decode());d.update({'before_geometry_sha256':sha(xx),'after_geometry_sha256':sha(yy),'geometry_equal':xx==yy})
  else:continue
  results.append(d)
copper_names=['Gerber_TopLayer.GTL','Gerber_BottomLayer.GBL','Gerber_InnerLayer1.G1','Gerber_InnerLayer2.G2'];copper=[x for x in results if x['file']in copper_names];drill=[x for x in results if x['file'].endswith('.DRL')];nonpaste=[x for x in results if 'PasteMaskLayer'not in x['file']]
report={'before_zip':str(a.before),'after_zip':str(a.after),'before_zip_sha256':sha(a.before.read_bytes()),'after_zip_sha256':sha(a.after.read_bytes()),'copper_drawing_operations_unchanged':all(x['geometry_equal']for x in copper),'drill_geometry_unchanged':all(x['geometry_equal']for x in drill),'all_nonpaste_fabrication_geometry_unchanged':all(x['geometry_equal']for x in nonpaste),'files':results,'limitations':'Compares emitted drawing operations in the observed absolute-coordinate MM RS274X subset, resolves aperture IDs and omits unused aperture definitions; ordered region paths and aperture macro definitions must match exactly. Drill comparison ignores only the generation timestamp. This is not arbitrary RS274X geometric rendering or fabrication approval.'}
dest=a.report or a.after.with_suffix('.geometry-comparison.json');dest.write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items()if k!='files'},indent=2));print(json.dumps([{'file':d['file'],'geometry_equal':d['geometry_equal'],'removed':len(d.get('removed_operations',[])),'added':len(d.get('added_operations',[]))}for d in results],indent=2))

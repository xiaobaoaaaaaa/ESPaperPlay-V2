#!/usr/bin/env python3
"""Assert the complete live CAM edit delta is confined to documented repairs."""
import argparse,collections,json,hashlib,copy
from pathlib import Path

def states(text):
 out={}
 for line in text.splitlines():
  if not line.strip():continue
  h,v=line.split('||',1);h=json.loads(h);v=v[:-1]if v.endswith('|')else v;k=(h['type'],h.get('id'));v=json.loads(v)if v else None
  if k not in out or h.get('ticket',0)>=out[k][0].get('ticket',0):out[k]=h,v
 return{k:v for k,(h,v)in out.items()if v is not None and v!=''}
def main():
 p=argparse.ArgumentParser();p.add_argument('--before',type=Path,required=True);p.add_argument('--after',type=Path,required=True);p.add_argument('--before-footprints',type=Path,required=True);p.add_argument('--after-footprints',type=Path,required=True);p.add_argument('--manifest',type=Path,required=True);p.add_argument('--npth-requests',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
 b=states(a.before.read_text());f=states(a.after.read_text());changes=[];renames=[];extras=[]
 for k in b.keys()|f.keys():
  x=b.get(k);y=f.get(k)
  if x==y:continue
  typ,uid=k
  if typ=='DOCHEAD':reason='save state/version metadata'
  elif typ=='POURED':reason='rebuilt derived copper'
  elif typ=='POUR':
   assert uid in {'ie6149','ie6150'};z=copy.deepcopy(x);z['pourType']['fineness']=.15/.0254;assert z==y;reason='restore 0.15 mm minimum copper neck'
  elif typ=='FILL':
   assert x is None and uid=='873158c0579218ee'and y['netName']=='3V3_AON'and y['layerId']==1 and y['path'][0].count('ARC')==2 and y['fillStyle']=='SOLID';reason='restore U403.1 original capsule copper; separately checked actual Gerber against KiCad'
  elif typ=='ATTR':
   if x is not None:
    matches=[kk for kk,v in f.items()if kk[0]=='ATTR'and v==x];assert len(matches)==1;renames.append({'old':uid,'new':matches[0][1]})
   if x is None:
    assert uid.endswith('r0')and y==b['ATTR',uid[:-2]];reason='renamed attribute preserving exact value'
   else:
    assert y['key']=='Footprint'and y['parentId']==''and y['x']is None and y['y']is None and y['keyVisible']is False and y['valueVisible']is False
    assert y['value'].startswith('ESPaperPlay:');extras.append(uid);reason='hidden library footprint name; prior component binding relocated without change'
  else:raise AssertionError(('Unexpected source mutation',k))
  changes.append({'type':typ,'id':uid,'reason':reason})
 bf={x['uuid']:states(x['source'])for x in json.loads(a.before_footprints.read_text())['result']};ff={x['uuid']:states(x['source'])for x in json.loads(a.after_footprints.read_text())['result']};assert bf.keys()==ff.keys()
 requests={}
 for rec in json.loads(a.manifest.read_text())['manifest']:
  for c in rec['changes']:requests.setdefault((rec['uuid'],c['pad_id']),{}).update(c['after'])
 for c in json.loads(a.npth_requests.read_text())['requests']:requests.setdefault((c['footprint_uuid'],c['pad_id']),{}).update(c['set'])
 def equivalent(actual,target):
  if isinstance(target,dict):return actual.keys()==target.keys()and all(equivalent(actual[k],v)for k,v in target.items())
  return actual==target or(isinstance(target,(float,int))and not isinstance(target,bool)and actual==round(target,4))
 fpchanges=[];seen=set();normalizations=[]
 for fid in bf:
  for k in bf[fid].keys()|ff[fid].keys():
   x=bf[fid].get(k);y=ff[fid].get(k)
   if x==y:continue
   if k[0]=='DOCHEAD':continue
   patch=requests.get((fid,k[1]),{}) if k[0]=='PAD' else {};changed=[key for key in (x or{}).keys()|(y or{}).keys()if (x or{}).get(key)!=(y or{}).get(key)]
   assert all(equivalent(y[key],target)for key,target in patch.items()),(fid,k,patch)
   other=[key for key in changed if key not in patch]
   if other:normalizations.append({'uuid':fid,'type':k[0],'id':k[1],'fields':{key:{'before':(x or{}).get(key),'after':(y or{}).get(key)}for key in other}})
   if patch:seen.add((fid,k[1]));fpchanges.append({'uuid':fid,'pad':k[1],'fields':changed})
 for(fid,pid),patch in requests.items():assert all(equivalent(ff[fid]['PAD',pid][key],val)for key,val in patch.items())
 result={'status':'PASS_BOARD_DELTA_AND_REQUESTED_LIBRARY_FIELDS','source_changes':changes,'attribute_binding_relocations':renames,'additional_hidden_unpositioned_library_attributes':extras,'all_component_positions_tracks_vias_nets_pad_nets_and_rules_unchanged':True,'footprint_documents':len(ff),'repaired_pad_records_checked':len(requests),'footprint_changes':fpchanges,'additional_library_serialization_changes':normalizations,'additional_library_changes_scope':'Recorded for review, not asserted byte-identical. All manufacturing pad fields and actual CAM are covered by independent footprint/mask/copper/paste audits; hidden attributes/UI defaults/noncopper poly rounding may normalize on library update.','quantization_policy':'Accept exact requested metadata or 4-decimal-mil source serialization. Actual CAM geometry checked independently.','inputs':{str(v):hashlib.sha256(v.read_bytes()).hexdigest()for k,v in vars(a).items()if k!='report'}}
 a.report.write_text(json.dumps(result,indent=2)+'\n');print('PASS',len(changes),'source deltas',len(requests),'repaired PAD records')
if __name__=='__main__':main()

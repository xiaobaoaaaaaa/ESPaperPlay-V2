#!/usr/bin/env python3
"""Read-only native-connectivity copper-path width/resistance review; no thermal qualification."""
from pathlib import Path
import argparse,collections,hashlib,heapq,json,math
import pcbnew as P
ROOT=next(p for p in Path(__file__).resolve().parents if (p/'hardware/devboard-r0').is_dir())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def uid(x):return x.m_Uuid.AsString()
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--board',type=Path,required=True);ap.add_argument('--rules',type=Path,default=Path(__file__).with_name('power-route-budget-rules.json'));ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
 rules=json.loads(a.rules.read_text());m=rules['material_assumptions'];rho=m['copper_resistivity_20C_ohm_m'];thick=m['outer_copper_thickness_um']*1e-6;factor=1+m['copper_temperature_coefficient_per_C']*(m['stress_calculation_temperature_C']-20)
 b=P.LoadBoard(str(a.board));b.BuildConnectivity();c=b.GetConnectivity();objs={};refs=collections.defaultdict(list)
 for f in b.GetFootprints():
  for p in f.Pads():
   if not p.GetNumber():continue
   objs[uid(p)]=p;refs[f.GetReference()+'.'+p.GetNumber()].append(uid(p))
 for t in b.GetTracks():objs[uid(t)]=t
 costs={};lengths={};widths={};types={};adj={}
 for k,o in objs.items():
  if isinstance(o,P.PCB_VIA):
   hole=P.ToMM(o.GetDrillValue())*1e-3;wall=m['via_finished_hole_plating_um']*1e-6;area=math.pi*((hole/2+wall)**2-(hole/2)**2);costs[k]=rho*(m['via_length_mm']*1e-3)/area;lengths[k]=0;types[k]='via'
  elif isinstance(o,P.PCB_TRACK):
   length=P.ToMM(o.GetLength());width=P.ToMM(o.GetWidth());costs[k]=rho*(length*1e-3)/(width*1e-3*thick);lengths[k]=length;widths[k]=width;types[k]='track'
  else:costs[k]=0;lengths[k]=0;types[k]='pad'
  neighbors=list(c.GetConnectedTracks(o))+list(c.GetConnectedPads(o));adj[k]=set(uid(n) for n in neighbors if uid(n)!=k and uid(n) in objs and n.GetNetCode()==o.GetNetCode())
 rows=[]; findings=[];missing=[]
 for rule in rules['path_rules']:
  starts=refs[rule['from']];ends=set(refs[rule['to']]);row=dict(rule)
  if not starts or not ends:row['status']='MISSING_PAD';missing.append(rule['id']);rows.append(row);continue
  netnames={objs[k].GetNetname() for k in starts+list(ends)};row['net_names']=sorted(netnames)
  if len(netnames)!=1:row['status']='MISMATCHED_NETS';missing.append(rule['id']);rows.append(row);continue
  distances={s:0 for s in starts};prev={};q=[(0,s) for s in starts];heapq.heapify(q);found=None
  while q:
   distance,k=heapq.heappop(q)
   if distance>distances[k]:continue
   if k in ends:found=k;break
   for other in adj[k]:
    nd=distance+costs[other]
    if nd<distances.get(other,math.inf):distances[other]=nd;prev[other]=k;heapq.heappush(q,(nd,other))
  if found is None:row['status']='UNCONNECTED';missing.append(rule['id']);rows.append(row);continue
  chain=[found]
  while chain[-1] not in starts:chain.append(prev[chain[-1]])
  chain.reverse();path_tracks=[k for k in chain if types[k]=='track'];vias=[k for k in chain if types[k]=='via'];narrow=[k for k in path_tracks if widths[k]+1e-6<rule['trunk_min_mm']];r20=distances[found]*1000
  row.update(status='CONNECTED',track_length_mm=round(sum(lengths[k] for k in path_tracks),3),via_count=len(vias),minimum_track_width_mm=min((widths[k] for k in path_tracks),default=None),sub_target_length_mm=round(sum(lengths[k] for k in narrow),3),copper_path_R20_mohm=round(r20,3),copper_path_R85_mohm=round(r20*factor,3),voltage_drop_per_amp_mV=round(r20,3),path_uuids=chain)
  reviews=[]
  if r20>rule['review_R20_mohm']:reviews.append('copper_resistance_above_review_target')
  if row['sub_target_length_mm']>rule['narrow_allowance_mm']:reviews.append('narrow_path_length_above_review_allowance')
  blocked={k for ref in rule.get('avoid_intermediate_pads',[]) for k in refs[ref]}
  touching_blocked=set(blocked.intersection(chain))
  for k in path_tracks+vias:
   touching_blocked.update(uid(p) for p in c.GetConnectedPads(objs[k]) if uid(p) in blocked)
  if touching_blocked:
   reviews.append('high_current_path_uses_quiet_gauge_pad')
   row['quiet_gauge_pad_contacts']=sorted(touching_blocked)
  row['review_findings']=reviews
  if reviews:findings.append({'id':rule['id'],'findings':reviews})
  rows.append(row)
 out={'status':'INCOMPLETE_CONNECTIVITY' if missing else 'REVIEW_REQUIRED' if findings else 'PASS_COPPER_PATH_REVIEW','board_sha256':sha(a.board),'rules_sha256':sha(a.rules),'material_assumptions':m,'path_count':len(rows),'unconnected_or_invalid_paths':missing,'review_findings':findings,'paths':rows,'limitations':rules['limitations']}
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:out[k] for k in ['status','path_count','unconnected_or_invalid_paths','review_findings']}))
 return 0
if __name__=='__main__':raise SystemExit(main())

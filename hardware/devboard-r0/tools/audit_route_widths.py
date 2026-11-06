#!/usr/bin/env python3
"""Read-only native route width/length audit; geometry statistics, not ampacity validation."""
from pathlib import Path
from collections import defaultdict
import argparse,json,math,hashlib
import pcbnew as P
p=argparse.ArgumentParser(description=__doc__);p.add_argument('board',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--project',type=Path);p.add_argument('--nominal-widths',type=Path);args=p.parse_args()
b=P.LoadBoard(str(args.board));mm=P.ToMM
project=args.project or args.board.with_suffix('.kicad_pro')
classes={x['name']:x.get('track_width') for x in json.loads(project.read_text()).get('net_settings',{}).get('classes',[])} if project.exists() else {}
overrides=json.loads(args.nominal_widths.read_text()) if args.nominal_widths else {}
pads=defaultdict(list)
for f in b.GetFootprints():
 for pad in f.Pads():
  q=pad.GetPosition();pads[pad.GetNetname()].append((f.GetReference()+'.'+pad.GetNumber(),mm(q.x),mm(q.y)))
def point(v):return [round(mm(v.x),6),round(mm(v.y),6)]
def nearest(net,q):
 arr=pads[net]
 if not arr:return None
 ref,x,y=min(arr,key=lambda a:math.hypot(a[1]-q[0],a[2]-q[1]));return {'pad':ref,'distance_mm':round(math.hypot(x-q[0],y-q[1]),4)}
nets={};vias=[];internal=[]
for t in b.GetTracks():
 name=t.GetNetname()
 if t.GetClass()=='PCB_VIA':
  vias.append({'net':name,'position_mm':point(t.GetPosition()),'diameter_mm':mm(t.GetWidth(P.F_Cu)),'drill_mm':mm(t.GetDrillValue()),'locked':t.IsLocked()});continue
 layer=b.GetLayerName(t.GetLayer());width=mm(t.GetWidth());length=mm(t.GetLength());nominal=overrides.get(name,classes.get(str(t.GetNetClassName())));start=point(t.GetStart());end=point(t.GetEnd())
 d=nets.setdefault(name,{'netclass':str(t.GetNetClassName()),'nominal_width_mm':nominal,'total_length_mm':0,'length_by_width_mm':defaultdict(float),'length_by_layer_mm':defaultdict(float),'below_nominal_total_length_mm':0,'below_nominal_segments':[]})
 d['total_length_mm']+=length;d['length_by_width_mm'][str(round(width,6))]+=length;d['length_by_layer_mm'][layer]+=length
 if nominal is not None and width<nominal-.001:
  d['below_nominal_total_length_mm']+=length;d['below_nominal_segments'].append({'layer':layer,'width_mm':width,'length_mm':round(length,6),'start_mm':start,'end_mm':end,'locked':t.IsLocked(),'start_nearest_same_net_pad':nearest(name,start),'end_nearest_same_net_pad':nearest(name,end)})
 if t.GetLayer() not in [P.F_Cu,P.B_Cu]:internal.append({'net':name,'layer':layer,'start_mm':start,'end_mm':end})
for d in nets.values():
 for key in ['total_length_mm','below_nominal_total_length_mm']:d[key]=round(d[key],6)
 for key in ['length_by_width_mm','length_by_layer_mm']:d[key]={k:round(v,6) for k,v in sorted(d[key].items())}
result={'board_sha256':hashlib.sha256(args.board.read_bytes()).hexdigest(),'scope':'Read-only geometry audit; no ampacity/thermal or signal-integrity certification. Below-nominal compares supplied/project netclass width with1um rounding allowance (null if unavailable); short necks are not automatically accepted.','routed_nets':len(nets),'nets':dict(sorted(nets.items())),'vias':vias,'internal_layer_tracks':internal}
args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'routed_nets':len(nets),'vias':len(vias),'internal_tracks':len(internal),'report':str(args.output)}))

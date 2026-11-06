#!/usr/bin/env python3
"""Read-only native KiCad signal paths: centerline length, pad access and layer transitions.
Uses actual segments/vias, not authored routing JSON. No board changes.
"""
from pathlib import Path
import argparse,json,math,heapq,hashlib
from collections import defaultdict,Counter
import pcbnew as P

def mm(v):return P.ToMM(v)
def xy(p):return (round(mm(p.x),6),round(mm(p.y),6))
def vv(p):return P.VECTOR2I(P.FromMM(p[0]),P.FromMM(p[1]))
def projection(q,a,z):
 dx=z[0]-a[0];dy=z[1]-a[1];den=dx*dx+dy*dy
 if not den:return a,0,math.dist(q,a)
 t=((q[0]-a[0])*dx+(q[1]-a[1])*dy)/den
 qp=(a[0]+t*dx,a[1]+t*dy)
 return qp,t,math.dist(q,qp)
def intersection(a,b,c,d):
 u=(b[0]-a[0],b[1]-a[1]);v=(d[0]-c[0],d[1]-c[1]);den=u[0]*v[1]-u[1]*v[0]
 if abs(den)<1e-10:return None
 w=(c[0]-a[0],c[1]-a[1]);t=(w[0]*v[1]-w[1]*v[0])/den;s=(w[0]*u[1]-w[1]*u[0])/den
 if -1e-6<=t<=1+1e-6 and -1e-6<=s<=1+1e-6:return (round(a[0]+t*u[0],6),round(a[1]+t*u[1],6))
 return None

def net_graph(board,net):
 graph=defaultdict(list);pads={};tracks=[];vias=[];points=defaultdict(set)
 layers={P.F_Cu,P.B_Cu}
 def node(layer,q):return ('xy',int(layer),round(q[0],6),round(q[1],6))
 def edge(a,z,w,detail):
  if a==z:return
  graph[a].append((z,w,detail));graph[z].append((a,w,detail))
 for t in board.GetTracks():
  if str(t.GetNetname())!=net:continue
  if isinstance(t,P.PCB_VIA):
   vias.append(t);q=xy(t.GetPosition())
   for l in layers:
    if t.IsOnLayer(l):points[l].add(q)
  elif isinstance(t,P.PCB_TRACK):
   if isinstance(t,P.PCB_ARC):raise RuntimeError('Critical-path arc unsupported; sample it explicitly before using this checker.')
   l=t.GetLayer();layers.add(l);a=xy(t.GetStart());z=xy(t.GetEnd());tracks.append((t,l,a,z));points[l]|={a,z}
 for f in board.GetFootprints():
  for p in f.Pads():
   if str(p.GetNetname())==net:
    key=f'{f.GetReference()}.{p.GetNumber()}'
    pads[key]=p
    for l in layers:
     if p.IsOnLayer(l):points[l].add(xy(p.GetPosition()))
 # Build exact centerline intersections and pad entry projections.
 for i,(t,l,a,z) in enumerate(tracks):
  for ot,ol,c,d in tracks[i+1:]:
   if ol==l:
    q=intersection(a,z,c,d)
    if q:points[l].add(q)
  for p in pads.values():
   if not p.IsOnLayer(l):continue
   q,tv,dist=projection(xy(p.GetPosition()),a,z)
   if -1e-6<=tv<=1+1e-6 and p.GetEffectiveShape(l).Collide(vv(q),P.FromMM(.000002)):
    points[l].add((round(q[0],6),round(q[1],6)))
 for t,l,a,z in tracks:
  cuts=[]
  for q in points[l]:
   _,tv,dist=projection(q,a,z)
   if -1e-5<=tv<=1+1e-5 and dist<.00001:cuts.append((max(0,min(1,tv)),q))
  cuts.sort()
  info={'kind':'track','uuid':str(t.m_Uuid.AsString()),'layer':board.GetLayerName(l),'width_mm':mm(t.GetWidth())}
  for (_,q),(_,r) in zip(cuts,cuts[1:]):edge(node(l,q),node(l,r),math.dist(q,r),info)
 # Via vertical length uses nominal board thickness, conservative F-B model.
 thick=mm(board.GetDesignSettings().GetBoardThickness())
 for v in vias:
  q=xy(v.GetPosition());active=[l for l in layers if v.IsOnLayer(l)]
  for i,l in enumerate(active):
   for m in active[i+1:]:
    edge(node(l,q),node(m,q),thick if {l,m}=={P.F_Cu,P.B_Cu} else thick/2,{'kind':'via','uuid':str(v.m_Uuid.AsString()),'at_mm':q,'from_layer':board.GetLayerName(l),'to_layer':board.GetLayerName(m)})
 for key,p in pads.items():
  center=xy(p.GetPosition());active=[l for l in layers if p.IsOnLayer(l)]
  for l in active:
   pn=('pad',key,int(l));graph[pn]
   for q in points[l]:
    if p.GetEffectiveShape(l).Collide(vv(q),P.FromMM(.000002)):
     edge(pn,node(l,q),math.dist(center,q),{'kind':'pad_access','pad':key,'layer':board.GetLayerName(l)})
  if p.GetAttribute()==P.PAD_ATTRIB_PTH:
   for i,l in enumerate(active):
    for m in active[i+1:]:edge(('pad',key,int(l)),('pad',key,int(m)),thick,{'kind':'pth_barrel','pad':key,'from_layer':board.GetLayerName(l),'to_layer':board.GetLayerName(m)})
 return graph,pads

def shortest(graph,start,end):
 q=[(0,0,start)];dist={start:0};prev={};seq=0
 while q:
  d,_,n=heapq.heappop(q)
  if d!=dist[n]:continue
  if n==end:break
  for other,w,meta in graph[n]:
   nd=d+w
   if nd+1e-9<dist.get(other,float('inf')):
    dist[other]=nd;prev[other]=(n,w,meta);seq+=1;heapq.heappush(q,(nd,seq,other))
 if end not in dist:return {'status':'UNCONNECTED','start':str(start),'end':str(end)}
 n=end;path=[]
 while n!=start:
  old,w,meta=prev[n];path.append({'from':old,'to':n,'length_mm':w,**meta});n=old
 path.reverse();counts=Counter(e['kind'] for e in path)
 return {'status':'CONNECTED','length_mm':dist[end],'planar_mm':sum(e['length_mm'] for e in path if e['kind'] in {'track','pad_access'}),'vertical_mm':sum(e['length_mm'] for e in path if e['kind'] in {'via','pth_barrel'}),'layer_transitions':counts['via']+counts['pth_barrel'],'layers':sorted({e['layer'] for e in path if 'layer' in e}),'path':path}

class Analyzer:
 def __init__(self,board):
  self.b=board;self.fp={f.GetReference():f for f in board.GetFootprints()};self.cache={}
 def pad(self,key):
  ref,pin=key.split('.');return next(p for p in self.fp[ref].Pads() if p.GetNumber()==pin)
 def route(self,start,end):
  pn=self.pad(start);qn=self.pad(end);net=str(pn.GetNetname());assert net==str(qn.GetNetname()),(start,end,net,str(qn.GetNetname()))
  if net not in self.cache:self.cache[net]=net_graph(self.b,net)
  graph,pads=self.cache[net];r=shortest(graph,('pad',start,int(P.F_Cu)),('pad',end,int(P.F_Cu)));r.update(net=net,from_pad=start,to_pad=end);return r

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('board',type=Path);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();b=P.LoadBoard(str(a.board));an=Analyzer(b)
 sd_map={'CLK':['U301.31','R710.1','R710.2','U701.2','U701.3','J701.5','J302.3'],'CMD':['U301.32','R711.1','R711.2','U701.5','U701.6','J701.3','J302.4'],'D0':['U301.24','R712.1','R712.2','U701.9','U701.8','J701.7','J302.5'],'D1':['U301.25','R713.1','R713.2','U701.12','U701.11','J701.8','J302.6'],'D2':['U301.34','R714.1','R714.2','U706.2','U706.3','J701.1','J302.7'],'D3':['U301.33','R715.1','R715.2','U706.5','U706.6','J701.2','J302.8']}
 out={'scope':'Native routed centerline path analysis; no field solver, timing or SI certification','board':str(a.board),'board_sha256':hashlib.sha256(a.board.read_bytes()).hexdigest(),'length_model':'Shortest centerline track path plus pad-center access; F-B vias and PTH barrels count nominal board thickness. Series component internal lengths/delays are excluded.','SD':{},'USB':{}}
 for name,ps in sd_map.items():
  segs=[an.route(ps[i],ps[i+1]) for i in (0,2,4)];entry_debug=an.route(ps[0],ps[6]);debug_res=an.route(ps[6],ps[1]);connected=all(x['status']=='CONNECTED' for x in segs+[entry_debug,debug_res]);r={'connected':connected,'segments':segs,'debug_mcu_path':entry_debug,'debug_resistor_path':debug_res}
  if connected:
   total=sum(x['length_mm'] for x in segs);stub=max(0,(entry_debug['length_mm']+debug_res['length_mm']-segs[0]['length_mm'])/2)
   r.update(main_total_mm=total,main_planar_mm=sum(x['planar_mm'] for x in segs),main_vertical_mm=sum(x['vertical_mm'] for x in segs),main_layer_transitions=sum(x['layer_transitions'] for x in segs),debug_stub_estimate_mm=stub,within_50_8mm=total<=50.8)
  out['SD'][name]=r
 if out['SD']['CLK']['connected']:
  clk=out['SD']['CLK']['main_total_mm']
  for r in out['SD'].values():
   if r['connected']:r.update(skew_from_clk_mm=r['main_total_mm']-clk,within_1_27mm_skew=abs(r['main_total_mm']-clk)<=1.27)
 for polarity,esd,res,mcu in [('DP','U501.1','R503','U301.14'),('DM','U501.2','R504','U301.13')]:
  pair=[an.route(esd,res+'.1'),an.route(res+'.2',mcu)];out['USB'][polarity]={'ESD_to_MCU_segments':pair}
  for contact in (['J501.A6','J501.B6'] if polarity=='DP' else ['J501.A7','J501.B7']):
   route=an.route(contact,esd);tot=sum(p['length_mm'] for p in pair+[route]) if all(p['status']=='CONNECTED' for p in pair+[route]) else None
   out['USB'][polarity][contact]={'contact_to_ESD':route,'total_to_MCU_mm':tot}
  for cap in (['C501.1'] if polarity=='DP' else ['C502.1']):
   left=an.route(res+'.2',cap);right=an.route(cap,mcu)
   if all(p['status']=='CONNECTED' for p in [left,right,pair[1]]):out['USB'][polarity]['DNP_cap_stub_mm']=max(0,(left['length_mm']+right['length_mm']-pair[1]['length_mm'])/2)
 for orientation in ['A','B']:
  pp=out['USB']['DP'][f'J501.{orientation}6']['total_to_MCU_mm'];pn=out['USB']['DM'][f'J501.{orientation}7']['total_to_MCU_mm']
  out['USB'][orientation+'_contact_pair_skew_mm']=None if pp is None or pn is None else pp-pn
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2)+'\n')
 print(json.dumps({'SD':{k:{x:v for x,v in r.items() if x not in ['segments','debug_mcu_path','debug_resistor_path']} for k,r in out['SD'].items()},'USB_skews':{k:v for k,v in out['USB'].items() if k.endswith('_skew_mm')}},indent=2))
if __name__=='__main__':main()

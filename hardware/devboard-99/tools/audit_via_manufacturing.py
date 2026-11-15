#!/usr/bin/env python3
"""Read-only KiCad audit of ordinary-via mask distance and ALL physical hole gaps.
Only U101's four footprint pad17 thermal holes and U301's twelve footprint
pad41 holes are recorded as intentional in-pad holes; no PCB_VIA is exempt.
"""
from pathlib import Path
import argparse,hashlib,json,math
import pcbnew as P
from shapely.geometry import Polygon,Point,GeometryCollection
from shapely.ops import unary_union
from shapely.strtree import STRtree
ERROR=.000005

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def xy(v):return [round(v.x/1e6,6),round(v.y/1e6,6)]
def polyshape(ps):
 gs=[]
 for i in range(ps.OutlineCount()):
  q=ps.COutline(i);outer=[xy(q.CPoint(j))for j in range(q.PointCount())];holes=[]
  for h in range(ps.HoleCount(i)):
   q=ps.CHole(i,h);holes.append([xy(q.CPoint(j))for j in range(q.PointCount())])
  if len(outer)>=3:gs.append(Polygon(outer,holes))
 return unary_union(gs)if gs else GeometryCollection()
def shape(o,l):
 ps=P.SHAPE_POLY_SET();o.TransformShapeToPolygon(ps,l,0,P.FromMM(ERROR),P.ERROR_OUTSIDE);return polyshape(ps)
def pad_hole(p):
 ps=P.SHAPE_POLY_SET();p.TransformHoleToPolygon(ps,0,P.FromMM(ERROR),P.ERROR_OUTSIDE);return polyshape(ps)
def circle(pos,r):return Point(pos).buffer(r/math.cos(math.pi/(4*512)),quad_segs=512)
def inventory(b):
 masks=[];holes=[];vias=[];exempt=[]
 for f in b.GetFootprints():
  for p in f.Pads():
   rec={'uuid':p.m_Uuid.AsString(),'kind':'footprint_pad','ref':f.GetReference(),'pad':p.GetNumber(),'net':p.GetNetname(),'position_mm':xy(p.GetPosition())}
   if p.GetDrillSize().x or p.GetDrillSize().y:
    h={**rec,'geometry':pad_hole(p),'drill_mm':xy(p.GetDrillSize()),'plated':p.GetAttribute()!=P.PAD_ATTRIB_NPTH};holes.append(h)
    if (f.GetReference(),p.GetNumber())in [('U101','17'),('U301','41')]:
     assert p.GetNetname()=='GND' and xy(p.GetDrillSize())==[.3,.3] and xy(p.GetSize())==[.6,.6]
     exempt.append({k:v for k,v in h.items()if k!='geometry'})
   for mask,cu in [(P.F_Mask,P.F_Cu),(P.B_Mask,P.B_Cu)]:
    if p.IsOnLayer(mask):
     g=shape(p,cu).buffer(P.ToMM(p.GetSolderMaskExpansion(mask)),quad_segs=256)
     if not g.is_empty:masks.append({**rec,'side':b.GetLayerName(mask),'geometry':g,'copper':shape(p,cu),'smd':p.GetAttribute()==P.PAD_ATTRIB_SMD})
  for item in f.GraphicalItems():
   if item.GetLayer() in [P.F_Mask,P.B_Mask]and hasattr(item,'TransformShapeToPolygon'):
    g=shape(item,item.GetLayer())
    if not g.is_empty:masks.append({'uuid':item.m_Uuid.AsString(),'kind':'footprint_mask_graphic','ref':f.GetReference(),'pad':'','net':'','side':item.GetLayerName(),'geometry':g,'smd':False})
 for item in b.GetDrawings():
  if item.GetLayer() in [P.F_Mask,P.B_Mask]and hasattr(item,'TransformShapeToPolygon'):
   g=shape(item,item.GetLayer())
   if not g.is_empty:masks.append({'uuid':item.m_Uuid.AsString(),'kind':'board_mask_graphic','ref':'','pad':'','net':'','side':item.GetLayerName(),'geometry':g,'smd':False})
 for t in b.GetTracks():
  if t.GetClass()!='PCB_VIA':continue
  rec={'uuid':t.m_Uuid.AsString(),'kind':'ordinary_board_via','net':t.GetNetname(),'position_mm':xy(t.GetPosition()),'drill_mm':P.ToMM(t.GetDrillValue()),'land_mm':P.ToMM(t.GetWidth(P.F_Cu)),'locked':t.IsLocked(),'geometry':circle(xy(t.GetPosition()),P.ToMM(t.GetDrillValue())/2)}
  vias.append(rec);holes.append(rec)
 return masks,holes,vias,exempt

def audit(path):
 path=Path(path).resolve();h=sha(path);b=P.LoadBoard(str(path));masks,holes,vias,exempt=inventory(b)
 clean=lambda q:{k:v for k,v in q.items()if k not in ['geometry','copper']}
 assert sum(x['ref']=='U101'for x in exempt)==4 and sum(x['ref']=='U301'for x in exempt)==12,'Expected r13 in-pad footprint holes missing/changed'
 trees={side:([x for x in masks if x['side']==side],None)for side in ['F.Mask','B.Mask']}
 trees={s:(v,STRtree([x['geometry']for x in v]))for s,(v,_)in trees.items()}
 rows=[];violations=[]
 for v in vias:
  row=clean(v);row['nearest_mask_by_side']={}
  for side,(ms,tree)in trees.items():
   ids,dist=tree.query_nearest(v['geometry'],all_matches=False,return_distance=True);i=int(ids[0]);m=ms[i]
   near={**clean(m),'hole_edge_gap_mm':float(dist[0]),'same_net':bool(v['net'])and v['net']==m['net'],'drill_intersection_mm2':v['geometry'].intersection(m['geometry']).area}
   if m.get('smd'):near['drill_intersects_SMT_copper']=v['geometry'].intersection(m['copper']).area>1e-10
   row['nearest_mask_by_side'][side]=near
  row['minimum_hole_mask_gap_mm']=min(x['hole_edge_gap_mm']for x in row['nearest_mask_by_side'].values());row['pass']=row['minimum_hole_mask_gap_mm']>=.20-ERROR
  rows.append(row)
  if not row['pass']:violations.append(row)
 ht=STRtree([x['geometry']for x in holes]);pairs=[];close=[]
 for i,a in enumerate(holes):
  for j in ht.query(a['geometry'].buffer(.35)):
   j=int(j)
   if j<=i:continue
   bb=holes[j];gap=a['geometry'].distance(bb['geometry']);row={'a':clean(a),'b':clean(bb),'hole_edge_gap_mm':gap,'pass':gap>=.254-2*ERROR};close.append(row)
   if not row['pass']:pairs.append(row)
 assert sha(path)==h
 return {'status':'PASS_NOMINAL_VIA_MANUFACTURING_GEOMETRY'if not violations and not pairs else'FAIL','source':str(path),'source_sha256':h,'source_unchanged':True,'geometry_error_mm':ERROR,'thresholds_mm':{'ordinary_via_drill_edge_to_F_and_B_pad_mask':.20,'all_drill_edge_to_drill_edge':.254},'scope':'Nominal native artwork, not fabrication tolerance or electrical/thermal qualification. No PCB_VIA is exempt, including external thermal vias. Component-lead PTH/NPTH holes are not ordinary vias but are included in all hole-to-hole checks.','ordinary_via_count':len(vias),'physical_hole_count':len(holes),'mask_object_count':len(masks),'intentional_in_pad_footprint_holes':exempt,'ordinary_via_mask_violations':violations,'hole_to_hole_violations':pairs,'ordinary_vias':rows,'nearby_hole_pairs_within_0_35mm':close,'minimum_ordinary_via_hole_to_mask_mm':min((x['minimum_hole_mask_gap_mm']for x in rows),default=None),'minimum_nearby_hole_gap_mm':min((x['hole_edge_gap_mm']for x in close),default=None)}
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--input',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();r=audit(a.input);a.output.parent.mkdir(exist_ok=True,parents=True);a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:r[k]for k in ['status','ordinary_via_count','physical_hole_count','minimum_ordinary_via_hole_to_mask_mm','minimum_nearby_hole_gap_mm']},indent=2));print('violations:',len(r['ordinary_via_mask_violations']),len(r['hole_to_hole_violations']))

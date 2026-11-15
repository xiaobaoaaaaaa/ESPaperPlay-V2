#!/usr/bin/env python3
"""Independent read-only operation-envelope cross-check against current board geometry."""
import argparse,hashlib,json,math
from pathlib import Path
import pcbnew as P
from shapely.geometry import Polygon,Point,box,GeometryCollection
from shapely.ops import unary_union

def poly(ps):
 out=[]
 for i in range(ps.OutlineCount()):
  q=ps.COutline(i);points=[(q.CPoint(k).x/1e6,q.CPoint(k).y/1e6)for k in range(q.PointCount())]
  holes=[]
  for j in range(ps.HoleCount(i)):
   h=ps.CHole(i,j);holes.append([(h.CPoint(k).x/1e6,h.CPoint(k).y/1e6)for k in range(h.PointCount())])
  if len(points)>=3:out.append(Polygon(points,holes))
 return unary_union(out)if out else GeometryCollection()
def padpoly(p):
 ps=P.SHAPE_POLY_SET();p.TransformShapeToPolygon(ps,P.F_Cu,0,P.FromMM(.00005),P.ERROR_INSIDE);return poly(ps)
def shape(e):
 return box(*e['bounds_mm'])if e['shape']=='rect'else Point(e['center_mm']).buffer(e['radius_mm'],quad_segs=256)
def graphic(d):
 if d.GetShape()==P.SHAPE_T_RECT:
  a=d.GetStart();b=d.GetEnd();return box(min(a.x,b.x)/1e6,min(a.y,b.y)/1e6,max(a.x,b.x)/1e6,max(a.y,b.y)/1e6)
 if d.GetShape()==P.SHAPE_T_CIRCLE:
  c=d.GetCenter();return Point(c.x/1e6,c.y/1e6).buffer(d.GetRadius()/1e6,quad_segs=256)
 return GeometryCollection()
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--board',type=Path,required=True);ap.add_argument('--envelopes',type=Path,required=True);ap.add_argument('--report',type=Path,required=True);args=ap.parse_args()
hash_before=hashlib.sha256(args.board.read_bytes()).hexdigest();b=P.LoadBoard(str(args.board));j=json.loads(args.envelopes.read_text());errors=[];results=[]
fps={f.GetReference():f for f in b.GetFootprints()};courtyards={r:poly(f.GetCourtyard(P.F_CrtYd))for r,f in fps.items()};padsets={r:unary_union([padpoly(p)for p in f.Pads()if p.IsOnLayer(P.F_Cu)])for r,f in fps.items()}
outline=P.SHAPE_POLY_SET();b.GetBoardPolygonOutlines(outline,False);board_shape=poly(outline)
groups=[g for g in b.Groups()if g.GetName()=='OPERATION_ACCESS_DOCUMENTATION'];drawings=list(groups[0].GetItems())if len(groups)==1 else[];used=set()
if len(groups)!=1 or len(drawings)!=21:errors.append({'kind':'operation_documentation_group_count','groups':len(groups),'items':len(drawings)})
if hash_before!=j['board_sha256']:errors.append({'kind':'manifest_board_hash_mismatch'})
if len(j['envelopes'])!=21 or len({e['name']for e in j['envelopes']})!=21:errors.append({'kind':'envelope_inventory'})
for e in j['envelopes']:
 g=shape(e);ref=e['reference'];overlaps=[];pads=[]
 if ref not in fps:errors.append({'kind':'missing_owner','ref':ref});continue
 for r,c in courtyards.items():
  if r==ref:continue
  area=g.intersection(c).area
  if area>1e-6:overlaps.append({'ref':r,'area_mm2':area})
  a=g.intersection(padsets[r]).area
  if a>1e-6:pads.append({'ref':r,'area_mm2':a})
 matches=[i for i,d in enumerate(drawings)if d.GetLayer()==P.Dwgs_User and not graphic(d).is_empty and graphic(d).hausdorff_distance(g)<.00001]
 if len(matches)!=1 or matches[0]in used:errors.append({'kind':'Dwgs_User_envelope_mismatch','name':e['name'],'matches':matches})
 else:used.add(matches[0])
 if overlaps or pads:errors.append({'kind':'operation_access_obstructed','name':e['name'],'courtyards':overlaps,'actual_copper_pads':pads})
 nearest=min(({'ref':r,'gap_mm':g.distance(c)}for r,c in courtyards.items()if r!=ref),key=lambda x:x['gap_mm'])
 results.append({'name':e['name'],'owner':ref,'other_courtyard_intersections':overlaps,'other_pad_intersections':pads,'nearest_other_courtyard':nearest,'board_outside_area_mm2':g.difference(board_shape).area,'drawing_matches':matches})
if len(used)!=len(drawings):errors.append({'kind':'unmatched_operation_graphics','indices':sorted(set(range(len(drawings)))-used)})
if hashlib.sha256(args.board.read_bytes()).hexdigest()!=hash_before:errors.append({'kind':'board_changed_during_audit'})
report={'status':'PASS_ENGINEERING_ACCESS_SCOPE'if not errors else'FAIL','method':'Standalone pcbnew+Shapely; reads explicit operation manifest, does not import layout/envelope generators. Owner excluded only; all other front courtyards and actual front copper pads checked, including full off-board antenna courtyard. Verifies each of 21 documented shapes in the PCB Dwgs.User group. Legitimate outside-board access is reported separately, never used as copper/physical footprint edge waiver.','limitations':j['assumptions'],'board_sha256':hash_before,'envelope_manifest_sha256':hashlib.sha256(args.envelopes.read_bytes()).hexdigest(),'envelopes_checked':len(results),'errors':errors,'checks':results}
args.report.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n');print(json.dumps({'status':report['status'],'checked':len(results),'errors':errors},ensure_ascii=False));raise SystemExit(bool(errors))

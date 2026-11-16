#!/usr/bin/env python3
"""Read-only native Gerber copper topology, plated access and source-net audit.
Does not use runtime POURED cache or KiCad geometry. CAM units mm,+Y up.
"""
import argparse,json,tempfile,collections,hashlib,sys
from pathlib import Path
from shapely.geometry import GeometryCollection,Point,box
from shapely.prepared import prep
from shapely.ops import unary_union
from shapely.strtree import STRtree
from native_source_geometry import load_inputs,source_geometry
from native_routed_cam_context import RoutedContext
from native_cam_geometry import Cam,object_geometry,polygons,sha,GEOMETRY_TOL
LAYER_NAMES={1:'F.Cu',2:'B.Cu',15:'In1.Cu',16:'In2.Cu'}

# These retain the original strict area comparisons; no clearance or topology
# tolerance is relaxed by the fast paths below.
MIN_CONTACT_AREA = 1e-8
FULLY_DRILLED_AREA = 1e-9

class LocalDrillCuts:
 """A minus union(D) needs only drills whose bounding boxes meet A.

 STRtree is only a conservative candidate filter: touching/overlapping boxes
 are retained. Every excluded drill is spatially disjoint from the item, so
 omitting it cannot alter the item's set difference. Layer-wide copper still
 subtracts the original complete union, preserving node IDs and polygons.
 """
 def __init__(self,geometries):
  self.geometries=geometries;self.tree=STRtree(geometries)if geometries else None
 def difference(self,g):
  ids=[]if self.tree is None else sorted(int(i)for i in self.tree.query(g))
  if not ids:return g
  local=self.geometries[ids[0]]if len(ids)==1 else unary_union([self.geometries[i]for i in ids])
  return g.difference(local)

def positive_area_probe(original,drilled):
 """Return a proven subset of the source item, not a point-only guess.

 The representative point may be in any remaining component. A 0.0002mm
 square is used only if its *actual area* exceeds the unchanged contact
 threshold and original.covers(square). It need not find every contact:
 callers retain the exact original intersection calculation as fallback.
 """
 if drilled.is_empty:return None
 p=drilled.representative_point();r=.0001
 probe=box(p.x-r,p.y-r,p.x+r,p.y+r)
 return probe if probe.area>MIN_CONTACT_AREA and original.covers(probe)else None

def positive_area_contact(plane,prepared,item,probe=None):
 """Exactly preserve intersection(item).area >1e-8.

 A prepared disjoint predicate proves zero area. A covered positive-area
 subset proves area above threshold. Every other case uses the unchanged
 original intersection, including tiny slivers, point/edge tangencies,
 holes, narrow strips and a source item spanning multiple CAM islands.
 """
 if prepared.disjoint(item):return False
 if probe is not None and prepared.covers(probe):return True
 return plane.intersection(item).area>MIN_CONTACT_AREA

def plated_wall_contact(copper, actual_drill):
 """A plated barrel joins only copper that shares a positive-length drill wall.

 Both geometries come from the same CAM drill polygon: copper has already had
 all actual drill apertures subtracted. An isolated fragment elsewhere in a
 nominal via/land envelope cannot touch this boundary. No gap dilation, point
 snapping, or source-envelope substitution is used; point-only tangency has
 zero length and cannot establish electrical contact.
 """
 return copper.intersection(actual_drill.boundary).length

def run(a):
 src,state,pads,holes,extra,ev=load_inputs(a);items,_,keepouts,board,unparsed=source_geometry(src,pads+extra,holes)
 holes=RoutedContext(a.source,a.state,a.archive).holes
 errors=[];nodes=[];layer_nodes={};drill_matches=[]
 with tempfile.TemporaryDirectory(prefix='native-cam-connectivity-')as td:
  cam=Cam(a.zip,td)
  drill_geometries=[d['geom_world']for d in cam.drills]
  removed_drills=unary_union(drill_geometries);local_drills=LocalDrillCuts(drill_geometries)
  for l,name in LAYER_NAMES.items():
   whole=GeometryCollection();batch=[];pol=None
   def flush():
    nonlocal whole,batch
    if batch:
     g=unary_union(batch);whole=whole.union(g)if pol else whole.difference(g);batch=[]
   for obj in cam.layers[name].objects:
    dark=bool(obj.polarity_dark)
    if pol is not None and dark!=pol:flush()
    pol=dark;batch.append(object_geometry(obj))
   flush();whole=whole.difference(removed_drills);ps=polygons(whole);layer_nodes[l]=list(range(len(nodes),len(nodes)+len(ps)))
   nodes += [{'layer':l,'g':p,'labels':set(),'members':[]}for p in ps]
   print(name,'polygons',len(ps),'area_mm2',round(whole.area,3),flush=True)
   outside=whole.difference(board.buffer(-.30+GEOMETRY_TOL))
   if outside.area>1e-7:errors.append({'kind':'COPPER_EDGE_CLEARANCE','layer':l,'area_mm2':outside.area})
   for k in keepouts:
    if l not in k['layers']:continue
    overlap=whole.intersection(k['g'].buffer(-GEOMETRY_TOL))
    if overlap.area>1e-7:errors.append({'kind':'COPPER_IN_KEEPOUT','layer':l,'keepout':k['id'],'area_mm2':overlap.area})
  parents=list(range(len(nodes)))
  def find(n):
   while parents[n]!=n:parents[n]=parents[parents[n]];n=parents[n]
   return n
  def merge(a,b):parents[find(a)]=find(b)
  trees={l:STRtree([nodes[n]['g']for n in ns])for l,ns in layer_nodes.items()}
  prepared_nodes=[prep(n['g'])for n in nodes]
  def hits(item,probe):
   out=[]
   for l in item['layers']:
    if l not in trees:continue
    for j in trees[l].query(item['g']):
     n=layer_nodes[l][int(j)]
     if positive_area_contact(nodes[n]['g'],prepared_nodes[n],item['g'],probe):out.append(n)
   return out
  # Establish only source-identified plated connections and verify the drill
  # inventory. Pads/traces label real CAM islands, never invent a plane link.
  unused=list(range(len(cam.drills)))
  cam_centers=[Point(d['center_world_mm'])for d in cam.drills]
  for h in holes:
   center=h['g'].centroid
   same=[n for n in unused if cam.drills[n]['plated'] != bool(h.get('npth')) and center.distance(cam_centers[n])<.00015 and h['g'].hausdorff_distance(cam.drills[n]['geom_world'])<.00015]
   if len(same)!=1:errors.append({'kind':'SOURCE_DRILL_NOT_UNIQUE_IN_CAM','id':h['id'],'matches':len(same)})
   else:unused.remove(same[0]);drill_matches.append({'source_id':h['id'],'cam_index':same[0]})
  for n in unused:errors.append({'kind':'CAM_DRILL_NOT_IN_SOURCE','drill':{k:v for k,v in cam.drills[n].items()if k!='geom_world'}})
  drill_by_source={d['source_id']:cam.drills[d['cam_index']]['geom_world']for d in drill_matches}
  plated_wall_checks=[];pad_hit_map={};item_missing=[];fully_drilled_source_items=[]
  for item in items:
   net=item.get('net') or ('__NC__'+item['id'] if item['kind']=='pad' else '')
   if not net:continue
   drilled=local_drills.difference(item['g'])
   if drilled.area<FULLY_DRILLED_AREA:
    fully_drilled_source_items.append({'id':item['id'],'net':net,'kind':item['kind']});continue
   hs=hits(item,positive_area_probe(item['g'],drilled))
   if not hs:item_missing.append(item['id']);continue
   for n in hs:nodes[n]['labels'].add(net);nodes[n]['members'].append(item['id'])
   if item.get('anchor'):
    hid=item['id']+'_hole'
    if hid not in drill_by_source:errors.append({'kind':'PLATED_ACCESS_DRILL_NOT_VERIFIED','id':item['id']})
    else:
     wall_hits=[];checks=[]
     for n in hs:
      contact=plated_wall_contact(nodes[n]['g'],drill_by_source[hid])
      checks.append({'layer':nodes[n]['layer'],'copper_node':n,'shared_wall_length_mm':contact})
      if contact>0:wall_hits.append(n)
      else:errors.append({'kind':'PLATED_ACCESS_COPPER_NOT_AT_DRILL_WALL','id':item['id'],'layer':nodes[n]['layer'],'copper_node':n})
     for n in wall_hits[1:]:merge(wall_hits[0],n)
     plated_wall_checks.append({'id':item['id'],'contacts':checks})
   if item['kind']=='pad':pad_hit_map[item['id']]=hs
  for ident in item_missing:errors.append({'kind':'SOURCE_CONDUCTOR_MISSING_IN_CAM','id':ident})
  groups=collections.defaultdict(list)
  for n in range(len(nodes)):groups[find(n)].append(n)
  labels={root:set().union(*(nodes[n]['labels']for n in ns))for root,ns in groups.items()}
  for root,nets in labels.items():
   if len(nets)>1:errors.append({'kind':'CAM_COPPER_SHORT','nets':sorted(nets),'layers':sorted({nodes[n]['layer']for n in groups[root]}),'members':sorted({m for n in groups[root]for m in nodes[n]['members']})})
  net_roots=collections.defaultdict(set)
  for root,nets in labels.items():
   for net in nets:
    if not net.startswith('__NC__'):net_roots[net].add(root)
  reports={}
  for net,roots in sorted(net_roots.items()):
   reports[net]={'copper_components':len(roots),'islands':[{'layers':sorted({nodes[n]['layer']for n in groups[root]}),'source_members':sorted({m for n in groups[root]for m in nodes[n]['members']})}for root in roots]}
   if len(roots)>1:errors.append({'kind':'CAM_NET_OPEN_OR_ISOLATED_SOURCE_COPPER','net':net,'components':len(roots)})
  orphans=[{'layer':nodes[n]['layer'],'area_mm2':nodes[n]['g'].area}for n in range(len(nodes))if not labels[find(n)]]
  for o in orphans:
   if o['area_mm2']>.02:errors.append({'kind':'UNASSIGNED_CAM_COPPER_ISLAND',**o})
  return {'status':'PASS_NATIVE_CAM_COPPER_TOPOLOGY'if not errors else'FAIL_NATIVE_CAM_COPPER_TOPOLOGY','inputs':{str(p):sha(p)for p in[a.source,a.state,a.archive,a.zip]},'source_inventory':{'components':len(state),'pads':len(pads),'holes':len(holes),'conductors':len(items)},'actual_copper_polygons':{LAYER_NAMES[l]:len(ns)for l,ns in layer_nodes.items()},'connected_copper_groups':len(groups),'verified_drills':len(drill_matches),'plated_wall_checks':plated_wall_checks,'fully_drilled_source_items':fully_drilled_source_items,'nets':reports,'unassigned_polygons':orphans,'errors':errors,'scope':'Actual Gerber copper minus actual drilled apertures, source-net labeling (each NC pad separately isolated), joined only by matching plated drills and positive-length actual copper contact at each actual drill wall; all four copper layers checked against native keepouts and 0.30mm board edge. Runtime POURED ignored.','limits':['This checks ideal CAM geometry, not fabricated copper continuity, plating thickness, solder joints, thermal performance, impedance, or circuit function.','Net labels and pad membership are taken from the native design; independent SCH/PCB netlist equivalence remains required.','Curve approximation error 0.00001mm; drill Hausdorff tolerance 0.00015mm; no copper-gap bridging is applied.'],'CAM_files':cam.files,'duplicate_drill_views':cam.duplicate_drill_views}


def self_test():
 """Positive/negative geometric predicates, including both strict thresholds."""
 cases=[]
 def compare(name,plane,item,drilled=None,expected=None):
  probe=positive_area_probe(item,item if drilled is None else drilled)
  actual=positive_area_contact(plane,prep(plane),item,probe)
  reference=plane.intersection(item).area>MIN_CONTACT_AREA
  assert actual==reference,(name,actual,reference)
  if expected is not None:assert actual==expected,(name,actual,expected)
  cases.append(name)
 plane=box(0,0,1,1)
 compare('interior positive-area subset',plane,box(.2,.2,.8,.8),expected=True)
 compare('edge-only tangency is not contact',plane,box(1,.2,2,.8),expected=False)
 compare('point-only tangency is not contact',plane,box(1,1,2,2),expected=False)
 for width,wanted in[(.5e-8,False),(1e-8,False),(2e-8,True)]:
  compare('strict area threshold '+str(width),plane,box(0,0,width,1),expected=wanted)
 donut=box(-1,-1,1,1).difference(box(-.1,-.1,.1,.1))
 compare('source inside drilled void is absent',donut,box(-.05,-.05,.05,.05),expected=False)
 item=box(-.2,-.2,.2,.2);compare('annular remainder positive',donut,item,item.difference(box(-.1,-.1,.1,.1)),True)
 left,right=box(-1,-1,-.001,1),box(.001,-1,1,1)
 compare('real copper gap stays empty',left.union(right),box(-.0005,-.5,.0005,.5),expected=False)
 spanning=box(-.02,-.1,.02,.1)
 compare('spanning item labels first island separately',left,spanning,expected=True)
 compare('spanning item also labels second island separately',right,spanning,expected=True)
 assert len(polygons(left.union(right)))==2,'Fast predicates must never merge islands'
 drills=[box(0,0,1,1),Point(2,2).buffer(.25),box(100,100,101,101)]
 local=LocalDrillCuts(drills);whole=unary_union(drills)
 for extra in[0,.5e-9,1e-9,2e-9,.01]:
  item=box(0,0,1+extra,1);a=local.difference(item);b=item.difference(whole)
  assert (a.area<FULLY_DRILLED_AREA)==(b.area<FULLY_DRILLED_AREA)
  assert a.symmetric_difference(b).area<1e-14
 cases.append('local drill subtraction preserves strict1e-9 remainder threshold')
 for item in[box(-.5,-.5,.5,.5),box(1,0,2,1),box(1.9,1.9,2.1,2.1),box(20,20,21,21)]:
  assert local.difference(item).symmetric_difference(item.difference(whole)).area<1e-14
 cases.append('local bbox filter retains overlaps and ignores only disjoint drills')
 # Reproduce the former false inter-layer bridge: source via envelope covers
 # both pieces, but an outer top fragment never reaches the physical barrel.
 drill=Point(0,0).buffer(.15,quad_segs=128)
 envelope=Point(0,0).buffer(.30,quad_segs=128)
 annulus=envelope.difference(drill);fragment=box(.22,-.02,.26,.02)
 assert positive_area_contact(fragment,prep(fragment),envelope)
 assert positive_area_contact(annulus,prep(annulus),envelope)
 assert plated_wall_contact(fragment,drill)==0
 assert plated_wall_contact(annulus,drill)>.9
 wall_nodes=[i for i,g in enumerate([fragment,annulus])if plated_wall_contact(g,drill)>0]
 assert wall_nodes==[1], 'Isolated copper fragment must not join through a barrel'
 cases.append('isolated via-envelope fragment cannot bridge copper layers')
 tangent=box(.15,0,.2,.05)
 assert plated_wall_contact(tangent,drill)==0
 cases.append('point-only plated-wall contact cannot bridge copper layers')
 slot=box(-.2,-.4,.2,.4).buffer(.1,quad_segs=128)
 shell=slot.buffer(.2,quad_segs=128).difference(slot)
 assert plated_wall_contact(shell,slot)>2
 cases.append('positive-length actual plated slot wall joins valid shell copper')
 print(json.dumps({'self_test':'PASS','cases':cases}))

def main():
 p=argparse.ArgumentParser()
 for key in['source','state','archive','zip','output']:p.add_argument('--'+key,type=Path)
 p.add_argument('--self-test',action='store_true');a=p.parse_args()
 if a.self_test:self_test();return False
 if not all(getattr(a,key)for key in['source','state','archive','zip','output']):p.error('--source/--state/--archive/--zip/--output required')
 r=run(a);a.output.write_text(json.dumps(r,indent=2));print(r['status'],collections.Counter(e['kind']for e in r['errors']));return bool(r['errors'])
if __name__=='__main__':raise SystemExit(main())

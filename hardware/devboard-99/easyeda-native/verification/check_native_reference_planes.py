#!/usr/bin/env python3
"""Project native signal routes onto the ACTUAL adjacent CAM GND reference planes.

No runtime POUR cache, inferred solid plane, gap bridging, or SI/EM qualification.
Top references Inner1; Bottom references Inner2 in the frozen native four-layer
stack. Ground copper is positively identified by matching source GND plated
access and actual positive-length barrel-wall contact, never by largest area.
"""
import argparse,collections,json,math,tempfile
from pathlib import Path
from shapely.geometry import Point,LineString,GeometryCollection,box
from shapely.ops import unary_union,linemerge,nearest_points
from shapely.strtree import STRtree
from native_cam_geometry import Cam,object_geometry,polygons,sha,GEOMETRY_TOL
from native_routed_cam_context import RoutedContext
from check_native_cam_connectivity import plated_wall_contact,LocalDrillCuts
MM=.0254
LAYER_NAMES={1:'F.Cu',2:'B.Cu',15:'In1.Cu',16:'In2.Cu'}
REFERENCE={1:15,2:16}
USB={'USB_DM_MCU','USB_DM_PORT','USB_DP_MCU','USB_DP_PORT'}
SD={n for s in ['CLK','CMD','D0','D1','D2','D3']for n in ['SD_'+s,'SD_'+s+'_BUS','SD_CARD_'+s]}
AUDIO={'AUDIO_BCLK_BUF','AUDIO_WS_BUF','AUDIO_DIN_BUF','I2S_BCLK_AUDIO','I2S_WS_AUDIO','I2S_DIN_AUDIO','MIC_SD_RAW','AUDIO_SD_BUF','AUDIO_OE_N','I2S_BCLK','I2S_WS','SPEAKER_DATA','MIC_DATA'}
EPD={'EPD_SCLK','EPD_MOSI','EPD_CS','EPD_DC','EPD_RST_N','EPD_BUSY'}|{'EPD_BUF_'+s for s in ['SCLK','MOSI','CS','DC','RST_N']}|{'EPD_PAD_'+s for s in ['SCLK','MOSI','CS','DC','RST_N','BUSY']}
GROUPS={'USB':USB,'SD':SD,'I2S_audio':AUDIO,'EPD':EPD}
SELECTED=set().union(*GROUPS.values())
DETOUR_RADII=[.25,.5,1.,2.,4.,8.]


def line_parts(g):
 if g.is_empty:return []
 if g.geom_type=='LineString':return [g]
 return [p for child in getattr(g,'geoms',[])for p in line_parts(child)]


def cam_copper(cam):
 """Exact polarity sequence; no GND buffer or cache credit."""
 drilled=unary_union([d['geom_world']for d in cam.drills]);out={}
 for layer,name in LAYER_NAMES.items():
  copper=GeometryCollection();batch=[];polarity=None
  def flush():
   nonlocal copper,batch
   if batch:
    g=unary_union(batch);copper=copper.union(g)if polarity else copper.difference(g);batch=[]
  for obj in cam.layers[name].objects:
   dark=bool(obj.polarity_dark)
   if polarity is not None and dark!=polarity:flush()
   polarity=dark;batch.append(object_geometry(obj))
  flush();out[layer]=copper.difference(drilled)
  print('actual CAM',name,len(polygons(out[layer])),'copper polygons',flush=True)
 return out


def ground_planes(context,cam,copper):
 """Identify GND by exact plated drill/source identity and real barrel contact."""
 holes={h['id']:h for h in context.holes};drilltree=STRtree([d['geom_world']for d in cam.drills]);errors=[]
 nodes={l:polygons(copper[l])for l in[15,16]};trees={l:STRtree(gs)for l,gs in nodes.items()};grounds={15:set(),16:set()};access=[]
 for item in context.items:
  if item.get('net')!='GND'or not item.get('anchor'):continue
  hid=item['id']+'_hole';h=holes.get(hid)
  if h is None:errors.append({'kind':'GND_ANCHOR_SOURCE_HOLE_MISSING','id':item['id']});continue
  ids=[int(i)for i in drilltree.query(h['g'].buffer(.00015))]
  matches=[i for i in ids if cam.drills[i]['plated']and h['g'].centroid.distance(cam.drills[i]['geom_world'].centroid)<.00015 and h['g'].hausdorff_distance(cam.drills[i]['geom_world'])<.00015]
  if len(matches)!=1:errors.append({'kind':'GND_ANCHOR_CAM_DRILL_NOT_UNIQUE','id':item['id'],'matches':len(matches)});continue
  drill=cam.drills[matches[0]]['geom_world'];contacts={}
  for l in[15,16]:
   ns=[int(i)for i in trees[l].query(drill)if plated_wall_contact(nodes[l][int(i)],drill)>0]
   grounds[l].update(ns);contacts[l]=ns
  if not all(contacts.values()):errors.append({'kind':'GND_ANCHOR_NOT_ACTUALLY_ON_BOTH_INNER_PLANES','id':item['id'],'contacts':contacts})
  else:access.append({'id':item['id'],'xy_mm':list(drill.centroid.coords[0]),'kind':item['kind'],'contacts':contacts})
 planes={l:unary_union([nodes[l][i]for i in sorted(grounds[l])])for l in[15,16]}
 return planes,access,errors,{'nodes_by_layer':{LAYER_NAMES[l]:sorted(ns)for l,ns in grounds.items()},'actual_GND_area_mm2':{LAYER_NAMES[l]:g.area for l,g in planes.items()}}


def station_probe(chain,station,direction,plane):
 """Find a true positive-area GND probe just outside an unreferenced interval."""
 for distance in[.001,.005,.01,.025,.05,.1,.2]:
  s=station+direction*distance
  if not 0<=s<=chain.length:continue
  q=chain.interpolate(s);probe=box(q.x-.0001,q.y-.0001,q.x+.0001,q.y+.0001)
  if plane.covers(probe):return probe
 return None


def detour_extent(plane,gap,entry,exit):
 """Smallest tested local window with real connected GND between both probes.

 The window is gap.buffer(radius), not a dilation of copper. Intersecting it
 with real GND cannot create a path that crosses a gap. Every same-component
 result requires both positive-area probes to be fully covered by that one
 actual clipped GND polygon. Radius is a spatial extent, not path length.
 """
 if entry is None or exit is None:return None
 for radius in DETOUR_RADII:
  local=plane.intersection(gap.buffer(radius,quad_segs=32))
  if any(p.covers(entry)and p.covers(exit)for p in polygons(local)):return radius
 return None


def analyze_chain(chain,plane,voids,voidtree,holes,transitions,ground_access,net):
 events=[]
 for gap in line_parts(chain.difference(plane)):
  if gap.length<=1e-12:continue
  ss=[chain.project(Point(q))for q in gap.coords];lo,hi=min(ss),max(ss)
  entry=station_probe(chain,lo,-1,plane);exit=station_probe(chain,hi,1,plane)
  radius=detour_extent(plane,gap,entry,exit)
  voidids=[int(i)for i in voidtree.query(gap)if voids[int(i)].intersection(gap).length>1e-12]
  vs=[voids[i]for i in voidids];void=unary_union(vs)
  hs=[h for h in holes if void.covers(h['g'].centroid)]
  own=[t for t in transitions if t['net']==net and void.covers(t['g'].centroid)]
  hole_rows=[{'id':h['id'],'NPTH':bool(h.get('npth')),'xy_mm':list(h['g'].centroid.coords[0])}for h in hs]
  terminal=entry is None or exit is None
  endpoints=([Point(chain.coords[0])]if entry is None else[])+([Point(chain.coords[-1])]if exit is None else[])
  endpoint_own=[t for t in own if any(t['g'].buffer(GEOMETRY_TOL).covers(p)for p in endpoints)]
  return_rows=[]
  for t in (endpoint_own if terminal else own):
   pt=t['g'].centroid
   if ground_access:
    best=min(ground_access,key=lambda g:pt.distance(Point(g['xy_mm'])))
    return_rows.append({'signal_access':t['id'],'ground_access':best['id'],'ground_access_verified_on_both_inner_planes':True,'distance_center_mm':pt.distance(Point(best['xy_mm']))})
  terminal_pth_only=bool(endpoint_own)and all(t['kind']=='pad'and len(t.get('routed_outer_layers',[]))==1 for t in endpoint_own)
  if gap.length<=2*GEOMETRY_TOL:classification='CAM_QUANTIZATION_SCALE_REFERENCE_GAP_REVIEW'
  elif terminal and terminal_pth_only:classification='PTH_SINGLE_LAYER_TERMINAL_ANTIPAD_NO_BOARD_LAYER_CHANGE'
  elif terminal and endpoint_own and return_rows and all(r['distance_center_mm']<=2.00001 for r in return_rows):classification='PLATED_SIGNAL_EXIT_WITH_VERIFIED_LOCAL_GND_RETURN'
  elif terminal:classification='TERMINAL_EXIT_WITHOUT_LOCAL_VERIFIED_RETURN_REVIEW'
  elif radius is not None and radius<=1.:
   classification='LOCAL_SINGLE_APERTURE_DETOUR'if len(hs)==1 else'LOCAL_MULTIPLE_APERTURE_DETOUR'if hs else'LOCAL_NONDRILL_VOID_DETOUR_REVIEW'
  else:classification='LONG_SLOT_OR_ANTIPAD_CHAIN_REVIEW'
  bounds=list(void.bounds)if not void.is_empty else None
  events.append({'classification':classification,'unreferenced_centerline_length_mm':gap.length,'chain_station_mm':[lo,hi],
   'gap_path_mm':[list(q)for q in gap.coords],'void_ids':voidids,'void_bounds_mm':bounds,'void_area_mm2':void.area,
   'actual_holes_in_connected_void':hole_rows,'own_net_plated_access_in_void':[t['id']for t in own],
   'endpoint_plated_access':[{'id':t['id'],'kind':t['kind'],'routed_outer_layers':t.get('routed_outer_layers',[]),'ref':t.get('ref'),'pin':t.get('pin')}for t in endpoint_own],
   'local_GND_return_access':return_rows,'both_entry_and_exit_have_positive_area_GND':entry is not None and exit is not None,
   'minimum_tested_connected_GND_window_radius_mm':radius,'tested_radii_mm':DETOUR_RADII,
   'review_required':classification.endswith('_REVIEW')})
 return events


def actual_void_corridor(ground,a,b,minimum):
 """No envelope prediction: measure separate actual non-GND CAM voids."""
 p,q=nearest_points(a,b);distance=p.distance(q)
 connector=LineString([p,q]) if distance else GeometryCollection()
 missing=connector.difference(ground).length if distance else 0.
 probe=Point((p.x+q.x)/2,(p.y+q.y)/2).buffer(minimum/2,quad_segs=128)
 positive_patch=ground.covers(probe)
 return {'pass':distance>=minimum and missing<1e-9 and positive_patch,'positive_area_GND_patch_diameter_mm':minimum,'positive_area_GND_patch_covered':positive_patch,'actual_GND_channel_mm':distance,
         'minimum_mm':minimum,'nearest_boundary_points_mm':[list(p.coords[0]),list(q.coords[0])],
         'uncovered_between_boundary_points_mm':missing,'same_connected_void':a.equals(b)}

def finite(x):
 if isinstance(x,float)and not math.isfinite(x):return None
 if isinstance(x,dict):return {k:finite(v)for k,v in x.items()}
 if isinstance(x,(list,tuple)):return [finite(v)for v in x]
 return x


def run(a):
 context=RoutedContext(a.source,a.state,a.archive);errors=[];routes=[]
 physical=sorted([{'layer_id':json.loads(i)[1],**b}for(k,i),b in context.source.items()if k=='LAYER_PHYS'],key=lambda r:r['zIndex'])
 copper_order=[r['layer_id']for r in physical if r['layer_id']in LAYER_NAMES]
 if copper_order!=[1,15,16,2]:raise ValueError('Adjacent reference assignment requires actual native copper order1/15/16/2; got '+str(copper_order))
 native_nets={i.get('net')for i in context.items}
 for (kind,ident),b in context.source.items():
  if b.get('netName')not in SELECTED or b.get('layerId')not in[1,2,15,16]:continue
  if kind in['PAD','VIA','COMPONENT']:continue
  if kind!='LINE':errors.append({'kind':'UNSUPPORTED_SELECTED_ROUTE_TYPE','id':ident,'type':kind});continue
  if b['layerId']not in REFERENCE:errors.append({'kind':'SELECTED_SIGNAL_ON_REFERENCE_LAYER','id':ident});continue
  center=LineString([(b['startX']*MM,b['startY']*MM),(b['endX']*MM,b['endY']*MM)])
  routes.append({'id':ident,'net':b['netName'],'layer':b['layerId'],'width_mm':b['width']*MM,'center':center,'g':center.buffer(b['width']*MM/2,quad_segs=32)})
 with tempfile.TemporaryDirectory(prefix='native-reference-plane-')as td:
  cam=Cam(a.zip,td);copper=cam_copper(cam);planes,access,ground_errors,ground_detail=ground_planes(context,cam,copper);errors.extend(ground_errors)
  for l,g in planes.items():
   if g.is_empty:errors.append({'kind':'NO_ACTUAL_VERIFIED_GND_REFERENCE_COPPER','layer':l})
  voids={l:polygons(context.board.difference(g))for l,g in planes.items()};voidtrees={l:STRtree(gs)for l,gs in voids.items()}
  corridor_rules=json.loads(a.corridors.read_text());corridor_checks=[]
  for rule in corridor_rules['pairs']:
   pad=next(p for p in context.pads if p.get('ref')==rule['reference_ref']and str(p.get('pin'))==str(rule['reference_pin']))
   center=pad['g'].centroid
   candidates=[i for i in context.items if i.get('anchor')and i['net']==rule['neighbor_net']and center.distance(i['g'].centroid)<=rule['neighbor_search_radius_mm']]
   if len(candidates)!=rule['expected_neighbor_count']:errors.append({'kind':'CORRIDOR_NEIGHBOR_COUNT_CHANGED','rule':rule['id'],'expected':rule['expected_neighbor_count'],'actual':len(candidates)})
   for layer in rule['layers']:
    def void_at(point):
     found=[int(n)for n in voidtrees[layer].query(point)if voids[layer][int(n)].covers(point)]
     if len(found)!=1:raise ValueError('Expected one actual non-GND CAM aperture for source plated access: '+str(list(point.coords)))
     return voids[layer][found[0]]
    base=void_at(center)
    for other in candidates:
     detail=actual_void_corridor(planes[layer],base,void_at(other['g'].centroid),rule['minimum_actual_GND_channel_mm'])
     detail.update(rule=rule['id'],layer=LAYER_NAMES[layer],reference_pad=pad['id'],neighbor_access=other['id'],neighbor_net=other['net'],neighbor_xy_mm=list(other['g'].centroid.coords[0]))
     corridor_checks.append(detail)
     if not detail['pass']:errors.append({'kind':'ACTUAL_GND_CORRIDOR_TOO_NARROW_OR_INTERRUPTED',**detail})
  transitions=[{**i,'routed_outer_layers':sorted({r['layer']for r in routes if r['net']==i['net']and r['g'].intersects(i['g'])})}for i in context.items if i.get('anchor')and i.get('net')in SELECTED]
  local_drills=LocalDrillCuts([d['geom_world']for d in cam.drills])
  summaries=[];all_events=[];coverage=[]
  expanded={l:copper[l].buffer(GEOMETRY_TOL)for l in[1,2]}
  for r in routes:
   missing=local_drills.difference(r['g']).difference(expanded[r['layer']]).area
   if missing>1e-8:errors.append({'kind':'SOURCE_ROUTE_NOT_COVERED_BY_ACTUAL_CAM','id':r['id'],'net':r['net'],'missing_area_mm2':missing,'CAM_format_tolerance_mm':GEOMETRY_TOL})
  for net in sorted(SELECTED):
   for l,ref in REFERENCE.items():
    rs=[r for r in routes if r['net']==net and r['layer']==l]
    if not rs:continue
    combined=unary_union([r['center']for r in rs]);chains=line_parts(combined if combined.geom_type=='LineString'else linemerge(combined))
    ribbon=unary_union([r['g']for r in rs]).intersection(copper[l]);uncovered=ribbon.difference(planes[ref]);length=sum(c.length for c in chains)
    events=[]
    for index,c in enumerate(chains):
     events.extend([{**e,'net':net,'signal_layer':LAYER_NAMES[l],'reference_layer':LAYER_NAMES[ref],'chain_index':index}for e in analyze_chain(c,planes[ref],voids[ref],voidtrees[ref],context.holes,transitions,access,net)])
    center_missing=sum(e['unreferenced_centerline_length_mm']for e in events)
    summary={'net':net,'signal_layer':LAYER_NAMES[l],'reference_layer':LAYER_NAMES[ref],'native_LINE_count':len(rs),'source_ids':[r['id']for r in rs],
     'unique_centerline_length_mm':length,'trace_ribbon_area_mm2':ribbon.area,'unreferenced_ribbon_area_mm2':uncovered.area,
     'unreferenced_centerline_length_mm':center_missing,'centerline_coverage_percent':100*(1-center_missing/length)if length else None,
     'events':events,'edge_only_reference_relief':bool(uncovered.area>1e-8 and not events)}
    summaries.append(summary);all_events.extend(events)
  review=[e for e in all_events if e['review_required']]
  absent=sorted(SELECTED-{r['net']for r in routes})
  report={'status':'GEOMETRIC_REFERENCE_REVIEW_REQUIRED'if errors or review else'PASS_GEOMETRIC_REFERENCE_SCREEN_WITH_REPORTED_LOCAL_APERTURES',
   'inputs':{str(p):sha(p)for p in[a.source,a.state,a.archive,a.zip,a.corridors]},'actual_reference_corridor_checks':corridor_checks,'selected_signal_groups':{k:sorted(v)for k,v in GROUPS.items()},
   'scope':'Existing actual native USB/SD/I2S/EPD outer-layer LINEs checked against actual adjacent CAM GND; this is not completion of absent/unrouted nets or signal-integrity qualification.',
   'selected_nets_without_any_routed_LINE':absent,'selected_nets_absent_from_native':sorted(SELECTED-native_nets),'route_LINE_count':len(routes),
   'ground_reference_identification':ground_detail,'verified_GND_vertical_access_count':len(access),'reference_layers':{'F.Cu':'In1.Cu','B.Cu':'In2.Cu'},'actual_native_physical_stack':physical,
   'plated_signal_access_outer_layer_incidence':[{'id':t['id'],'net':t['net'],'kind':t['kind'],'ref':t.get('ref'),'pin':t.get('pin'),'routed_outer_layers':t['routed_outer_layers']}for t in transitions],
   'classification_counts':dict(collections.Counter(e['classification']for e in all_events)),'routes':summaries,'review_events':review,'physical_review_events':[e for e in review if e['classification']!='CAM_QUANTIZATION_SCALE_REFERENCE_GAP_REVIEW'],'numerical_scale_review_events':[e for e in review if e['classification']=='CAM_QUANTIZATION_SCALE_REFERENCE_GAP_REVIEW'],'errors':errors,
   'screening_parameters':{'local_GND_window_radii_mm':DETOUR_RADII,'local_detour_screen_max_radius_mm':1.,'plated_exit_return_project_limit_mm':2.,'reference_copper_dilation_mm':0.,'ribbon_and_centerline_geometry':'Actual CAM copper inside each native LINE envelope, excluding actual drills. Native LINE remainder must be covered by actual CAM within format-roundtrip tolerance; actual adjacent GND is never expanded.',
    'classification_note':'1mm local-window and2mm existing via-return screens are project geometric review thresholds, not electromagnetic or industry-standard pass limits. A connected local GND window does not measure current density, detour path length, impedance or timing.'},
   'limitations':['No fabricated continuity, copper/plating thickness, impedance, crosstalk, return-current field, EMI, edge-rate or timing qualification.','Existing routed copper only. Missing nets, terminal connectivity, SCH/PCB equivalence, full CAM topology/shorts and native DRC must pass separately.','A source GND label plus matched actual barrel contact identifies local reference copper; full-board CAM GND-single-group verification remains independently required.','Every missing centerline interval is retained. Small CAM-quantization-scale cases are explicitly flagged, never joined or silently discarded.','A void chain may be long even when the crossed gap is short: connected void extent and actual local GND bypass are both reported.']}
  if a.svg:write_svg(a.svg,planes,routes,all_events)
  return report


def write_svg(path,planes,routes,events):
 colors={'USB':'#de4b27','SD':'#087daf','I2S_audio':'#8b32aa','EPD':'#1d9764'}
 parts=['<svg xmlns="http://www.w3.org/2000/svg" width="2000" height="1080" viewBox="0 0 210 114"><rect width="210" height="114" fill="white"/>']
 for l,ref,offset in[(1,15,3),(2,16,108)]:
  parts.append(f'<text x="{offset}" y="4" font-size="2.5">{LAYER_NAMES[l]} signal / {LAYER_NAMES[ref]} actual GND</text><g transform="translate({offset},106) scale(1,-1)">')
  for p in polygons(planes[ref]):
   p=p.simplify(.001,preserve_topology=True) # Display only; all checks above use unsimplified actual CAM.
   rings=[p.exterior,*p.interiors];d=' '.join('M'+' L'.join(f'{x:.5f},{y+99:.5f}'for x,y in ring.coords)+' Z'for ring in rings)
   parts.append(f'<path d="{d}" fill="#d9dddd" fill-rule="evenodd" stroke="none"/>')
  for r in routes:
   if r['layer']!=l:continue
   group=next(g for g,nets in GROUPS.items()if r['net']in nets);xy=' '.join(f'{x:.5f},{y+99:.5f}'for x,y in r['center'].coords)
   parts.append(f'<polyline points="{xy}" fill="none" stroke="{colors[group]}" stroke-width="{r["width_mm"]:.5f}"/>')
  for e in events:
   if e['signal_layer']!=LAYER_NAMES[l]or not e['review_required']:continue
   p=LineString(e['gap_path_mm']).centroid;parts.append(f'<circle cx="{p.x:.5f}" cy="{p.y+99:.5f}" r="1.0" fill="none" stroke="red" stroke-width=".15"/>')
  parts.append('</g>')
 parts.append('<text x="3" y="112" font-size="2">Red circles: review required. Gray: actual verified GND. Colors: USB orange / SD blue / I2S purple / EPD green. Display simplification only:1um.</text></svg>')
 Path(path).write_text(''.join(parts))


def self_test():
 tests=[];board=box(-10,-10,10,10);chain=LineString([(-5,0),(5,0)])
 def analyze(name,voids,expected,holes=None):
  plane=board.difference(unary_union(voids));void=polygons(board.difference(plane))
  events=analyze_chain(chain,plane,void,STRtree(void),holes or[],[],[],'TEST')
  assert [x['classification']for x in events]==expected,(name,events)
  tests.append({'case':name,'pass':True,'events':events});return events
 analyze('Continuous actual GND yields no missing intervals',[],[])
 circle=Point(0,0).buffer(.45,quad_segs=128);h={'id':'single','g':Point(0,0).buffer(.15),'npth':False}
 ev=analyze('Ordinary single antipad retains bounded local GND bypass',[circle],['LOCAL_SINGLE_APERTURE_DETOUR'],[h]);assert ev[0]['minimum_tested_connected_GND_window_radius_mm']<=.5
 ev=analyze('Globally connected GND does not hide a long perpendicular slot',[box(-.4,-6,.4,6)],['LONG_SLOT_OR_ANTIPAD_CHAIN_REVIEW']);assert ev[0]['minimum_tested_connected_GND_window_radius_mm']==8
 holes=[{'id':str(i),'g':Point(0,i*.7).buffer(.15),'npth':False}for i in range(-8,9)]
 ev=analyze('Connected antipad chain requires remote detour despite short crossing',[Point(0,i*.7).buffer(.45,quad_segs=128)for i in range(-8,9)],['LONG_SLOT_OR_ANTIPAD_CHAIN_REVIEW'],holes);assert ev[0]['unreferenced_centerline_length_mm']<1 and len(ev[0]['actual_holes_in_connected_void'])==17
 ev=analyze('Full split has no finite tested GND detour',[box(-.4,-11,.4,11)],['LONG_SLOT_OR_ANTIPAD_CHAIN_REVIEW']);assert ev[0]['minimum_tested_connected_GND_window_radius_mm']is None
 analyze('Unreferenced terminal with no plated return remains flagged',[box(-6,-.4,-4,.4)],['TERMINAL_EXIT_WITHOUT_LOCAL_VERIFIED_RETURN_REVIEW'])
 # Restricting a GND window never fills a real slit between probes.
 plane=board.difference(box(-.0001,-11,.0001,11));gap=LineString([(-.0001,0),(.0001,0)])
 assert detour_extent(plane,gap,box(-.002,-.0001,-.001,.0001),box(.001,-.0001,.002,.0001))is None
 tests.append({'case':'No buffer or local-window operation bridges a real copper slit','pass':True})
 # The previous via-only project review missed J303.6's actual PTH layer swap.
 # Require exact outer-layer incidence, not a blanket exemption for headers.
 disk=Point(-5,0).buffer(.9,quad_segs=128);plane=board.difference(disk);voids=[disk]
 transition={'id':'HEADER.6','kind':'pad','net':'TEST','g':Point(-5,0).buffer(.75),'routed_outer_layers':[1]}
 event=analyze_chain(chain,plane,voids,STRtree(voids),[],[transition],[],'TEST')[0]
 assert event['classification']=='PTH_SINGLE_LAYER_TERMINAL_ANTIPAD_NO_BOARD_LAYER_CHANGE'
 tests.append({'case':'Single-layer debug PTH terminal is not falsely treated as a layer transfer','pass':True})
 transition['routed_outer_layers']=[1,2]
 event=analyze_chain(chain,plane,voids,STRtree(voids),[],[transition],[],'TEST')[0]
 assert event['classification']=='TERMINAL_EXIT_WITHOUT_LOCAL_VERIFIED_RETURN_REVIEW'
 tests.append({'case':'True PTH Top-Bottom transfer cannot inherit a single-layer terminal exemption','pass':True})
 access=[{'id':'verified-return','xy_mm':[-5,1.5]}]
 event=analyze_chain(chain,plane,voids,STRtree(voids),[],[transition],access,'TEST')[0]
 assert event['classification']=='PLATED_SIGNAL_EXIT_WITH_VERIFIED_LOCAL_GND_RETURN'
 access[0]['xy_mm']=[-5,3]
 event=analyze_chain(chain,plane,voids,STRtree(voids),[],[transition],access,'TEST')[0]
 assert event['classification']=='TERMINAL_EXIT_WITHOUT_LOCAL_VERIFIED_RETURN_REVIEW'
 tests.append({'case':'Actual PTH transfer requires the same nearby verified GND access as a signal via','pass':True})
 a=box(-1,-1,-.1,1);b=box(.1,-1,1,1);ground=board.difference(a.union(b))
 assert actual_void_corridor(ground,a,b,.15)['pass']
 assert not actual_void_corridor(ground,a,a,.15)['pass']
 blocked=ground.difference(box(-.01,-1,.01,1))
 assert not actual_void_corridor(blocked,a,b,.15)['pass']
 tests.append({'case':'Actual corridor width requires distinct voids and an uninterrupted real GND connector','pass':True})
 return {'status':'PASS','cases':tests}


def main():
 p=argparse.ArgumentParser(description=__doc__)
 for key in['source','state','archive','zip','output','svg']:p.add_argument('--'+key,type=Path)
 p.add_argument('--corridors',type=Path,default=Path(__file__).with_name('reference-plane-corridors.json'))
 p.add_argument('--self-test',action='store_true');a=p.parse_args()
 if a.self_test:r=self_test()
 else:
  if not all(getattr(a,k)for k in['source','state','archive','zip','output']):p.error('--source/--state/--archive/--zip/--output required')
  r=run(a)
 if a.output:a.output.write_text(json.dumps(finite(r),indent=2,allow_nan=False)+'\n')
 print(json.dumps({**{k:r[k]for k in['status','route_LINE_count','classification_counts']if k in r},'error_count':len(r.get('errors',[])),'review_count':len(r.get('review_events',[]))}))
 return bool(r.get('errors')or r.get('review_events'))
if __name__=='__main__':raise SystemExit(main())

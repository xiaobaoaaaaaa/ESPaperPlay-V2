#!/usr/bin/env python3
"""Read-only critical-signal/reference-plane projection and F/B return-access audit.
No refill or CAD changes. Actual saved GND fill polygons, not zone outlines.
"""
import argparse,collections,hashlib,json,math,sys,os,re
from pathlib import Path
import pcbnew as P
from shapely.geometry import Point,LineString,GeometryCollection
from shapely.ops import unary_union
ROOT=next(p for p in Path(__file__).resolve().parents if (p/'hardware/devboard-99').is_dir())
sys.path.insert(0,str(ROOT/'hardware/devboard-99/tools'))
from check_u101_r13 import polys,native_geom
EPS=.00002
USB=['/USB_INPUT/USB_DP_PORT','/USB_INPUT/USB_DM_PORT','USB_DP_MCU','USB_DM_MCU']
SD=[n for s in ['CLK','CMD','D0','D1','D2','D3']for n in ['SD_'+s,'/STORAGE_SD/SD_'+s+'_BUS','SD_CARD_'+s]]
EPD=['EPD_SCLK','EPD_MOSI','EPD_BUF_SCLK','EPD_BUF_MOSI','EPD_PAD_SCLK','EPD_PAD_MOSI']
AUDIO=['I2S_BCLK','I2S_WS','SPEAKER_DATA','/AUDIO/AUDIO_BCLK_BUF','/AUDIO/AUDIO_WS_BUF','/AUDIO/AUDIO_DIN_BUF','/AUDIO/I2S_BCLK_AUDIO','/AUDIO/I2S_WS_AUDIO','/AUDIO/I2S_DIN_AUDIO','/AUDIO/MIC_SD_RAW','MIC_DATA']
xy=lambda v:[P.ToMM(v.x),P.ToMM(v.y)]
uid=lambda x:x.m_Uuid.AsString()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def lines(g):
 if g.is_empty:return []
 if g.geom_type in ['LineString','LinearRing']:return [g]
 if hasattr(g,'geoms'):return [l for z in g.geoms for l in lines(z)]
 return []
def components(g):
 if g.is_empty:return []
 return [g]if g.geom_type=='Polygon'else list(g.geoms)
def region(g):
 return {'area_mm2':g.area,'bounds_mm':list(g.bounds)if not g.is_empty else None,'centroid_mm':list(g.centroid.coords)[0]if not g.is_empty else None}
def fill_margin_config():
 version='.'.join(P.GetBuildVersion().split('.')[0:2])
 base=Path(os.environ.get('KICAD_CONFIG_HOME',str(Path(os.environ.get('XDG_CONFIG_HOME',str(Path.home()/'.config')))/'kicad')))
 path=base/version/'kicad_advanced';value=.0005;source='KiCad10 official ADVANCED_CFG default ExtraFillMargin'
 if path.exists():
  m=re.search(r'^\s*ExtraFillMargin\s*=\s*([0-9.eE+-]+)',path.read_text(),re.M)
  if m:value=float(m.group(1));source='Explicit ExtraFillMargin in active kicad_advanced'
 return value,{'value_mm':value,'source':source,'inspected_config_path':str(path),'config_exists':path.exists(),'runtime_version':P.GetBuildVersion()}
def antipad_envelope(t,layer,clearance,max_error,extra_margin):
 ps=P.SHAPE_POLY_SET();t.TransformShapeToPolygon(ps,layer,P.FromMM(clearance+extra_margin),P.FromMM(max_error),P.ERROR_OUTSIDE);g=polys(ps)
 circular=t.GetClass()=='PCB_VIA'or(isinstance(t,P.PAD)and t.GetShape()==P.PAD_SHAPE_CIRCLE and t.GetOffset().x==0 and t.GetOffset().y==0)
 meta={'native_clearance_margin_mm':clearance+extra_margin,'native_polygon_max_error_mm':max_error,'rounding_padding_mm':EPS}
 if circular:
  center=xy(t.GetPosition());radius=max(math.dist(center,p)for part in components(g)for p in part.exterior.coords);n=128;envelope=Point(center).buffer((radius+EPS)/math.cos(math.pi/(4*n)),quad_segs=n);meta.update(method='Circumscribed128-quadrant polygon around circumcircle of nativeERROR_OUTSIDE clearance vertices',native_outer_vertex_radius_mm=radius,circle_radius_mm=radius+EPS)
 else:envelope=g.buffer(EPS,quad_segs=64);meta['method']='NativeERROR_OUTSIDE clearance polygon plus rounding padding; non-circular native silhouette preserved'
 meta['covers_native_clearance_polygon']=envelope.covers(g);assert meta['covers_native_clearance_polygon']
 return envelope,meta

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--board',type=Path,required=True);ap.add_argument('--report',type=Path,required=True);ap.add_argument('--return-target-mm',type=float,default=2.0);a=ap.parse_args();before=sha(a.board);b=P.LoadBoard(str(a.board));critical=set(USB+SD+AUDIO+EPD);extra_margin,extra_info=fill_margin_config();max_error=P.ToMM(b.GetDesignSettings().m_MaxError);refs={P.F_Cu:P.In1_Cu,P.B_Cu:P.In2_Cu};errors=[];reviews=[]
 planes={};plane_rows=[];clearances={};exempt={};native_by_id={};net_exist={p.GetNetname()for f in b.GetFootprints()for p in f.Pads()};missingnets=sorted(critical-net_exist)
 if missingnets:errors.append({'kind':'critical_net_missing','nets':missingnets})
 for l in refs.values():
  zs=[z for z in b.Zones()if not z.GetIsRuleArea()and z.IsOnLayer(l)];gs=[polys(z.GetFilledPolysList(l))for z in zs if z.GetNetname()=='GND'and z.HasFilledPolysForLayer(l)];g=unary_union(gs);planes[l]=g;clearances[l]=max([P.ToMM(z.GetLocalClearance())for z in zs]+[0]);row={'layer':b.GetLayerName(l),'zone_count':len(zs),'only_GND_zones':bool(zs)and all(z.GetNetname()=='GND'for z in zs),'saved_fill_flags_fresh':bool(zs)and all(z.IsFilled()and not z.NeedRefill()and z.HasFilledPolysForLayer(l)for z in zs),'copper_region_count':len(components(g)),'fill_area_mm2':g.area,'zone_clearance_mm':clearances[l]};plane_rows.append(row)
  if not row['only_GND_zones']or not row['saved_fill_flags_fresh']or row['copper_region_count']!=1:errors.append({'kind':'invalid_saved_reference_plane','details':row})
 fps=list(b.GetFootprints());allpads=[p for f in fps for p in f.Pads()];alltracks=list(b.GetTracks());throughs=[v for v in alltracks if v.GetClass()=='PCB_VIA']+[p for p in allpads if p.GetAttribute()==P.PAD_ATTRIB_PTH];stale=[];ground_returns=[]
 # Count GND access only when its copper annulus intersects BOTH actual saved references.
 for t in throughs:
  node={'uuid':uid(t),'net':t.GetNetname(),'position_mm':xy(t.GetPosition()),'kind':'PTH_pad'if isinstance(t,P.PAD)else'via'}
  if isinstance(t,P.PAD):node.update(reference=t.GetParentFootprint().GetReference(),pin=t.GetNumber());drill=max(P.ToMM(t.GetDrillSize().x),P.ToMM(t.GetDrillSize().y))
  else:drill=P.ToMM(t.GetDrillValue())
  geoms={l:native_geom(t,l)for l in refs.values()if t.IsOnLayer(l)};ring={l:g.difference(Point(node['position_mm']).buffer(drill/2,quad_segs=64))for l,g in geoms.items()};contact={b.GetLayerName(l):planes[l].intersection(g).area for l,g in ring.items()}
  if node['net']=='GND'and all(l in ring and planes[l].intersection(ring[l]).area>1e-5 for l in refs.values()):ground_returns.append({**node,'annular_overlap_with_saved_plane_mm2':contact})
  elif node['net']not in ['', 'GND']:
   for l,g in geoms.items():
    overlap=planes[l].intersection(g).area
    if overlap>1e-5:stale.append({'uuid':uid(t),'net':node['net'],'reference_layer':b.GetLayerName(l),'copper_overlap_area_mm2':overlap})
  if node['net']in critical:
   native_by_id[uid(t)]=(t,node,geoms)
   node['antipad_envelopes']={}
   for l,g in geoms.items():
    env,meta=antipad_envelope(t,l,clearances[l],max_error,extra_margin);node['antipad_envelopes'][b.GetLayerName(l)]=meta;exempt.setdefault((node['net'],l),[]).append((node,env))
 if stale:errors.append({'kind':'non_GND_through_copper_intersects_saved_GND_fill','objects':stale,'meaning':'Saved fills are stale or have a real clearance violation; do not trust projection until refill/nativeDRC.'})
 exempt_union={k:unary_union([g for _,g in v])for k,v in exempt.items()};plane_eps={l:g.buffer(EPS)for l,g in planes.items()};rows=[];tracks_by_net_layer=collections.defaultdict(list)
 for t in alltracks:
  if t.GetClass()=='PCB_VIA'or t.GetNetname()not in critical:continue
  if t.GetClass()=='PCB_ARC':errors.append({'kind':'unsupported_critical_arc','uuid':uid(t),'net':t.GetNetname()});continue
  l=t.GetLayer()
  if l not in refs:errors.append({'kind':'critical_route_on_non_outer_layer','uuid':uid(t),'layer':b.GetLayerName(l)});continue
  ref=refs[l];start,end=xy(t.GetStart()),xy(t.GetEnd());w=P.ToMM(t.GetWidth());line=LineString([start,end]);copper=line.buffer(w/2,quad_segs=64);tracks_by_net_layer[(t.GetNetname(),l)].append(copper);ex=exempt_union.get((t.GetNetname(),ref),GeometryCollection());missing=line.difference(plane_eps[ref]);other=missing.difference(ex);corridor=copper.difference(plane_eps[ref]);othercorridor=corridor.difference(ex);gaplines=lines(other);selfgaps=missing.intersection(ex);explained=[{'uuid':n['uuid'],'kind':n['kind'],'position_mm':n['position_mm'],'envelope_method':n['antipad_envelopes'][b.GetLayerName(ref)]}for n,g in exempt.get((t.GetNetname(),ref),[])if missing.intersects(g)]
  row={'uuid':uid(t),'net':t.GetNetname(),'layer':b.GetLayerName(l),'reference_layer':b.GetLayerName(ref),'start_mm':start,'end_mm':end,'width_mm':w,'length_mm':line.length,'all_centerline_void_mm':missing.length,'own_through_antipad_centerline_mm':selfgaps.length,'unexplained_centerline_void_mm':other.length,'longest_unexplained_centerline_gap_mm':max([g.length for g in gaplines]+[0]),'unexplained_centerline_gap_coordinates_mm':[list(g.coords)for g in gaplines],'nominal_copper_projection_area_mm2':copper.area,'all_projection_void_area_mm2':corridor.area,'unexplained_projection_void_area_mm2':othercorridor.area,'unexplained_projection_regions':[region(g)for g in components(othercorridor)if g.area>1e-8],'own_through_antipad_explanations':explained};rows.append(row)
  if other.length>1e-4 or othercorridor.area>1e-4:reviews.append({'kind':'reference_copper_gap_outside_own_antipad','track_uuid':uid(t),'net':t.GetNetname(),'reference_layer':b.GetLayerName(ref),'centerline_gap_mm':other.length,'max_contiguous_gap_mm':row['longest_unexplained_centerline_gap_mm'],'nominal_projection_void_mm2':othercorridor.area})
 unions={k:unary_union(gs)for k,gs in tracks_by_net_layer.items()};transition_rows=[]
 for t,n,_ in native_by_id.values():
  touches={b.GetLayerName(l):unions.get((n['net'],l),GeometryCollection()).intersects(native_geom(t,l))for l in refs if t.IsOnLayer(l)};actual=all(touches.get(b.GetLayerName(l),False)for l in refs);near=min(ground_returns,key=lambda g:math.dist(n['position_mm'],g['position_mm']),default=None);dist=math.dist(n['position_mm'],near['position_mm'])if near else None;row={**n,'touches_same_net_tracks_on_outer_layers':touches,'actual_F_B_track_transition':actual,'nearest_GND_through_UUID':near['uuid']if near else None,'nearest_GND_through_position_mm':near['position_mm']if near else None,'nearest_GND_through_center_distance_mm':dist,'within_return_target':dist is not None and dist<=a.return_target_mm+EPS,'nearest_GND_actual_annular_plane_contact_mm2':near['annular_overlap_with_saved_plane_mm2']if near else None};transition_rows.append(row)
  if actual and not row['within_return_target']:reviews.append({**row,'through_object_kind':row['kind'],'kind':'F_B_transition_return_access_too_far'})
 summary={}
 for n in sorted(critical):
  ns=[r for r in rows if r['net']==n];summary[n]={'track_count':len(ns),'total_track_copper_length_mm':sum(r['length_mm']for r in ns),'total_unexplained_centerline_void_mm':sum(r['unexplained_centerline_void_mm']for r in ns),'total_unexplained_projection_void_mm2':sum(r['unexplained_projection_void_area_mm2']for r in ns),'max_contiguous_unexplained_gap_mm':max([r['longest_unexplained_centerline_gap_mm']for r in ns]+[0]),'actual_F_B_transition_count':sum(r['actual_F_B_track_transition']for r in transition_rows if r['net']==n),'far_return_transition_count':sum(r['actual_F_B_track_transition']and not r['within_return_target']for r in transition_rows if r['net']==n)}
 unchanged=sha(a.board)==before
 if not unchanged:errors.append({'kind':'input_board_changed_during_read'})
 result={'status':'FAIL_SAVED_REFERENCE_DATA'if errors else'REVIEW_REQUIRED'if reviews else'PASS_GEOMETRIC_REFERENCE_REVIEW','scope':'All tracks and branches on39 nominated critical nets:4USB,18SD,11speaker/microphoneI2S,6EPD SPI. This is nominal2D projection, not impedance/return-inductance/eye/timing/EMI certification. Actual saved inner GND fill used; no refill or CAD edit. Pad-only connections with zero track length are named in summary but are not track-projection-certified.','board':str(a.board),'board_sha256':before,'script_sha256':sha(Path(__file__)),'input_unchanged':unchanged,'reference_mapping':{'F.Cu':'In1.Cu','B.Cu':'In2.Cu'},'return_target_center_distance_mm':a.return_target_mm,'KiCad_ExtraFillMargin':extra_info,'antipad_algorithm_evidence':'antipad-bound-research.md: KiCad10.0.8 ExtraFillMargin andERROR_OUTSIDE/arc segment rounding; no arbitrary0.01mm allowance.','numerical_thresholds':{'plane_boundary_buffer_mm':EPS,'own_antipad_polygon_max_error_allowance_mm':max_error,'minimum_reported_nonself_centerline_gap_mm':.0001,'minimum_reported_nonself_projection_gap_area_mm2':.0001},'self_antipad_policy':'Own-net nativeERROR_OUTSIDE clearance polygons include the actual ExtraFillMargin and board maximum approximation error; circular pads/vias use a strictly circumscribed envelope of native vertex radii. This is explained separately, not called plane copper. Entire merged void is never exempted. Physical F/B track transitions through these nodes must meet the stated nearbyGND access target; PTH terminals with only one outer track layer are listed separately.','inner_planes':plane_rows,'qualified_GND_through_access_count':len(ground_returns),'qualified_GND_through_access':ground_returns,'errors':errors,'reviews':reviews,'net_summary':summary,'tracks':rows,'critical_through_nodes':transition_rows};a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps({'status':result['status'],'errors':len(errors),'reviews_by_kind':dict(collections.Counter(r['kind']for r in reviews)),'critical_tracks':len(rows),'critical_through_nodes':len(transition_rows),'actual_F_B_transitions':sum(r['actual_F_B_track_transition']for r in transition_rows),'qualified_GND_access':len(ground_returns),'worst_nets':sorted(summary.items(),key=lambda kv:kv[1]['total_unexplained_centerline_void_mm'],reverse=True)[:8]},indent=2));return 1 if errors else 0
if __name__=='__main__':raise SystemExit(main())

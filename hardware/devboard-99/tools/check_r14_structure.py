#!/usr/bin/env python3
"""Independent read-only r14 routed structure and actual ground-plane audit.
Does not import routing/layout generators and never saves/refills a board.
"""
import argparse,collections,hashlib,importlib.util,json,math,sys,xml.etree.ElementTree as ET
from pathlib import Path
import pcbnew as P
from shapely.geometry import Point
from shapely.ops import unary_union
root=next(p for p in Path(__file__).resolve().parents if (p/'hardware/devboard-99').is_dir())
spec=importlib.util.spec_from_file_location('r13_geometry',root/'hardware/devboard-99/tools/check_u101_r13.py');geom=importlib.util.module_from_spec(spec);spec.loader.exec_module(geom)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def uid(x):return x.m_Uuid.AsString()
def mm(x):return P.ToMM(x)
def xy(v):return [round(mm(v.x),6),round(mm(v.y),6)]
def main():
 ap=argparse.ArgumentParser(description=__doc__)
 for name in ['board','baseline','netlist','report']:ap.add_argument('--'+name,type=Path,required=True)
 ap.add_argument('--drc',type=Path);a=ap.parse_args();errors=[];reviews=[];checks={}
 def check(key,ok,**detail):
  checks[key]={'pass':bool(ok),**detail}
  if not ok:errors.append(key)
 inputs={str(p):sha(p)for p in [a.board,a.baseline,a.netlist,a.board.with_suffix('.kicad_pro')]if p.exists()};b=P.LoadBoard(str(a.board));old=P.LoadBoard(str(a.baseline));b.BuildConnectivity();c=b.GetConnectivity()
 fps={f.GetReference():f for f in b.GetFootprints()};of={f.GetReference():f for f in old.GetFootprints()};check('physical_inventory',set(fps)==set(of)and len(fps)==240,count=len(fps))
 differences=[]
 for ref,f in fps.items():
  if ref not in of:continue
  o=of[ref];n0=geom.canonical(o);n1=geom.canonical(f)
  sig=lambda fp,n:{uid(orig):geom.pad_sig(p)for orig,p in zip(fp.Pads(),n.Pads())}
  traits=lambda fp:[uid(fp),fp.GetValue(),fp.GetFPIDAsString(),xy(fp.GetPosition()),fp.GetOrientationDegrees(),fp.GetLayer(),fp.IsDNP(),fp.GetPath().AsString(),dict(fp.GetFieldsText())]
  if traits(f)!=traits(o)or sig(f,n1)!=sig(o,n0):differences.append(ref)
 check('r13_footprints_placement_metadata_pad_geometry_and_UUIDs_preserved',not differences,changed=differences)
 # Keepouts include all-layer antenna, microSD and microphone regions.
 oldtree=geom.parse(a.baseline.read_text());tree=geom.parse(a.board.read_text());oldfps={geom.uuid(n):n for n in oldtree[1:]if isinstance(n,list)and n[0]=='footprint'};newfps={geom.uuid(n):n for n in tree[1:]if isinstance(n,list)and n[0]=='footprint'}
 altered=[]
 for id,n in oldfps.items():
  oz=[x for x in n if isinstance(x,list)and x[0]=='zone'];nz=[x for x in newfps.get(id,[])if isinstance(x,list)and x[0]=='zone']
  if oz!=nz:altered.append(id)
 check('all_footprint_keepouts_unchanged',not altered,changed=altered)
 def serialized_footprint_semantics(n):
  # KiCad reorders pads/properties on SaveBoard and makes the default
  # remove_unused_layers=no explicit; keep every other field and vertex order.
  children=[]
  for child in n[2:]:
   if isinstance(child,list)and child[0]=='pad':
    child=child[:4]+sorted([x for x in child[4:]if x!=['remove_unused_layers','no']],key=lambda x:json.dumps(x,sort_keys=True))
   children.append(child)
  return n[:2]+sorted(children,key=lambda x:json.dumps(x,sort_keys=True))
 u=uid(fps['U101']);check('U101_entire_footprint_semantics_retained_r13',serialized_footprint_semantics(oldfps[u])==serialized_footprint_semantics(newfps[u]),normalization='Only top-level/pad property ordering and explicit remove_unused_layers=no default; all geometry vertex order and other fields preserved')
 net=ET.parse(a.netlist).getroot();expected={str((p.get('ref'),p.get('pin'))):[n.get('name')]for n in net.findall('nets/net')for p in n.findall('node')};actual=geom.pin_map(b)
 check('electrical_inventory_and_assignments',len(expected)==774 and len(net.findall('components/comp'))==236 and len(net.findall('nets/net'))==181 and actual==expected,logical_pins=len(actual),nets=len(net.findall('nets/net')))
 check('four_layers_front_assembly',b.GetCopperLayerCount()==4 and all(f.GetLayer()==P.F_Cu for f in fps.values()))
 outline=P.SHAPE_POLY_SET();valid=b.GetBoardPolygonOutlines(outline,False);poly=geom.polys(outline);bb=poly.bounds;check('outline99mm',valid and outline.OutlineCount()==1 and abs(bb[2]-bb[0]-99)<.00001 and abs(bb[3]-bb[1]-99)<.00001,bounds_mm=bb)
 tracks=[t for t in b.GetTracks()if t.GetClass()in ['PCB_TRACK','PCB_ARC']];vias=[t for t in b.GetTracks()if t.GetClass()=='PCB_VIA'];check('real_routing_present',bool(tracks)and bool(vias),tracks=len(tracks),vias=len(vias))
 check('outer_only_signal_power_tracks',all(t.GetLayer()in [P.F_Cu,P.B_Cu]for t in tracks),inner=[uid(t)for t in tracks if t.GetLayer()not in [P.F_Cu,P.B_Cu]])
 badvias=[{'uuid':uid(v),'diameter_mm':mm(v.GetWidth(P.F_Cu)),'drill_mm':mm(v.GetDrillValue()),'type':v.GetViaType()}for v in vias if v.GetViaType()!=P.VIATYPE_THROUGH or mm(v.GetWidth(P.F_Cu))<.6-1e-6 or mm(v.GetDrillValue())<.3-1e-6 or (mm(v.GetWidth(P.F_Cu))-mm(v.GetDrillValue()))/2<.15-1e-6 or not all(v.IsOnLayer(l)for l in [P.F_Cu,P.In1_Cu,P.In2_Cu,P.B_Cu])]
 check('standard_through_vias_min030_060',not badvias,violations=badvias)
 check('minimum_track_width',all(mm(t.GetWidth())>=.15-1e-6 for t in tracks),minimum_mm=min((mm(t.GetWidth())for t in tracks),default=None))
 drills=[{'ref':f.GetReference(),'pin':p.GetNumber(),'drill_mm':xy(p.GetDrillSize())}for f in fps.values()for p in f.Pads()if max(xy(p.GetDrillSize()))>0];check('physical_pad_drills_min030',all(min(x['drill_mm'])>=.3-1e-6 for x in drills),count=len(drills))
 pro=json.loads(a.board.with_suffix('.kicad_pro').read_text());ds=pro['board']['design_settings'];rules=ds['rules'];needed={'min_clearance':.15,'min_track_width':.15,'min_through_hole_diameter':.3,'min_via_diameter':.6,'min_via_annular_width':.15,'min_hole_to_hole':.25,'min_copper_edge_clearance':.3}
 check('manufacturing_rules_not_relaxed',all(rules.get(k,0)>=v-1e-9 for k,v in needed.items()),actual={k:rules.get(k)for k in needed});check('no_DRC_exclusions',not ds.get('drc_exclusions'))
 critical=['unconnected_items','shorting_items','clearance','hole_clearance','drill_out_of_range','copper_edge_clearance'];check('critical_DRC_checks_enabled',all(ds.get('rule_severities',{}).get(k)!='ignore'for k in critical))
 # No refill is performed: stale/missing plane fills fail rather than being hidden.
 planes={};plane_info=[]
 for layer in [P.In1_Cu,P.In2_Cu]:
  zones=[z for z in b.Zones()if not z.GetIsRuleArea()and z.IsOnLayer(layer)];fills=[geom.polys(z.GetFilledPolysList(layer))for z in zones if z.HasFilledPolysForLayer(layer)];g=unary_union(fills);planes[layer]=g;n=1 if g.geom_type=='Polygon'else len(g.geoms)if not g.is_empty else 0
  entry={'layer':b.GetLayerName(layer),'zones':len(zones),'all_GND':all(z.GetNetname()=='GND'for z in zones),'fresh':bool(zones)and all(z.HasFilledPolysForLayer(layer)and z.IsFilled()and not z.NeedRefill()for z in zones),'connected_regions':n,'coverage_fraction':g.area/poly.area};plane_info.append(entry)
  check('filled_continuous_GND_'+b.GetLayerName(layer),entry['all_GND']and entry['fresh']and n==1 and entry['coverage_fraction']>=.85,**entry)
 # The eight external thermal reservations must now be real plated GND vias.
 external={'U201-TH1':(33.7,29.0),'U201-TH2':(34.5,29.0),'U203-TH1':(14.0,46.7),'U203-TH2':(14.0,49.3),'U802-TH1':(34.25,73.3),'U802-TH2':(33.75,68.7),'U802-TH3':(31.7,71.25),'U802-TH4':(32.95,68.6)};thermal=[]
 for name,q in external.items():
  matches=[v for v in vias if v.GetNetname()=='GND'and math.dist(q,xy(v.GetPosition()))<.000001]
  ok=len(matches)==1 and all(g.covers(Point(q).buffer(.30))for g in planes.values())
  thermal.append({'name':name,'position_mm':q,'matching_vias':[uid(v)for v in matches],'both_planes_cover_030mm_land_radius':ok,'both_planes_cover_additional_0_05mm_halo':all(g.covers(Point(q).buffer(.35))for g in planes.values())})
 check('eight_real_external_thermal_GND_vias',all(x['both_planes_cover_030mm_land_radius']for x in thermal),items=thermal,scope='Electrical copper geometry only; external thermal-via performance still requires first-board temperature tests')
 check('obsolete_thermal_reservations_removed',not any(g.GetName()=='THERMAL_RESERVATIONS_LAYOUT_ONLY'for g in b.Groups()))
 access=[g for g in b.Groups()if g.GetName()=='OPERATION_ACCESS_DOCUMENTATION'];check('operation_envelope_inventory_preserved',len(access)==1 and len(list(access[0].GetItems()))==21)
 rootpad=next(p for p in fps['U101'].Pads()if p.GetNumber()=='17'and p.GetAttribute()==P.PAD_ATTRIB_SMD);connected={uid(rootpad)}|{uid(x)for x in c.GetConnectedItems(rootpad)};groundpads=[p for f in fps.values()for p in f.Pads()if p.GetNetname()=='GND'];unreached=[{'uuid':uid(p),'ref':p.GetParentFootprint().GetReference(),'pin':p.GetNumber()}for p in groundpads if uid(p)not in connected]
 check('all_ground_pads_in_EP17_native_connected_component',not unreached,ground_pad_count=len(groundpads),unreached=unreached)
 # A nearby return is counted only when actual filled GND copper covers it on both references.
 ground_returns=[]
 for v in vias:
  if v.GetNetname()=='GND'and all(g.covers(Point(xy(v.GetPosition())))for g in planes.values()):ground_returns.append((uid(v),xy(v.GetPosition())))
 for p in groundpads:
  if p.GetAttribute()!=P.PAD_ATTRIB_PTH:continue
  # Thermal-connected PTH pads may not contain zone fill at their centre.
  # Count actual pad-annulus contact with both saved reference-plane fills.
  hole=Point(xy(p.GetPosition())).buffer(max(xy(p.GetDrillSize()))/2,quad_segs=64)
  if all(p.IsOnLayer(l)and planes[l].intersection(geom.native_geom(p,l).difference(hole)).area>1e-5 for l in planes):ground_returns.append((uid(p),xy(p.GetPosition())))
 transitions=[]
 for v in vias:
  if v.GetNetname()=='GND':continue
  q=xy(v.GetPosition());nearest=min(ground_returns,key=lambda r:math.dist(q,r[1]),default=None);dist=math.dist(q,nearest[1])if nearest else None;transitions.append({'uuid':uid(v),'net':v.GetNetname(),'position_mm':q,'nearest_GND_uuid':nearest[0]if nearest else None,'distance_mm':dist})
 far=[x for x in transitions if x['distance_mm']is None or x['distance_mm']>2.0]
 if far:reviews.append({'kind':'return_geometry_target_2mm','items':far,'scope':'Review target; not a return-inductance or SI certificate'})
 if a.drc:
  d=json.loads(a.drc.read_text());check('native_DRC_all_closed',not d['violations']and not d['unconnected_items']and not d['schematic_parity'],violations=len(d['violations']),unconnected=len(d['unconnected_items']),schematic_parity=len(d['schematic_parity']))
 else:reviews.append({'kind':'native_DRC_not_supplied','detail':'Structural report alone cannot release routing.'})
 check('source_inputs_unchanged',all(Path(p).exists()and sha(Path(p))==h for p,h in inputs.items()))
 report={'status':'FAIL'if errors else'PASS_STRUCTURE_REVIEW_PENDING'if reviews else'PASS_ROUTED_STRUCTURE','scope':'Native structure/connectivity/filled planes only; power-path, critical signal/reference paths, actual CAM/drill/mask and U101 continuous paste tolerance audits remain separate.','errors':errors,'reviews':reviews,'checks':checks,'inner_planes':plane_info,'ground_return_transitions':transitions,'input_hashes':inputs,'script_sha256':sha(Path(__file__))};a.report.parent.mkdir(exist_ok=True,parents=True);a.report.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n');print(json.dumps({'status':report['status'],'errors':errors,'reviews':len(reviews)},ensure_ascii=False));return bool(errors)
if __name__=='__main__':raise SystemExit(main())

#!/usr/bin/env python3
"""Independent read-only U101 OSP/open-PTH/paste audit. Native CLI runs only in scratch copies."""
import argparse,collections,copy,hashlib,json,math,re,shutil,subprocess,sys,xml.etree.ElementTree as ET
from pathlib import Path
import pcbnew as P
from shapely.geometry import Polygon,Point,GeometryCollection,box
from shapely.ops import unary_union
from shapely.affinity import scale,translate
from gerbonara import GerberFile,ExcellonFile
from gerbonara.utils import MM
EPS=.00002

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def xy(v):return [round(v.x/1e6,6),round(v.y/1e6,6)]
def parse(text):
 stack=[];root=None
 for tok in re.findall(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+',text):
  if tok=='(':
   node=[]
   if stack:stack[-1].append(node)
   else:root=node
   stack.append(node)
  elif tok==')':stack.pop()
  else:
   if tok.startswith('"'):value=json.loads(tok)
   else:
    try:value=float(tok)
    except ValueError:value=tok
   stack[-1].append(value)
 if stack:raise ValueError('Unbalanced source S-expression')
 return root

def child(node,key):return next((x for x in node if isinstance(x,list)and x and x[0]==key),None)
def uuid(node):
 n=child(node,'uuid');return n[1]if n else None

def polys(ps):
 result=[]
 for i in range(ps.OutlineCount()):
  q=ps.COutline(i);outer=[xy(q.CPoint(k))for k in range(q.PointCount())];holes=[]
  for j in range(ps.HoleCount(i)):
   h=ps.CHole(i,j);holes.append([xy(h.CPoint(k))for k in range(h.PointCount())])
  if len(outer)>2:result.append(Polygon(outer,holes))
 return unary_union(result)if result else GeometryCollection()
def native_geom(item,layer):
 ps=P.SHAPE_POLY_SET();item.TransformShapeToPolygon(ps,layer,0,P.FromMM(EPS),P.ERROR_INSIDE);return polys(ps)
def canonical(fp):
 n=P.Cast_to_FOOTPRINT(fp.Duplicate(False));n.SetOrientationDegrees(0);n.SetPosition(P.VECTOR2I(0,0));return n

def pad_sig(p,net=True):
 d={'number':p.GetNumber(),'position':xy(p.GetPosition()),'size':xy(p.GetSize()),'orientation':round(p.GetOrientationDegrees()%360,6),'shape':int(p.GetShape()),'attribute':int(p.GetAttribute()),'drill':xy(p.GetDrillSize()),'offset':xy(p.GetOffset()),'layers':p.GetLayerSet().FmtHex(),'mask':p.GetLocalSolderMaskMargin(),'paste':p.GetLocalSolderPasteMargin(),'paste_ratio':p.GetLocalSolderPasteMarginRatio(),'zone_connection':int(p.GetLocalZoneConnection()),'roundrect':p.GetRoundRectRadiusRatio(),'chamfer':p.GetChamferRectRatio()}
 if net:d['net']=p.GetNetname()
 if p.GetShape()==P.PAD_SHAPE_CUSTOM:d['geometry']=native_geom(p,P.F_Paste if p.IsOnLayer(P.F_Paste)else P.F_Cu).normalize().wkt
 return d

def pin_map(board):
 d=collections.defaultdict(set)
 for f in board.GetFootprints():
  for p in f.Pads():
   if p.GetNumber():d[(f.GetReference(),p.GetNumber())].add(p.GetNetname())
 return {str(k):sorted(v)for k,v in d.items()}
def object_geom(o):
 result=GeometryCollection()
 for p in o.to_primitives(MM):
  pts=p.to_arc_poly().approximate_arcs(EPS).outline
  if len(pts)<3:continue
  g=Polygon(pts).buffer(0);result=result.union(g)if p.polarity_dark==o.polarity_dark else result.difference(g)
 return result

def gerber(path):
 result=GeometryCollection();file=GerberFile.open(path)
 for o in file.objects:
  g=object_geom(o);result=result.union(g)if o.polarity_dark else result.difference(g)
 return scale(result,yfact=-1,origin=(0,0))
def execute(argv,log):
 p=subprocess.run(argv,capture_output=True,text=True);log.write_text(p.stdout+p.stderr)
 if p.returncode:raise RuntimeError(f'Native command failed ({p.returncode}): {argv}')
def copy_project(src,dst):
 dst.mkdir(parents=True,exist_ok=True)
 for p in src.iterdir():
  if p.is_file()and (p.suffix in {'.kicad_pro','.kicad_pcb','.kicad_sch','.kicad_dru','.kicad_sym'}or p.name in {'fp-lib-table','sym-lib-table'}):shutil.copy2(p,dst/p.name)
  elif p.is_dir()and p.name.endswith('.pretty'):shutil.copytree(p,dst/p.name,dirs_exist_ok=True)

def main():
 ap=argparse.ArgumentParser(description=__doc__)
 for k in ['board','report-dir','work-dir']:ap.add_argument('--'+k,type=Path,required=True)
 ap.add_argument('--before',type=Path,help='Optional baseline directory; otherwise source files are read from git --baseline-revision into scratch')
 ap.add_argument('--baseline-revision',default='63ced99')
 ap.add_argument('--expected-project-sha256',default='5d0bb4cbdf0debfde3b0bbaa46beb881384e01f041e8320a8b961a606fbfbe6e',help='Pre-edit GUI/user project settings snapshot to preserve')
 ap.add_argument('--hole-offset',type=float,default=.63);ap.add_argument('--mask-margin',type=float,default=.02);ap.add_argument('--registration-limit',type=float,default=.03);ap.add_argument('--edge-error-limit',type=float,default=.02)
 ap.add_argument('--paste-design',choices=['cross','rounded-hole-keepouts'],required=True);ap.add_argument('--paste-span',type=float,required=True);ap.add_argument('--cross-width',type=float);ap.add_argument('--keepout-half-square',type=float);ap.add_argument('--keepout-radius',type=float)
 a=ap.parse_args();src=a.board.resolve();out=a.report_dir.resolve();work=a.work_dir.resolve();out.mkdir(parents=True,exist_ok=True);work.mkdir(parents=True,exist_ok=True)
 assert work!=src.parent and work!=out,'CLI scratch must be outside design and review output directories'
 if a.before:before=a.before.resolve()
 else:
  before=work/'baseline';before.mkdir(exist_ok=True);repo=src.parents[2];prefix='hardware/devboard-99/'
  files=subprocess.check_output(['git','-C',str(repo),'ls-tree','-r','--name-only',a.baseline_revision,'--',prefix],text=True).splitlines()
  for name in files:
   rel=Path(name[len(prefix):])
   if rel.suffix not in {'.kicad_pro','.kicad_pcb','.kicad_sch','.kicad_dru','.kicad_mod','.kicad_sym'}and rel.name not in {'fp-lib-table','sym-lib-table'}:continue
   data=subprocess.check_output(['git','-C',str(repo),'show',a.baseline_revision+':'+name]);dest=before/rel;dest.parent.mkdir(exist_ok=True,parents=True);dest.write_bytes(data)
 inputs=[p for p in src.parent.iterdir()if p.is_file()and p.suffix in {'.kicad_pro','.kicad_pcb','.kicad_sch','.kicad_dru'}]+list((src.parent/'ESPaperPlay.pretty').glob('*.kicad_mod'))
 hashes={str(p):sha(p)for p in inputs};errors=[];warnings=[{'kind':'supplier_tolerance_envelope_not_certified','detail':'The analysis envelope is conditional; domestic published PAD/plug-in-hole tolerances are not a certified via-process envelope for this board. See review-r13/README.md.'},{'kind':'mask_registration_unspecified','detail':'Nominal mask bridges are measured; solder-mask registration capability for this order is unverified.'},{'kind':'annular_independent_worst_case_not_closed','detail':'Nominal annuli pass CAD/DRC, but independently combining conservative maximum hole size and position bounds does not establish a guaranteed remaining annulus.'},{'kind':'print_registration_not_measured','detail':'The local ±0.03 mm per-axis stencil registration acceptance bound is an assumption, not a measured printing result.'},{'kind':'wicking_and_thermal_unqualified','detail':'Paste avoidance does not qualify molten-solder wicking, reflow joints, or thermal performance of open PTHs.'}];checks={}
 def check(name,ok,**extra):
  checks[name]={'pass':bool(ok),**extra}
  if not ok:errors.append({'check':name,**extra})
 baseline=before/src.name;b=P.LoadBoard(str(src));old=P.LoadBoard(str(baseline));fps={f.GetReference():f for f in b.GetFootprints()};ofs={f.GetReference():f for f in old.GetFootprints()}
 check('physical_inventory',set(fps)==set(ofs)and len(fps)==240,count=len(fps));check('electrical_pin_net_map',pin_map(b)==pin_map(old),pins=len(pin_map(b)))
 check('user_project_settings_byte_preserved',sha(src.with_suffix('.kicad_pro'))==a.expected_project_sha256,before_sha=a.expected_project_sha256,after_sha=sha(src.with_suffix('.kicad_pro')))
 sch_diffs=[p.name for p in inputs if p.suffix=='.kicad_sch'and (before/p.name).exists()and sha(p)!=sha(before/p.name)]
 check('schematics_unchanged',not sch_diffs,changed=sch_diffs)
 raw=parse(src.read_text());prior=parse(baseline.read_text());bn={uuid(x):x for x in raw[1:]if isinstance(x,list)and uuid(x)};on={uuid(x):x for x in prior[1:]if isinstance(x,list)and uuid(x)}
 fp_changed=[]
 for r,f in fps.items():
  if r=='U101':continue
  u=f.m_Uuid.AsString()
  if u not in on or bn.get(u)!=on[u]:fp_changed.append(r)
 check('other_239_footprints_exact',not fp_changed,changed=fp_changed)
 edge_changed=[u for u,n in on.items()if child(n,'layer')==['layer','Edge.Cuts']and bn.get(u)!=n]
 check('board_outline_unchanged',not edge_changed,changed=edge_changed)
 op=next(n for n in prior[1:]if isinstance(n,list)and n[:2]==['group','OPERATION_ACCESS_DOCUMENTATION']);members=child(op,'members')[1:];changed_access=[u for u in members if bn.get(u)!=on.get(u)]
 check('operation_group_and_all_21_shapes_unchanged',bn.get(uuid(op))==op and not changed_access and len(members)==21,changed=changed_access)
 old_thermal=next(n for n in prior[1:]if isinstance(n,list)and n[:2]==['group','THERMAL_RESERVATIONS_LAYOUT_ONLY']);old_members=set(child(old_thermal,'members')[1:]);old_center=xy(ofs['U101'].GetPosition());expected_removed=set()
 for uid in old_members:
  item=on[uid];c=child(item,'center')
  if item[0]=='gr_circle'and c and abs(c[1]-old_center[0])<1 and abs(c[2]-old_center[1])<1:expected_removed.add(uid)
 new_thermal=bn.get(uuid(old_thermal));new_members=set(child(new_thermal,'members')[1:])if new_thermal else set()
 check('only_U101_eight_thermal_placeholders_removed',len(expected_removed)==8 and set(on)-set(bn)==expected_removed and new_members==old_members-expected_removed and len(new_members)==16 and all(bn.get(uid)==on[uid]for uid in new_members),removed_count=len(expected_removed),retained_count=len(new_members))
 allowed_changes={uuid(old_thermal),ofs['U101'].m_Uuid.AsString()};unexpected=[]
 text_replacements={'ESPaperPlay 99 / r12\nPLACEMENT ONLY - NOT FOR FAB':'ESPaperPlay 99 / r13\nPLACEMENT ONLY - NOT FOR FAB','ESPaperPlay 99 - r12 PLACEMENT / 4 layers':'ESPaperPlay 99 - r13 UNROUTED / 4 layers'}
 for uid,n in bn.items():
  if uid in allowed_changes:continue
  prior_item=on.get(uid)
  if n==prior_item:continue
  expected=copy.deepcopy(prior_item)
  if expected and expected[0]=='gr_text'and expected[1]in text_replacements:expected[1]=text_replacements[expected[1]]
  if n!=expected:unexpected.append({'uuid':uid,'type':n[0]})
 check('all_other_UUID_objects_preserved',not unexpected,unexpected_changes=unexpected)
 old_setup=copy.deepcopy(child(prior,'setup'));child(child(old_setup,'stackup'),'copper_finish')[1]='OSP'
 check('setup_only_surface_finish_changed',old_setup==child(raw,'setup'))
 misc=lambda tree:[n for n in tree[1:]if not isinstance(n,list)or(not uuid(n)and n[0]not in {'setup','title_block'})]
 check('other_board_metadata_and_net_definitions_preserved',misc(prior)==misc(raw))
 title=child(raw,'title_block');check('updated_r13_99mm_title',child(title,'rev')[1]=='r13 THERMAL / UNROUTED'and any('99 x 99 mm'in str(n)for n in title),title=title)

 check('no_tracks_or_board_vias',len(b.GetTracks())==0,count=len(b.GetTracks()));check('four_copper_layers',b.GetCopperLayerCount()==4)
 physical_drills=[xy(p.GetDrillSize())for f in fps.values()for p in f.Pads()if max(xy(p.GetDrillSize()))>0]
 check('all_physical_drills_at_least_0_30mm',all(min(d)>=.3 for d in physical_drills),count=len(physical_drills),minimum_mm=min(min(d)for d in physical_drills))
 copper_finish=child(child(child(raw,'setup'),'stackup'),'copper_finish')
 check('OSP_finish',copper_finish==['copper_finish','OSP'],actual=copper_finish)
 u=fps['U101'];ou=ofs['U101'];cn=canonical(u);co=canonical(ou)
 check('U101_instance_identity_and_placement',u.m_Uuid.AsString()==ou.m_Uuid.AsString()and u.GetPosition()==ou.GetPosition()and u.GetOrientationDegrees()==ou.GetOrientationDegrees()and u.GetPath().AsString()==ou.GetPath().AsString(),reference_position=xy(u.GetPosition()),angle=u.GetOrientationDegrees())
 smd_old={p.GetNumber():p for p in co.Pads()if p.GetNumber()};smd_new={p.GetNumber():p for p in cn.Pads()if p.GetNumber()and p.GetAttribute()==P.PAD_ATTRIB_SMD}
 check('original_U101_signal_and_EP_pads_preserved',smd_old.keys()==smd_new.keys()and all({**pad_sig(p),**({'zone_connection':2}if k=='17'else{})}==pad_sig(smd_new[k])for k,p in smd_old.items()),old_count=len(smd_old),new_count=len(smd_new))
 holes=[p for p in cn.Pads()if max(xy(p.GetDrillSize()))>0];hpos=sorted(xy(p.GetPosition())for p in holes)
 check('four_open_PTH_GND_holes',len(holes)==4 and hpos==[[-a.hole_offset,-a.hole_offset],[-a.hole_offset,a.hole_offset],[a.hole_offset,-a.hole_offset],[a.hole_offset,a.hole_offset]]and all(p.GetNumber()=='17'and p.GetAttribute()==P.PAD_ATTRIB_PTH and xy(p.GetDrillSize())==[.3,.3]and xy(p.GetSize())==[.6,.6]and p.GetNetname()=='GND'and p.IsOnLayer(P.F_Mask)and p.IsOnLayer(P.B_Mask)and p.GetLocalSolderMaskMargin()==P.FromMM(a.mask_margin)and int(p.GetLocalZoneConnection())==2 and not p.IsOnLayer(P.F_Paste)for p in holes),positions=hpos,details=[pad_sig(p)for p in holes])
 libdir=src.parent/'ESPaperPlay.pretty';libname=u.GetFPIDAsString().split(':',1)[1];lib=P.FootprintLoad(str(libdir),libname);lc=canonical(lib)
 key=lambda p:json.dumps(pad_sig(p,False),sort_keys=True)
 check('U101_library_pad_geometry_matches',collections.Counter(key(p)for p in cn.Pads())==collections.Counter(key(p)for p in lc.Pads()),library=libname)
 old_libs={p.name:sha(p)for p in (before/'ESPaperPlay.pretty').glob('*.kicad_mod')if p.stem!=libname};new_libs={p.name:sha(p)for p in libdir.glob('*.kicad_mod')if p.stem!=libname}
 check('all_other_local_libraries_preserved',old_libs==new_libs,count=len(old_libs))
 paste=unary_union([native_geom(p,P.F_Paste)for p in cn.Pads()if not p.GetNumber()and p.IsOnLayer(P.F_Paste)])
 L=a.paste_span
 if a.paste_design=='cross':
  W=a.cross_width;expected=unary_union([box(-L/2,-W/2,L/2,W/2),box(-W/2,-L/2,W/2,L/2)])
 else:
  H=a.keepout_half_square;R=a.keepout_radius;forbidden=unary_union([box(x-H,y-H,x+H,y+H).buffer(R,quad_segs=512)for x,y in hpos]);expected=box(-L/2,-L/2,L/2,L/2).difference(forbidden)
 check('EP_paste_shape_matches_explicit_design',paste.hausdorff_distance(expected)<.001 and paste.symmetric_difference(expected).area<.005,design=a.paste_design,span_mm=L,keepout_half_square_mm=a.keepout_half_square,keepout_radius_mm=a.keepout_radius,hausdorff_error_mm=paste.hausdorff_distance(expected),symmetric_difference_area_mm2=paste.symmetric_difference(expected).area,actual_area_mm2=paste.area,expected_area_mm2=expected.area,EP_coverage_pct=paste.area/1.68**2*100)
 tolerance=[]
 for dia in [.30,.35,.40,.43]:
  hg=unary_union([Point(*p).buffer(dia/2,quad_segs=256)for p in hpos])
  for shift in sorted(set([0,.03,.05,.10,.105,.175,round(a.registration_limit+.075,6)])):
   for growth in [0,.02,.025,.05]:
    gaps=[];overlaps=[]
    for dx in [-shift,0,shift]:
     for dy in [-shift,0,shift]:
      pg=translate(paste.buffer(growth,join_style=2),xoff=dx,yoff=dy);gaps.append(pg.distance(hg));overlaps.append(pg.intersection(hg).area)
    tolerance.append({'hole_diameter_mm':dia,'translation_each_axis_mm':shift,'paste_growth_mm':growth,'minimum_gap_mm':min(gaps),'maximum_overlap_mm2':max(overlaps)})
 check('nominal_paste_avoids_drills',tolerance[0]['maximum_overlap_mm2']<1e-9,minimum_gap_mm=tolerance[0]['minimum_gap_mm'])
 stack=next(x for x in tolerance if x['hole_diameter_mm']==.43 and x['translation_each_axis_mm']==round(a.registration_limit+.075,6)and x['paste_growth_mm']==a.edge_error_limit)
 if a.paste_design=='rounded-hole-keepouts':check('conservative_tolerance_stack_20um_target',stack['minimum_gap_mm']>=.0199 and stack['maximum_overlap_mm2']<1e-9,**stack)
 # Continuous envelope proof. Secant radius inflation makes every polygonized
 # circular buffer enclose its ideal circle instead of borrowing clearance.
 Q=512;secant=1/math.cos(math.pi/(4*Q));H=round(a.registration_limit+.075,6);swept_holes=unary_union([box(x-H,y-H,x+H,y+H).buffer(.43/2*secant,quad_segs=Q)for x,y in hpos])
 def continuous_clearance(pg):
  expanded=pg.buffer(a.edge_error_limit*secant,quad_segs=Q,join_style=1)
  return {'relative_position_halfwidth_each_axis_mm':H,'maximum_drill_diameter_mm':.43,'paste_outward_error_mm':a.edge_error_limit,'circular_buffer_quad_segs':Q,'circular_buffer_secant_inflation':secant,'minimum_gap_mm':expanded.distance(swept_holes),'overlap_area_mm2':expanded.intersection(swept_holes).area,'method':'Continuous Minkowski square+disk hole-location envelope against outward-offset paste; circle buffers are circumscribed by secant radius inflation, not sampled placements.'}
 cc=continuous_clearance(paste);check('continuous_native_paste_tolerance_envelope',cc['minimum_gap_mm']>=.0199 and cc['overlap_area_mm2']<1e-9,**cc)

 # Native programs operate only on copied source, leaving the user's GUI/project state untouched.
 project=work/'project';copy_project(src.parent,project);pcb=project/src.name;sch=pcb.with_suffix('.kicad_sch');cam=work/'cam';cam.mkdir(exist_ok=True)
 execute(['kicad-cli','sch','export','netlist','--format','kicadxml','-o',str(out/'netlist.xml'),str(sch)],out/'netlist.log')
 execute(['kicad-cli','sch','erc','--format','json','-o',str(out/'native-erc.json'),str(sch)],out/'native-erc.log')
 execute(['kicad-cli','pcb','drc','--schematic-parity','--format','json','-o',str(out/'native-drc.json'),str(pcb)],out/'native-drc.log')
 execute(['kicad-cli','pcb','export','gerbers','--layers','F.Paste,B.Paste,F.Mask,B.Mask,F.Cu,B.Cu','--no-protel-ext','-o',str(cam)+'/',str(pcb)],out/'gerber-export.log')
 execute(['kicad-cli','pcb','export','drill','--format','excellon','--excellon-separate-th','--generate-report','-o',str(cam)+'/',str(pcb)],out/'drill-export.log')
 drc=json.loads((out/'native-drc.json').read_text());erc=json.loads((out/'native-erc.json').read_text());ercv=[v for s in erc['sheets']for v in s['violations']]
 check('native_DRC',not drc['violations']and not drc['schematic_parity'],violations=drc['violations'],schematic_parity=drc['schematic_parity'],expected_unconnected_count=len(drc['unconnected_items']))
 check('native_ERC',not ercv,violations=ercv)
 check('unrouted_connectivity_count_unchanged',len(drc['unconnected_items'])==499,count=len(drc['unconnected_items']))
 net=ET.parse(out/'netlist.xml').getroot();pins={str((n.get('ref'),n.get('pin'))):[g.get('name')]for g in net.findall('nets/net')for n in g.findall('node')}
 check('exported_netlist_equals_board',pins==pin_map(b),components=len(net.findall('components/comp')),nets=len(net.findall('nets/net')),pins=len(pins))
 # Inspect the actual exported layers in the full exposed-pad neighbourhood.
 center=xy(u.GetPosition());roi=translate(box(-.95,-.95,.95,.95),xoff=center[0],yoff=center[1]);gfiles={p.name:p for p in cam.glob('*.gbr')}
 def layer(s):return next(p for p in gfiles.values()if p.stem.endswith('-'+s))
 actual_paste=gerber(layer('F_Paste')).intersection(roi);pg=translate(paste,xoff=center[0],yoff=center[1]);check('exported_EP_paste_equals_native',actual_paste.symmetric_difference(pg).area<1e-6,area_mm2=actual_paste.area)
 back_paste=gerber(layer('B_Paste'));check('no_bottom_paste',back_paste.is_empty,area_mm2=back_paste.area)
 drill_records=[]
 for p in cam.glob('*.drl'):
  f=ExcellonFile.open(p)
  for o in f.objects:
   g=scale(object_geom(o),yfact=-1,origin=(0,0));c=g.centroid
   if roi.contains(c):drill_records.append({'file':p.name,'center_mm':[round(c.x,6),round(c.y,6)],'diameter_mm':round(g.bounds[2]-g.bounds[0],6),'geometry':g})
 expected_centers=sorted([[round(center[0]+p[0],6),round(center[1]+p[1],6)]for p in hpos])
 check('exported_four_PTH_drills',len(drill_records)==4 and sorted(x['center_mm']for x in drill_records)==expected_centers and all(abs(x['diameter_mm']-.3)<.00005 and '-PTH' in x['file']for x in drill_records),drills=[{k:v for k,v in x.items()if k!='geometry'}for x in drill_records])
 actual_holes=unary_union([x['geometry']for x in drill_records]);check('Gerber_paste_avoids_Excellon_drills',actual_paste.intersection(actual_holes).area<1e-9,gap_mm=actual_paste.distance(actual_holes))
 cc=continuous_clearance(translate(actual_paste,xoff=-center[0],yoff=-center[1]));check('continuous_actual_Gerber_tolerance_envelope',cc['minimum_gap_mm']>=.0199 and cc['overlap_area_mm2']<1e-9,**cc)
 masks={s:gerber(layer(s))for s in ['F_Mask','B_Mask']}
 for side,mg in masks.items():check('open_holes_'+side,mg.buffer(EPS).covers(actual_holes),uncovered_area_mm2=actual_holes.difference(mg).area)
 front_parts=[masks['F_Mask']]if masks['F_Mask'].geom_type=='Polygon'else list(masks['F_Mask'].geoms);central=next(g for g in front_parts if g.covers(Point(center)));bridges=[]
 for p in u.Pads():
  if p.GetNumber()not in {str(i)for i in range(1,17)}:continue
  point=Point(xy(p.GetPosition()));matching=[g for g in front_parts if g.covers(point)]
  bridges.append({'pin':p.GetNumber(),'matching_mask_components':len(matching),'gap_mm':central.distance(matching[0])if len(matching)==1 else -1})
 mask_gap=min(x['gap_mm']for x in bridges);check('actual_EP_to_peripheral_mask_bridge_0_10mm',len(bridges)==16 and mask_gap>=.1-.00001,minimum_gap_mm=mask_gap,per_pin=bridges)
 lands=unary_union([native_geom(p,P.F_Cu)for p in u.Pads()if p.GetAttribute()==P.PAD_ATTRIB_PTH]);non_ground=[]
 for f in b.GetFootprints():
  for p in f.Pads():
   if p.IsOnLayer(P.F_Cu)and p.GetNetname()!='GND':non_ground.append({'ref':f.GetReference(),'pin':p.GetNumber(),'net':p.GetNetname(),'gap_mm':lands.distance(native_geom(p,P.F_Cu))})
 nearest=min(non_ground,key=lambda x:x['gap_mm']);check('thermal_lands_to_other_net_copper',nearest['gap_mm']>=.15-.00001,minimum_gap_mm=nearest['gap_mm'],nearest_other_pad=nearest)

 check('formal_sources_unchanged_by_audit',all(Path(p).exists()and sha(Path(p))==h for p,h in hashes.items()))
 archive=out/'independent-cam';archive.mkdir(exist_ok=True)
 for p in cam.iterdir():
  if p.is_file():shutil.copy2(p,archive/p.name)
 (archive/'REVIEW_ONLY.txt').write_text('REVIEW ONLY — UNROUTED BOARD — NOT A MANUFACTURING RELEASE\nSix selected artwork layers from a four-copper-layer unrouted board, plus drill files, exported independently for U101 inspection.\nNo routing, solder-wicking, reflow, thermal or factory-process qualification is implied.\n')
 import cairosvg
 zoom=translate(box(-1.9,-1.9,1.9,1.9),xoff=center[0],yoff=center[1])
 svg=['<svg xmlns="http://www.w3.org/2000/svg" width="1800" height="710" viewBox="0 0 1800 710"><rect width="1800" height="710" fill="white"/>', '<g font-family="sans-serif" fill="#20242b" text-anchor="middle"><text x="900" y="38" font-size="30">U101 r13 — REVIEW ONLY — exported CAM</text>', '<text x="900" y="74" font-size="23">OSP; 4 open PTH Ø0.30 / land Ø0.60 mm; EP paste '+format(paste.area/1.68**2*100,'.2f')+'%</text></g>']
 def svg_geometry(g,ox,oy,color,stroke='none'):
  shapes=[g]if g.geom_type=='Polygon'else getattr(g,'geoms',[]);paths=[]
  for poly in shapes:
   if poly.geom_type!='Polygon':continue
   for ring in [poly.exterior,*poly.interiors]:
    points=list(ring.coords);paths.append('M'+' L'.join(format(ox+x*125,'.5f')+','+format(oy+y*125,'.5f')for x,y in points)+' Z')
  return '<path d="'+' '.join(paths)+'" fill="'+color+'" stroke="'+stroke+'" stroke-width="1.5" fill-rule="evenodd"/>'
 for ox,name,title,color in zip([300,900,1500],['F_Cu','F_Mask','F_Paste'],['F.Cu copper','F.Mask openings','F.Paste apertures'],['#b78a32','#92c9bc','#507ee1']):
  oy=380;svg.append('<text x="'+str(ox)+'" y="123" text-anchor="middle" font-family="sans-serif" font-size="25">'+title+'</text>');svg.append('<rect x="'+str(ox-237.5)+'" y="142.5" width="475" height="475" fill="#fafafa" stroke="#ddd"/>')
  for q in [-1.5,-1,-.5,0,.5,1,1.5]:
   x=ox+q*125;y=oy+q*125;svg.append('<path d="M'+str(x)+',142.5 V617.5 M'+str(ox-237.5)+','+str(y)+' H'+str(ox+237.5)+'" stroke="#e4e6ea" stroke-width="1"/>');svg.append('<text x="'+str(x)+'" y="641" text-anchor="middle" font-family="sans-serif" font-size="16">'+str(q)+'</text>')
  gg=translate(gerber(layer(name)).intersection(zoom),xoff=-center[0],yoff=-center[1]);svg.append(svg_geometry(gg,ox,oy,color));hh=translate(actual_holes,xoff=-center[0],yoff=-center[1]);svg.append(svg_geometry(hh,ox,oy,'white','#b82929'));svg.append('<text x="'+str(ox)+'" y="666" text-anchor="middle" font-family="sans-serif" font-size="17">Local X (mm), local Y positive down</text>')
 svg.append('<text x="900" y="699" text-anchor="middle" font-family="sans-serif" font-size="18">Red outline: actual Excellon drill. Nominal artwork; print/reflow and thermal performance remain unqualified.</text></svg>')
 svgtext=''.join(svg);(out/'U101-actual-CAM-review.svg').write_text(svgtext);cairosvg.svg2png(bytestring=svgtext.encode(),write_to=str(out/'U101-actual-CAM-review.png'))

 changes=[{'uuid':u,'type':n[0]}for u,n in bn.items()if on.get(u)!=n];removed=[{'uuid':u,'type':n[0]}for u,n in on.items()if u not in bn]
 result={'status':'PASS_U101_REVISION_SCOPE'if not errors else'FAIL','stage':'Unrouted placement; open PTH/OSP/paste geometry verified, no completed routing, thermal, factory capability or reflow qualification claim.','checks':checks,'errors':errors,'warnings':warnings,'paste_tolerance_sweep':tolerance,'tolerance_scope':'Sensitivity sweep only. It is not a claim that a drill, laser stencil, print spread or manual alignment capability is guaranteed by a manufacturer.','changed_board_objects':changes,'removed_board_objects':removed,'source_hashes':hashes,'baseline_board_sha256':sha(baseline),'baseline_revision':a.baseline_revision,'expected_preedit_project_sha256':a.expected_project_sha256,'native_CAD_scratch':str(project),'CAM_scratch':str(cam),'CAM_export_hashes':{p.name:sha(p)for p in cam.iterdir()if p.is_file()},'script_sha256':sha(Path(__file__))}
 (out/'independent-validation.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps({'status':result['status'],'checks':len(checks),'errors':errors},ensure_ascii=False,indent=2));return bool(errors)
if __name__=='__main__':raise SystemExit(main())

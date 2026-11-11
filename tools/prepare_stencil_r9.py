#!/usr/bin/env python3
"""Read native CAD + actual plotted Gerbers; create a paste-only DIY candidate.

Never modifies the source PCB. Run from repository root:
  PYTHONPATH=/path/to/dependencies python tools/prepare_stencil_r9.py
Tested dependencies: KiCad pcbnew/CLI 10.0.8, shapely==2.2.0,
gerbonara==1.6.2, matplotlib==3.11.2 (plots only). No dependency install is performed.
All coordinates in reports are KiCad absolute mm, with Y downward.
"""
from pathlib import Path
import sys, json, math, hashlib, subprocess, collections, uuid, argparse, shutil, csv
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--board',type=Path,default=ROOT/'hardware/devboard-r0/ESPaperPlay_Devboard.kicad_pcb')
parser.add_argument('--work-dir',type=Path,default=ROOT/'build/dfm-r9/stencil')
parser.add_argument('--review-dir',type=Path,default=ROOT/'hardware/devboard-r0/review-r9')
parser.add_argument('--output-dir',type=Path,default=ROOT/'hardware/devboard-r0/output/manufacturing/r9-review/stencil')
import pcbnew as P
from shapely.geometry import Polygon, Point, box, GeometryCollection
from shapely.ops import unary_union
from shapely.affinity import scale
from gerbonara import GerberFile
from gerbonara.utils import MM

SOURCE=ROOT/'hardware/devboard-r0/ESPaperPlay_Devboard.kicad_pcb'
OUT=ROOT/'build/dfm-r9/stencil'
SUPPORTED_R8_SHA256='1a4556d866cc1352a2c45b674c94d2f233edf28c3e003bd96c8f6caf1e630681'
MANUAL={'J501','J701','J601','J406'}
CRITICAL={'U101':'17','U201':'8','U203':'9','U802':'17','U301':'41','U803':'4'}
LAYERS={'F.Paste':P.F_Paste,'B.Paste':P.B_Paste,'F.Mask':P.F_Mask,'B.Mask':P.B_Mask}
SUFFIX={'F.Paste':'F_Paste.gtp','B.Paste':'B_Paste.gbp','F.Mask':'F_Mask.gts','B.Mask':'B_Mask.gbs'}
EPS=0.00005
def mm(x):return P.ToMM(x)
def xy(p):return (mm(p.x),mm(p.y))
def pt(p):return P.VECTOR2I(P.FromMM(p[0]),P.FromMM(p[1]))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def pathlabel(p):
 try:return str(Path(p).relative_to(ROOT))
 except ValueError:return str(p)
def r(x):return round(float(x),8)
def polys(s):
 if s.is_empty:return []
 return [s] if s.geom_type=='Polygon' else [p for p in s.geoms if p.geom_type=='Polygon']
def polyshape(ps):
 result=[]
 for i in range(ps.OutlineCount()):
  ln=ps.COutline(i);a=[xy(ln.CPoint(j)) for j in range(ln.PointCount())]
  hs=[]
  for h in range(ps.HoleCount(i)):
   ln=ps.CHole(i,h);hs.append([xy(ln.CPoint(j)) for j in range(ln.PointCount())])
  if len(a)>=3:result.append(Polygon(a,hs).buffer(0))
 return unary_union(result)
def shape(o,layer):
 ps=P.SHAPE_POLY_SET();o.TransformShapeToPolygon(ps,layer,0,P.FromMM(EPS),P.ERROR_INSIDE)
 return polyshape(ps)
def pad_hole(p):
 ps=P.SHAPE_POLY_SET();p.TransformHoleToPolygon(ps,0,P.FromMM(EPS),P.ERROR_INSIDE)
 return polyshape(ps)
def native_paste_features(b):
 result=[]
 for f in b.GetFootprints():
  for p in f.Pads():
   for name,layer in [('F.Paste',P.F_Paste),('B.Paste',P.B_Paste)]:
    if p.IsOnLayer(layer):
     margin=p.GetSolderPasteMargin(layer)
     assert margin.x==margin.y==0,(f.GetReference(),p.GetNumber(),'nonzero paste margin requires additional handling')
     result.append((f.GetReference(),name,shape(p,layer)))
  for g in f.GraphicalItems():
   if g.GetLayer() in [P.F_Paste,P.B_Paste]:result.append((f.GetReference(),P.LayerName(g.GetLayer()),shape(g,g.GetLayer())))
 return result
def gerber_geometry(path,native_features):
 file=GerberFile.open(path);records=[];whole=GeometryCollection()
 for idx,obj in enumerate(file.objects):
  s=GeometryCollection()
  for prim in obj.to_primitives(MM):
   polygon=Polygon(prim.to_arc_poly().approximate_arcs(EPS).outline).buffer(0)
   # Macro dark/clear operations are local to this aperture, not the whole layer.
   s=s.union(polygon) if prim.polarity_dark else s.difference(polygon)
  s=scale(s,yfact=-1,origin=(0,0))
  attrs=getattr(obj,'attrs',{})
  ref=attrs.get('.C',(None,))[0] if isinstance(attrs,dict) else None
  if ref is None and s.area>0:
   # Gerbonara 1.6.2 Region drops X2 attrs: recover owner from CAD, never guess by ref order.
   candidates=[(r0,s.intersection(ns).area) for r0,ln,ns in native_features if ln=='F.Paste' and s.intersects(ns)]
   candidates=[(rr,aa) for rr,aa in candidates if aa>s.area*.99]
   if candidates:ref=max(candidates,key=lambda z:z[1])[0]
  whole=whole.union(s) if obj.polarity_dark else whole.difference(s)
  records.append({'index':idx,'ref':ref,'class':type(obj).__name__,'shape':s})
 return records,whole
def metrics(s):
 return {'area_mm2':r(s.area),'perimeter_mm':r(s.length),'bounds_mm':[r(x) for x in s.bounds] if not s.is_empty else [],
   'components':len(polys(s)),'unsupported_islands':sum(len(p.interiors) for p in polys(s)),
   'area_ratio_at_thickness':{str(t):r(s.area/(s.length*t)) if s.length else None for t in [.10,.12,.125]}}
def snapshot(b):
 """Geometry invariants exclude paste-only objects, retain copper/mask/drill/placements/routes/zones."""
 rows=[]
 for f in b.GetFootprints():
  rows.append(('fp',f.GetReference(),xy(f.GetPosition()),f.GetOrientationDegrees(),f.IsDNP()))
  for p in f.Pads():
   ls=[l for l in p.GetLayerSet().Seq() if l not in (P.F_Paste,P.B_Paste)]
   if ls:
    rows.append(('pad',f.GetReference(),p.GetNumber(),p.m_Uuid.AsString(),xy(p.GetPosition()),xy(p.GetSize()),p.GetOrientationDegrees(),p.GetNetname(),p.GetDrillSize().x,p.GetDrillSize().y,tuple(ls),
     tuple((l,shape(p,l).normalize().wkb_hex) for l in ls if l in [P.F_Cu,P.B_Cu,P.In1_Cu,P.In2_Cu,P.F_Mask,P.B_Mask]),p.GetSolderMaskExpansion(P.F_Mask),p.GetSolderMaskExpansion(P.B_Mask)))
  for g in f.GraphicalItems():
   if g.GetLayer() not in (P.F_Paste,P.B_Paste):rows.append(('graphic',f.GetReference(),g.m_Uuid.AsString(),g.GetLayer(),str(g)))
 for t in b.GetTracks():
  row=('track',t.m_Uuid.AsString(),t.GetNetname(),xy(t.GetStart()),xy(t.GetEnd()),t.GetLayer(),mm(t.GetWidth(P.F_Cu) if t.GetClass()=='PCB_VIA' else t.GetWidth()))
  if t.GetClass()=='PCB_VIA':row+=('via',mm(t.GetDrillValue()),tuple(t.GetLayerSet().Seq()),t.IsTented(P.F_Mask),t.IsTented(P.B_Mask))
  rows.append(row)
 for z in b.Zones():rows.append(('zone',z.m_Uuid.AsString(),z.GetNetname(),tuple(z.GetLayerSet().Seq()),polyshape(z.Outline()).normalize().wkb_hex))
 # str(SWIG object) contains memory addresses: only stable identifiers are sufficient for unmodified non-paste graphics.
 rows=[rr[:-1] if rr[0]=='graphic' else rr for rr in rows]
 return hashlib.sha256(json.dumps(sorted(rows,key=str),sort_keys=True).encode()).hexdigest()
def clear_footprint_paste(f,reason,delta):
 for p in list(f.Pads()):
  removed=[P.LayerName(l) for l in (P.F_Paste,P.B_Paste) if p.IsOnLayer(l)]
  if not removed:continue
  delta.append({'action':'remove_paste','reason':reason,'ref':f.GetReference(),'pad':p.GetNumber(),'uuid':p.m_Uuid.AsString(),'layers':removed})
  ls=p.GetLayerSet();ls.RemoveLayer(P.F_Paste);ls.RemoveLayer(P.B_Paste)
  if list(ls.Seq()):p.SetLayerSet(ls)
  else:f.Delete(p)
 for g in list(f.GraphicalItems()):
  if g.GetLayer() in (P.F_Paste,P.B_Paste):
   delta.append({'action':'remove_paste_graphic','reason':reason,'ref':f.GetReference(),'uuid':g.m_Uuid.AsString(),'layer':P.LayerName(g.GetLayer())});f.Delete(g)
def derive(b):
 delta=[]
 for f in list(b.GetFootprints()):
  if f.IsDNP():clear_footprint_paste(f,'default_DNP',delta)
  if f.GetReference() in MANUAL:clear_footprint_paste(f,'user_selected_hand_soldered_connector',delta)
  if f.GetReference()=='U301':
   for p in list(f.Pads()):
    if p.GetNumber()=='' and p.IsOnLayer(P.F_Paste) and not p.IsOnLayer(P.F_Cu):
     delta.append({'action':'remove_paste','reason':'ESP32_optional_EPAD_not_soldered_DIY_default','ref':'U301','pad':'EPAD_window','uuid':p.m_Uuid.AsString()});f.Delete(p)
  if f.GetReference()=='U803':
   targets=[p for p in f.Pads() if p.GetShape()==P.PAD_SHAPE_CUSTOM and p.IsOnLayer(P.F_Paste) and not p.IsOnLayer(P.F_Cu)]
   assert len(targets)==1
   old=targets[0];ring=shape(old,P.F_Paste);centre=(61.0,62.0)
   assert xy(f.GetPosition())==(61.,61.) and f.GetOrientationDegrees()==0,'re-evaluate mic bridge placement if footprint moved'
   cuts=unary_union([box(centre[0]-.075,centre[1]-1,centre[0]+.075,centre[1]+1),box(centre[0]-1,centre[1]-.075,centre[0]+1,centre[1]+.075)])
   parts=polys(ring.difference(cuts));assert len(parts)==4
   old_uuid=old.m_Uuid.AsString();f.Delete(old)
   delta.append({'action':'replace_paste_ring_with_4_segments','reason':'support_stencil_central_island','ref':'U803','source_uuid':old_uuid,'steel_bridge_width_mm':.15,'before':metrics(ring),'after':metrics(unary_union(parts)),'qualification':'engineering_candidate_requires_print_reflow_and_acoustic_seal_validation_not_PUI_specified_bridge_width'})
   for i,s in enumerate(sorted(parts,key=lambda q:q.centroid.wkt)):
    anchor=s.representative_point();origin=(anchor.x,anchor.y)
    p=P.PAD(f);p.SetNumber('');p.SetAttribute(P.PAD_ATTRIB_SMD);p.SetShape(P.PAD_SHAPE_CUSTOM)
    layers=P.LSET();layers.AddLayer(P.F_Paste);p.SetLayerSet(layers)
    p.SetAnchorPadShape(P.F_Paste,P.PAD_SHAPE_CIRCLE);p.SetSize(pt((.01,.01)));p.SetPosition(pt(origin));p.SetOrientationDegrees(0)
    points=P.VECTOR_VECTOR2I()
    for x,y in list(s.exterior.coords)[:-1]:points.append(pt((x-origin[0],y-origin[1])))
    p.AddPrimitivePoly(P.F_Paste,points,0,True)
    p.SetUuid(P.KIID(str(uuid.uuid5(uuid.NAMESPACE_URL,sha(SOURCE)+':U803-paste-bridge:'+str(i)))))
    f.Add(p)
 return delta
def plot_board(board,outdir):
 outdir.mkdir(exist_ok=True)
 subprocess.run(['kicad-cli','pcb','export','gerbers','--layers',','.join(LAYERS),'--output',str(outdir),str(board)],check=True,capture_output=True,text=True)
def report_board(boardpath,plotdir):
 b=P.LoadBoard(str(boardpath));native=native_paste_features(b);layers={};raw={}
 for lname in LAYERS:
  matches=list(plotdir.glob('*-'+SUFFIX[lname]));assert len(matches)==1
  records,geom=gerber_geometry(matches[0],native);raw[lname]=(records,geom)
  grouped=collections.defaultdict(list)
  for o in records:grouped[o['ref']].append(o['shape'])
  layers[lname]={'file':pathlabel(matches[0]),'sha256':sha(matches[0]),'objects':len(records),'physical_components':len(polys(geom)),'union_area_mm2':r(geom.area),
   'by_ref':{str(ref):metrics(unary_union(shapes)) for ref,shapes in sorted(grouped.items(),key=lambda kv:str(kv[0]))}}
 pads=[];holes=[];tht_paste=[];fprefs={f.GetReference():f for f in b.GetFootprints()}
 for f in b.GetFootprints():
  for p in f.Pads():
   if p.IsOnLayer(P.F_Cu) and p.GetAttribute()==P.PAD_ATTRIB_SMD:pads.append((f.GetReference(),p,shape(p,P.F_Cu)))
   if p.GetDrillSize().x:
    h=pad_hole(p)
    row={'kind':'NPTH' if p.GetAttribute()==P.PAD_ATTRIB_NPTH else 'footprint_PTH','ref':f.GetReference(),'pad':p.GetNumber(),'uuid':p.m_Uuid.AsString(),'centre_mm':xy(p.GetPosition()),'drill_mm':xy(p.GetDrillSize()),'shape':h,
         'explicit_F_Mask':p.IsOnLayer(P.F_Mask),'explicit_B_Mask':p.IsOnLayer(P.B_Mask)}
    holes.append(row)
    if p.IsOnLayer(P.F_Paste) or p.IsOnLayer(P.B_Paste):tht_paste.append({k:v for k,v in row.items() if k!='shape'})
 for v in b.GetTracks():
  if v.GetClass()=='PCB_VIA':
   holes.append({'kind':'native_via','uuid':v.m_Uuid.AsString(),'centre_mm':xy(v.GetPosition()),'drill_mm':[mm(v.GetDrillValue())]*2,'net':v.GetNetname(),
    'diameter_mm':mm(v.GetWidth(P.F_Cu)),'tenting_setting_F':v.IsTented(P.F_Mask),'tenting_setting_B':v.IsTented(P.B_Mask),'shape':Point(xy(v.GetPosition())).buffer(mm(v.GetDrillValue())/2,quad_segs=128)})
 vip=[];paste_drills=[];near=[]
 for h in holes:
  hs=h['shape'];smt=[{'ref':rf,'pad':p.GetNumber(),'overlap_mm2':r(hs.intersection(s).area)} for rf,p,s in pads if hs.intersection(s).area>1e-6]
  hm={k:v for k,v in h.items() if k!='shape'}
  hm.update({'intersected_SMT_copper':smt,'F_Mask_open_hole_fraction':r(hs.intersection(raw['F.Mask'][1]).area/hs.area),
             'B_Mask_open_hole_fraction':r(hs.intersection(raw['B.Mask'][1]).area/hs.area),
             'F_Paste_overlap_hole_mm2':r(hs.intersection(raw['F.Paste'][1]).area),
             'drill_to_F_Mask_opening_gap_mm':r(hs.distance(raw['F.Mask'][1])),
             'drill_to_B_Mask_opening_gap_mm':r(hs.distance(raw['B.Mask'][1]))})
  if smt:vip.append(hm)
  elif h['kind']=='native_via':
   outer=Point(h['centre_mm']).buffer(h['diameter_mm']/2,quad_segs=128)
   contacts=[{'ref':rf,'pad':p.GetNumber(),'annular_overlap_mm2':r(outer.intersection(s).area),'drill_to_SMT_copper_gap_mm':r(hs.distance(s))} for rf,p,s in pads if outer.intersection(s).area>1e-8]
   if contacts:
    hm['annular_copper_contacts_only']=contacts;near.append(hm)
  if hm['F_Paste_overlap_hole_mm2']>1e-6:paste_drills.append(hm)
 critical={}
 for ref,padnum in CRITICAL.items():
  f=fprefs[ref];cu=unary_union([shape(p,P.F_Cu) for p in f.Pads() if p.GetNumber()==padnum and p.GetAttribute()==P.PAD_ATTRIB_SMD])
  own=unary_union([o['shape'] for o in raw['F.Paste'][0] if o['ref']==ref]);ep=own.intersection(cu)
  critical[ref]={'pad':padnum,'copper_area_mm2':r(cu.area),'paste_area_inside_copper_mm2':r(ep.area),'paste_coverage_percent':r(100*ep.area/cu.area),
   'EP_apertures':metrics(ep),'holes_in_copper':[h for h in vip if any(v['ref']==ref and v['pad']==padnum for v in h['intersected_SMT_copper'])]}
 flat=[]
 for o in raw['F.Paste'][0]:
  for s in polys(o['shape']):flat.append({'object':o['index'],'ref':o['ref'],**metrics(s)})
 flat.sort(key=lambda z:z['area_ratio_at_thickness']['0.1'] or 999)
 # Actual soldermask gap for native SMD pad pairs within each relevant IC/connector.
 webs={}
 for ref in sorted(set(CRITICAL)|MANUAL):
  f=fprefs[ref];pp=[]
  for p in f.Pads():
   if p.GetNumber() and p.GetAttribute()==P.PAD_ATTRIB_SMD and p.IsOnLayer(P.F_Mask):
    s=shape(p,P.F_Mask).buffer(mm(p.GetSolderMaskExpansion(P.F_Mask)),quad_segs=64)
    pp.append((p,s))
  gaps=[]
  for i,(p,s) in enumerate(pp):
   for q,t in pp[i+1:]:
    if p.GetNumber()==q.GetNumber() or (p.GetNetname() and p.GetNetname()==q.GetNetname()):continue
    dist=s.distance(t)
    if dist<.31:gaps.append({'pads':[p.GetNumber(),q.GetNumber()],'gap_mm':r(dist)})
  webs[ref]={'minimum_different_net_pad_mask_gap_mm':min((q['gap_mm'] for q in gaps),default=None),'pairs_below_0_15mm':[q for q in gaps if q['gap_mm']<.1499],
     'method':'native pad geometry plus effective mask expansion; actual plotted mask union used separately for hole exposure'}
 dnp=sorted(f.GetReference() for f in b.GetFootprints() if f.IsDNP())
 return {'source':pathlabel(boardpath),'sha256':sha(boardpath),'kicad_version':P.Version(),'method':{'gerber':'Gerbonara 1.6.2 actual aperture macros/regions, shapely union, curves <=0.00005 mm approximation; zero-width fractured polygon slits healed with buffer(0)','coverage':'actual plotted F.Paste intersected with native SMD copper geometry ERROR_INSIDE (custom pads match plotted polygon)','area_ratio':'A/(P*t), P includes inner wall perimeters; screening at 0.66 is not process qualification','coordinates':'absolute KiCad mm, Y downward'},
 'global_mask_expansion_mm':mm(b.GetDesignSettings().m_SolderMaskExpansion),'global_min_mask_web_mm':mm(b.GetDesignSettings().m_SolderMaskMinWidth),
 'layers':layers,'critical':critical,'dnp_refs':dnp,'dnp_paste_refs':sorted(set(o['ref'] for o in raw['F.Paste'][0] if o['ref'] in dnp)),
 'drilled_pads_with_paste_layer':tht_paste,'holes_intersecting_SMT_copper':vip,'native_vias_annular_contact_only':near,'holes_intersecting_F_Paste':paste_drills,'stencil_apertures_sorted_by_AR':flat,'mask_webs':webs},raw
def drawings(raw,candidate):
 import matplotlib;matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 def draw(ax,s,col,alpha=1):
  for p in polys(s):
   xs,ys=p.exterior.xy;ax.fill(xs,ys,facecolor=col,alpha=alpha)
   for ring in p.interiors:
    xs,ys=ring.xy;ax.fill(xs,ys,facecolor='white')
 fig,axes=plt.subplots(1,2,figsize=(10,5))
 for ax,data,title in zip(axes,[raw,candidate],['Raw U803: unsupported center island','DIY candidate: four 0.15 mm steel bridges']):
  ss=unary_union([q['shape'] for q in data['F.Paste'][0] if q['ref']=='U803']);draw(ax,ss,'#D07825');draw(ax,Point(61,62).buffer(.3),'#222222')
  ax.set_title(title,fontsize=11);ax.set_xlim(59.45,62.55);ax.set_ylim(63.05,59.05);ax.set_aspect('equal');ax.grid(alpha=.2);ax.set_xlabel('Absolute X / mm');ax.set_ylabel('Absolute Y / mm')
 fig.tight_layout();fig.savefig(OUT/'mic-stencil-before-after.png',dpi=180);plt.close(fig)
def source_inventory():
 sources=[
  ('BQ24074','hardware/reference/power/bq24074.pdf','https://www.ti.com/lit/ds/symlink/bq24074.pdf','PDF pp.53–54, RGT0016C package drawing 4222419/E 07/2025; 0.125 mm stencil, 85% EP coverage, optional via handling'),
  ('TPS63802','hardware/reference/power/tps63802.pdf','https://www.ti.com/lit/ds/symlink/tps63802.pdf','PDF p.37, DLA0010A; 0.10 mm stencil, split pad 8, 83% nominal coverage'),
  ('MAX17048','hardware/reference/power/max17048.pdf','https://www.analog.com/media/en/technical-documentation/data-sheets/MAX17048-MAX17049.pdf','package TDFN 8, 2x2 mm, separate land-pattern review in r3'),
  ('MAX98357A','hardware/reference/power/max98357a.pdf','https://www.analog.com/media/en/technical-documentation/data-sheets/MAX98357A-MAX98357B.pdf','TQFN package T1633-4; see ADI generic QFN assembly guide for stencil'),
  ('PUI microphone','hardware/reference/peripherals/DMM-4026-B-I2S-R.pdf','https://api.puiaudio.com/filename/DMM-4026-B-I2S-R.pdf','Rev A 2021-05-26, PDF p.4 reflow limits/no cleaning, p.6 package bottom view'),
  ('LAILAN touch connector','hardware/reference/closure-r4/files/mechanical/lail-fpc-cdx01-6p.pdf',None,'Recommended Metal-Mask t=0.10 mm; current PCB has separate 0.25x0.65 mm paste rectangles over 0.30x0.80 mm copper'),
  ('PUI MEMS application guide',None,'https://puiaudio.com/wp-content/uploads/2022/08/Wide-BandMEMSMicrophonesApplicationGuide.pdf','Manufacturer-authored PDF mirrored at https://www.mouser.com/pdfDocs/puiaudiowide-bandmemsmicrophonesapplicationguide.pdf; reviewed pp.4,7–9; primary host captcha prevented local download; 0.10–0.12 mm stencil, Type 4 no-clean low-flux, >=0.5 mm NPTH'),
  ('ADI QFN assembly guide',None,'https://www.analog.com/en/resources/app-notes/smt-assembly-and-pcb-design-guidelines-for-maxims-standard-wirebonded-quad-flatpack.html','4 mil 1:1 perimeter apertures, 50–80% EP coverage, AR>0.66, profile at actual solder joints; general guidance not package-specific approval'),
  ('TI QFN/SON attachment SLUA271C',None,'https://www.ti.com/lit/an/slua271a/slua271a.pdf','Current fetched document Rev C Dec2023, pp.7–8 via/mask, p.11 AR and thermal-pad guidance. Does not mandate filled/capped vias in every case.'),
  ('Espressif module v1.8',None,'https://www.espressif.com/sites/default/files/documentation/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf','PDF p.41: EPAD soldering optional for module, improves thermal performance; too much paste can lift module. Not applicable to other IC ground/thermal pads.')]
 result=[]
 for name,local,url,evidence in sources:
  row={'name':name,'url':url,'evidence':evidence,'retrieved_or_reviewed':'2026-11-11'}
  if local:
   p=ROOT/local;row.update({'local_file':local,'exists':p.exists(),'sha256':sha(p) if p.exists() else None,'distribution':'existing repository-local reference cache; not included in r9 manufacturing package'})
  else:row.update({'local_file':None,'sha256':None,'evidence_mode':'web tool primary-source content; no downloaded binary or fabricated file hash','distribution':'URL only; document not included in r9 manufacturing package'})
  result.append(row)
 return result
def chinese_report(j):
 o=j['original'];c=j['DIY_candidate'];a=c['stencil_apertures_sorted_by_AR'][0]
 near=c['native_vias_annular_contact_only'];nearest=min(near,key=lambda h:h['drill_to_F_Mask_opening_gap_mm'])
 coverage='\n'.join(f"| {ref} / {o['critical'][ref]['pad']} | {o['critical'][ref]['paste_coverage_percent']:.2f}% | {c['critical'][ref]['paste_coverage_percent']:.2f}% | {len(o['critical'][ref]['holes_in_copper'])} |" for ref in CRITICAL)
 return f'''# r9 阻焊与 DIY 钢网审查

结论：已生成独立钢网工程候选；**0.10 mm 钢片、U803 四条 0.15 mm 支撑桥尚需试印与实际回流验证**。正式 r8 PCB、封装库、电路及 BOM 未修改。加工目录只有修正后的正面焊膏 Gerber，原生焊膏、派生 PCB 和比较文件留在 build 中；禁止将原生 F.Paste 直接作为本次钢网。

审查源：`{o['source']}`，SHA-256 `{j['source_sha256_unchanged']}`；KiCad {o['kicad_version']}。详见同目录 `stencil-audit.json` 的逐开窗面积/周长/面积比、逐孔暴露率、84 项派生操作和原厂资料索引。

## 实际修正与装配划分

- 六个 DNP 位置 C501/C502/J301/J302/J303/R108 均不印膏。原生输出仍含其中三个 SMD 位 C501/C502/R108 的共 6 个开窗；三个 DNP 排针原本无 paste。
- 按用户选择，J501 USB、J701 microSD、J601 屏幕 FPC、J406 触摸 FPC 全部不印膏，后续手焊；排针、接线端子等 THT 同样不印膏。原生 J501 的 4 个 PTH 外壳槽孔原来带 paste，候选已消除。细脚接口仍需细尖/合适刀头、放大检查、控量助焊剂与吸锡带；尤其 USB 的靠壳焊点应确认烙铁可达后再固定外壳。若以后改成回流，必须重建接口钢网版本，不能手工随意补孔。
- U301 保留 40 个外围引脚印膏，取消中央 EPAD 的 9 个窗口，铜、12 个孔、接地保持原样。Espressif v1.8 PDF p.41 允许该模组 EPAD 不焊；代价是热路径不同，应验证持续 Wi-Fi/CPU/PSRAM 负载下温升及稳定性。这不适用于 U101/U201/U203/U802 的地/热焊盘。
- U803 原始闭合环在普通激光钢网上会留下悬空中心钢片。Gerber 内用于表达孔洞的零宽折返不是实体支撑桥。候选仅分割 paste 为四段，保持原铜环与 0.60 mm NPTH；四条桥宽 0.15 mm 属工程建议，不是 PUI 指定尺寸。回流后应形成连续声学密封，必须验证声孔无锡/助焊剂污染和漏声。

![麦克风钢网前后比较：橙色为开窗、黑色为PCB声孔，白色为保留钢片](stencil-microphone.png)

原始正面焊膏：**{o['layers']['F.Paste']['objects']} 个绘制对象，{o['layers']['F.Paste']['physical_components']} 个几何独立开窗，210 个位号**。候选：**{c['layers']['F.Paste']['objects']} 个对象/开窗，203 个位号**；两版背面焊膏均为空。原始 USB 有共用焊盘的重叠绘制，统计已按实际几何合并，未重复计面积。

## 焊膏覆盖和厚度

表中面积来自实际 Gerber 与铜焊盘相交；圆角/原生自定义多边形会使数值与标注矩形面积略有差别。覆盖率未扣钻孔，表示印膏设计覆盖，不等于回流后的有效焊接面积。

| 器件 / 焊盘 | 原始覆盖 | DIY 候选覆盖 | 铜焊盘内孔数 |
| --- | ---: | ---: | ---: |
{coverage}

U101 保留 1.55×1.55 mm 单窗口：TI RGT0016C 示例是 **0.125 mm、85%**，本次 0.10 mm 在同开孔下膏体积少 20%，不能仅凭面积比通过就认为焊量足够。U201 的 pad 8 分成两个 0.55×0.25 mm 窗口，原厂明确采用 **0.10 mm、约 83%**。U203 四个 0.32×0.48 mm 圆角窗口和 U802 四个 0.50×0.50 mm 窗口保持；ADI 通用 QFN 指南的 EP 50–80% 范围可作工艺起点，不能替代试焊。

U803 六个信号脚 paste 为 0.51×0.34 mm，对 0.60×0.40 mm 铜，线性 85%、面积 72.25%。分段地环覆盖为 {c['critical']['U803']['paste_coverage_percent']:.2f}%，印膏边缘到声孔最小约 0.2475 mm。PUI 指南建议 0.10–0.12 mm 钢网、Type 4 免清洗低助焊剂锡膏；不清洗、不超声、不对声孔吸/吹气，遵守具体料号回流曲线。DMM 数据页上限 260°C/30 s、217°C 以上≤90 s 不是炉温目标，应以锡膏曲线和板上实测温度确定曲线。

按 A/(开孔周长×钢片厚度) 计算，候选最小面积比在 **{a['ref']}：0.10 mm 为 {a['area_ratio_at_thickness']['0.1']:.4f}，0.12 mm 为 {a['area_ratio_at_thickness']['0.12']:.4f}，0.125 mm 为 {a['area_ratio_at_thickness']['0.125']:.4f}**。均高于通用 0.66 筛查值，但不能证明转移率、焊量或桥接良率。0.10 mm 是兼顾 U201/PUI 的首轮试印候选；优先精密激光、电抛光钢网，禁止厂商未经复核整体扩大/缩小开孔。

## 孔与阻焊的实际关系

11 个原生地/热过孔和 U301 封装自带 12 个 PTH 共 **23 孔**落在 SMD 铜焊盘内；实际 Gerber 中正面孔口 **100% 在阻焊开窗内**，背面均无开窗。原生 vias 的 front/back tenting=true 不能覆盖被另一个焊盘开窗暴露的孔；U301 PTH 的实际层集合为 `*.Cu F.Mask`，自身已正面开窗且与中央 SMD 开窗重叠，背面无 B.Mask。

另有 **44 个原生过孔仅铜环接触 SMD 铜，钻孔并未进入 SMD 铜**；实际 Gerber 中它们的孔口名义上均被 mask 遮盖、没有 paste 覆盖。然而最小孔边到正面 mask 开口距离仅 **{nearest['drill_to_F_Mask_opening_gap_mm']:.5f} mm**，孔位 {nearest['centre_mm']}，邻近 Q201.2；另有若干仅 0.025 mm 余量。不能将理想图形遮盖当作阻焊对位公差下的可靠盖油。逐孔 mask 暴露、间距、原始/候选 paste 覆盖见 `special-hole-register.csv` 和 JSON 的 `native_vias_annular_contact_only`，本轮仅提交 CAM 确认，不改板。

U101 4 孔、U201 2 孔、U802 4 孔，共 **10 个 0.20 mm 孔直接在候选印膏下**。U203 1 孔和 U301 12 孔没有直接印膏，但回流时仍可能吸走附近熔锡；取消 U301 可选 EPAD 印膏只降低该模组的装配复杂性，未改变孔工艺。孔坐标、UUID、重叠面积见 JSON。

盖油、塞孔和树脂填孔后镀铜封帽是不同工艺。本文件没有生成任何填孔/封帽要求的制造证明。对其余 11 个 IC 地/热孔，应由板厂确认实际可做的孔处理及装配接受条件，再结合试焊确定；TI 示例允许填/塞/盖等路线，不能误写为所有孔只允许填孔封帽。不要从背面补锡去补偿不可见的热焊盘缺陷。

阻焊原图保持不变：全局扩展 0、最小桥宽规则 0；U101/U201 局部每边 +0.05 mm，U803 +0.025 mm。关键异网焊盘间最窄设计桥：U201 0.150 mm、U101 0.160 mm、U802 对角 0.1768 mm、U203/USB/触摸 0.200 mm、屏幕 FPC/microSD 0.250 mm。多数零扩展焊盘没有额外对位余量，需要板厂 CAM 确认开窗、最小桥及对位公差。**不要统一加 0.05 mm**：U802 对角桥会缩至约 0.0768 mm。0.150 mm 也不能直接称作满足 6 mil（0.1524 mm）。

## 验证与复现

脚本固定校验支持的 r8 源哈希，拒绝不同源板沿用本次工艺。已断言：铜、阻焊、孔、网络、布局、布线不变；F.Mask/B.Mask 实际 Gerber 几何一致；最终位号集合恰好为原生实装 SMD 207 位扣除手焊接口 4 位；U301外围40脚印膏、中央不印膏；背面无paste；U803没有悬空钢岛。DNP、手焊接口和封装 PTH/NPTH 焊盘自身无 paste 定义；**这不表示所有钻孔都避开印膏，10 个原生热过孔仍被IC热焊盘印膏覆盖**。未做试印、回流、X-ray、热或声学实物验证。

```sh
# 使用带 pcbnew 的系统 Python；在独立依赖目录或虚拟环境提供下列包。
# gerbonara==1.6.2 shapely==2.2.0 matplotlib==3.11.2
PYTHONPATH=/path/to/dependencies python tools/prepare_stencil_r9.py
```

可用 `--board` 指定同一已审查 r8 板的副本位置；新版本板会被固定哈希拒绝，需要重审并更新脚本。`--work-dir`、`--review-dir`、`--output-dir` 指定输出位置；脚本不自动安装软件、不改源 PCB、不联系或下单。正式候选文件：`{j['published_candidate']['file']}`。

原厂依据：[TI BQ24074](https://www.ti.com/lit/ds/symlink/bq24074.pdf)，[TI TPS63802](https://www.ti.com/lit/ds/symlink/tps63802.pdf)，[TI QFN/SON SLUA271C](https://www.ti.com/lit/an/slua271a/slua271a.pdf)，[ADI QFN 装配指南](https://www.analog.com/en/resources/app-notes/smt-assembly-and-pcb-design-guidelines-for-maxims-standard-wirebonded-quad-flatpack.html)，[PUI 具体麦克风](https://api.puiaudio.com/filename/DMM-4026-B-I2S-R.pdf)，[PUI MEMS 指南（原厂文件的分销商镜像）](https://www.mouser.com/pdfDocs/puiaudiowide-bandmemsmicrophonesapplicationguide.pdf)，[Espressif v1.8](https://www.espressif.com/sites/default/files/documentation/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf)。页码、原始本地文件 SHA-256 和下载限制见 JSON sources；未把资料中没有规定的桥宽当作原厂要求。
'''
def preflight_paths(args):
 """Resolve symlinks and reject source/output collisions before creating any directory."""
 source=args.board.expanduser().resolve(strict=True)
 work=args.work_dir.expanduser().resolve()
 review=args.review_dir.expanduser().resolve()
 output=args.output_dir.expanduser().resolve()
 formal=(ROOT/'hardware/devboard-r0/ESPaperPlay_Devboard.kicad_pcb').resolve()
 if work==formal.parent or formal.parent in work.parents:
  raise ValueError('Scratch --work-dir must be outside the formal hardware/devboard-r0 tree')
 for directory in (work,review,output,work/'native-plot',work/'diy-candidate-plot'):
  if directory in (source,formal) or (directory.exists() and not directory.is_dir()):
   raise ValueError(f'Output directory collides with a file: {directory}')
 variant_name='ESPaperPlay_Devboard_DIY_stencil_candidate'
 writable=[work/(variant_name+'.kicad_pcb'),work/'original-audit.json',work/'stencil-audit.json',work/'mic-stencil-before-after.png',
           review/'stencil-audit.json',review/'stencil-review.md',review/'stencil-microphone.png',review/'special-hole-register.csv',output/'ESPaperPlay_Devboard-DIY-F_Paste.gtp']
 for directory,stem in [(work/'native-plot',source.stem),(work/'diy-candidate-plot',variant_name)]:
  writable.extend(directory/(stem+'-'+suffix) for suffix in SUFFIX.values())
  writable.append(directory/(stem+'-job.gbrjob'))
 resolved=[p.resolve() for p in writable]
 if len(set(resolved))!=len(resolved):raise ValueError('Conflicting work/review/manufacturing output paths')
 for p in resolved:
  if p in (source,formal):raise ValueError(f'Refusing to overwrite protected source PCB: {p}')
  if p.exists() and p.is_dir():raise ValueError(f'Output file path is an existing directory: {p}')
 return source,work,review,output
def write_special_holes(j,path):
 original=j['original'];candidate=j['DIY_candidate']
 assert len(original['holes_intersecting_SMT_copper'])==23
 assert len(original['native_vias_annular_contact_only'])==44
 candidate_holes={h['uuid']:h for k in ['holes_intersecting_SMT_copper','native_vias_annular_contact_only'] for h in candidate[k]}
 rows=[]
 for kind,key in [('drill_in_SMT_copper','holes_intersecting_SMT_copper'),('annular_contact_only','native_vias_annular_contact_only')]:
  for h in original[key]:
   contacts=h['intersected_SMT_copper'] or h.get('annular_copper_contacts_only',[])
   c=candidate_holes[h['uuid']]
   rows.append({'source_sha256':j['source_sha256_unchanged'],'classification':kind,'object_kind':h['kind'],'uuid':h['uuid'],'x_mm':h['centre_mm'][0],'y_mm':h['centre_mm'][1],
    'drill_x_mm':h['drill_mm'][0],'drill_y_mm':h['drill_mm'][1],'associated_pads':';'.join(q['ref']+'.'+q['pad'] for q in contacts),'net':h.get('net','GND' if h.get('ref')=='U301' else ''),
    'explicit_footprint_F_Mask':h.get('explicit_F_Mask',''),'explicit_footprint_B_Mask':h.get('explicit_B_Mask',''),'native_via_tenting_setting_F':h.get('tenting_setting_F',''),'native_via_tenting_setting_B':h.get('tenting_setting_B',''),
    'actual_F_Mask_open_hole_fraction':h['F_Mask_open_hole_fraction'],'actual_B_Mask_open_hole_fraction':h['B_Mask_open_hole_fraction'],
    'drill_to_F_Mask_opening_gap_mm':h['drill_to_F_Mask_opening_gap_mm'],'drill_to_B_Mask_opening_gap_mm':h['drill_to_B_Mask_opening_gap_mm'],
    'raw_F_Paste_overlap_hole_mm2':h['F_Paste_overlap_hole_mm2'],'DIY_F_Paste_overlap_hole_mm2':c['F_Paste_overlap_hole_mm2'],
    'process_status':'CAM_hole_treatment_and_actual_assembly_pending; mask_tenting_is_not_fill_and_copper_cap'})
 with path.open('w',newline='',encoding='utf-8') as f:
  writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(sorted(rows,key=lambda x:(x['classification'],x['x_mm'],x['y_mm'])))
def main():
 global SOURCE,OUT
 args=parser.parse_args()
 SOURCE,OUT,args.review_dir,args.output_dir=preflight_paths(args)
 source_hash=sha(SOURCE)
 assert source_hash==SUPPORTED_R8_SHA256,'Unsupported PCB revision: r9 stencil process is pinned to reviewed r8 SHA-256; re-review before changing this guard'
 OUT.mkdir(parents=True,exist_ok=True);args.review_dir.mkdir(parents=True,exist_ok=True);args.output_dir.mkdir(parents=True,exist_ok=True)
 plot_board(SOURCE,OUT/'native-plot')
 original,raw=report_board(SOURCE,OUT/'native-plot')
 (OUT/'original-audit.json').write_text(json.dumps(original,ensure_ascii=False,indent=2)+'\n')
 b=P.LoadBoard(str(SOURCE));before=snapshot(b)
 expected_paste_refs={f.GetReference() for f in b.GetFootprints() if f.GetAttributes()&P.FP_SMD and not f.IsDNP()}-MANUAL
 assert len(expected_paste_refs)==203
 delta=derive(b);assert snapshot(b)==before,'protected non-paste geometry changed'
 variant=OUT/'ESPaperPlay_Devboard_DIY_stencil_candidate.kicad_pcb';P.SaveBoard(str(variant),b)
 reopened=P.LoadBoard(str(variant));assert snapshot(reopened)==before,'save/reload changed non-paste invariants'
 plot_board(variant,OUT/'diy-candidate-plot')
 candidate,cr=report_board(variant,OUT/'diy-candidate-plot')
 actual_paste_refs=set(candidate['layers']['F.Paste']['by_ref'])
 assert actual_paste_refs==expected_paste_refs and len(actual_paste_refs)==203,'Wrong assembly population in stencil'
 assert candidate['layers']['B.Paste']['objects']==0 and candidate['layers']['B.Paste']['union_area_mm2']==0,'Unexpected backside paste'
 assert not candidate['dnp_paste_refs']
 assert not candidate['drilled_pads_with_paste_layer']
 assert not (MANUAL&set(candidate['layers']['F.Paste']['by_ref']))
 assert candidate['critical']['U301']['paste_coverage_percent']==0
 assert len([o for o in cr['F.Paste'][0] if o['ref']=='U301'])==40
 assert candidate['layers']['F.Paste']['by_ref']['U301']['components']==40
 module=next(f for f in reopened.GetFootprints() if f.GetReference()=='U301')
 assert {p.GetNumber() for p in module.Pads() if p.IsOnLayer(P.F_Paste)}=={str(i) for i in range(1,41)},'U301 peripheral paste changed'
 assert candidate['layers']['F.Paste']['by_ref']['U803']['unsupported_islands']==0
 for side in ['F.Mask','B.Mask']:
  assert raw[side][1].symmetric_difference(cr[side][1]).area<1e-9,side+' changed'
 assert source_hash==sha(SOURCE),'source modified'
 result={'status':'engineering_candidate_not_fabrication_release','source_sha256_unchanged':source_hash,'protected_geometry_sha256':before,'delta':delta,'original':original,'DIY_candidate':candidate,
 'assertions':{'source_matches_pinned_r8_revision':True,'source_unchanged':True,'native_copper_mask_drill_routes_placement_invariants_unchanged':True,'plotted_F_B_mask_geometry_unchanged':True,'paste_refs_exactly_203_fitted_SMD_minus_manual':True,'B_Paste_empty':True,'DNP_paste_absent':True,'manual_connectors_paste_absent':True,'footprint_PTH_NPTH_pads_have_no_paste_layers':True,'U301_exactly_40_peripheral_paste_pads':True,'U301_optional_EPAD_paste_absent':True,'U803_no_unsupported_stencil_island':True},
 'limits':['Steel bridge width is an engineering proposal, not a manufacturer-approved stencil prescription.','No reflow, print transfer, thermal or acoustic-seal validation has been performed.','Global solder-mask zero expansion has no registration allowance on most pads; fabricator must assess process margins.','Tented via setting does not cover a hole which lies inside another open soldermask pad.','Gerber parser and polygons do not prove resin fill/copper cap or guaranteed tenting.']}
 (OUT/'stencil-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 drawings(raw,cr)
 output_paste=args.output_dir/'ESPaperPlay_Devboard-DIY-F_Paste.gtp'
 shutil.copy2(OUT/'diy-candidate-plot/ESPaperPlay_Devboard_DIY_stencil_candidate-F_Paste.gtp',output_paste)
 result['published_candidate']={'file':pathlabel(output_paste),'sha256':sha(output_paste),'engineering_candidate':True,'steel_thickness_mm':.10,'microphone_bridge_mm':.15}
 result['dependencies']={'pcbnew_cli':P.Version(),'gerbonara':'1.6.2','shapely':'2.2.0','matplotlib':'3.11.2','python_tested':'3.15.2','installation':'external PYTHONPATH or system environment; script does not install dependencies'}
 result['sources']=source_inventory()
 write_special_holes(result,args.review_dir/'special-hole-register.csv')
 (OUT/'stencil-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 (args.review_dir/'stencil-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 shutil.copy2(OUT/'mic-stencil-before-after.png',args.review_dir/'stencil-microphone.png')
 (args.review_dir/'stencil-review.md').write_text(chinese_report(result),encoding='utf-8')
 print(json.dumps({'original_paste_objects':original['layers']['F.Paste']['objects'],'candidate_paste_objects':candidate['layers']['F.Paste']['objects'],'raw_refs':len(original['layers']['F.Paste']['by_ref']),'candidate_refs':len(candidate['layers']['F.Paste']['by_ref']),'VIP_holes':len(original['holes_intersecting_SMT_copper']),'raw_paste_holes':len(original['holes_intersecting_F_Paste']),'candidate_paste_holes':len(candidate['holes_intersecting_F_Paste']),'min_AR':candidate['stencil_apertures_sorted_by_AR'][0],'assertions':result['assertions']},indent=2))
if __name__=='__main__':main()

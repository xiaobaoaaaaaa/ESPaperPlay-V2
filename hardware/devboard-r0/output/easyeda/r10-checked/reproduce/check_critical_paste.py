#!/usr/bin/python3
"""Read-only source-to-GTP audit of critical independently defined paste openings.
Use Fedora /usr/bin/python3 (pcbnew). Only the emitted RS274X subset is parsed.
"""
import argparse,hashlib,json,math,re,zipfile
from pathlib import Path
import pcbnew
from check_gerber_rings import parse_region,flashes
TOL=2e-5
REFS=['U301','U203','U802','U101','U201','J406']
def box(points):return [min(x for x,y in points),min(y for x,y in points),max(x for x,y in points),max(y for x,y in points)]
def padbox(p):
 b=p.GetBoundingBox();return [b.GetLeft()/1e6,-b.GetBottom()/1e6,b.GetRight()/1e6,-b.GetTop()/1e6]
def matchbox(a,b):return max(abs(x-y)for x,y in zip(a,b))<TOL
p=argparse.ArgumentParser();p.add_argument('zip',type=Path);p.add_argument('--report',type=Path);p.add_argument('--board',type=Path,default=Path('/home/xiaobao/Projects/ESPaperPlay-V2/hardware/devboard-r0/ESPaperPlay_Devboard.kicad_pcb'));a=p.parse_args()
with zipfile.ZipFile(a.zip)as z:text=z.read('Gerber_TopPasteMaskLayer.GTP').decode()
assert '%MOMM*%'in text and '%FSLAX45Y45*%'in text
regions=[parse_region(s)for s in re.findall(r'G36\*(.*?)G37\*',text,re.S)]
for r in regions:r['bbox']=box(r['points'])
fl=flashes(text);board=pcbnew.LoadBoard(str(a.board));checks=[]
for ref in REFS:
 f=next(f for f in board.GetFootprints()if f.GetReference()==ref);expected=[];copper_no_paste=[];retained=[]
 for pad in f.Pads():
  cu=pad.IsOnLayer(pcbnew.F_Cu);paste=pad.IsOnLayer(pcbnew.F_Paste)
  if paste and not cu:
   sz=pad.GetSize();w,h=sz.x/1e6,sz.y/1e6;shape=pad.GetShape();assert shape in [pcbnew.PAD_SHAPE_RECT,pcbnew.PAD_SHAPE_ROUNDRECT]
   radius=pad.GetRoundRectCornerRadius()/1e6 if shape==pcbnew.PAD_SHAPE_ROUNDRECT else 0
   expected.append({'bbox_mm':padbox(pad),'area_mm2':w*h-(4-math.pi)*radius*radius,'size_mm':[w,h],'corner_radius_mm':radius})
  if cu and not paste and pad.GetAttribute()==pcbnew.PAD_ATTRIB_SMD:
   q=pad.GetPosition();copper_no_paste.append({'pin':pad.GetNumber(),'center_mm':[q.x/1e6,-q.y/1e6]})
  if ref=='J406'and cu and paste:
   q=pad.GetPosition();retained.append({'pin':pad.GetNumber(),'center_mm':[q.x/1e6,-q.y/1e6]})
 for g in f.GraphicalItems():
  if g.GetLayer()!=pcbnew.F_Paste:continue
  assert g.GetShape()==pcbnew.SHAPE_T_RECT and g.GetWidth()==0
  s,e=g.GetStart(),g.GetEnd();b=box([(s.x/1e6,-s.y/1e6),(e.x/1e6,-e.y/1e6)]);w,h=b[2]-b[0],b[3]-b[1]
  expected.append({'bbox_mm':b,'area_mm2':w*h,'size_mm':[w,h],'corner_radius_mm':0})
 window_checks=[]
 for e in expected:
  rr=[r for r in regions if matchbox(r['bbox'],e['bbox_mm'])];aa=sum(r['area']for r in rr)
  window_checks.append({'center_mm':[(e['bbox_mm'][0]+e['bbox_mm'][2])/2,(e['bbox_mm'][1]+e['bbox_mm'][3])/2],'size_mm':e['size_mm'],'corner_radius_mm':e['corner_radius_mm'],'matching_regions':len(rr),'actual_area_mm2':aa,'expected_area_mm2':e['area_mm2'],'pass':len(rr)==1 and abs(aa-e['area_mm2'])<2e-6})
 unwanted=[]
 for c in copper_no_paste:
  for ff in fl:
   if math.dist(c['center_mm'],[ff['x'],ff['y']])<TOL:unwanted.append({'pin':c['pin'],'center_mm':c['center_mm'],'aperture':ff['aperture'],'shape':ff['spec'][0],'parameters':ff['spec'][1]})
 kept=[]
 for c in retained:
  matches=[ff for ff in fl if math.dist(c['center_mm'],[ff['x'],ff['y']])<TOL];kept.append({**c,'flashes':len(matches),'pass':len(matches)==1})
 checks.append({'ref':ref,'expected_manual_windows':len(expected),'manual_windows':window_checks,'unexpected_automatic_pad_flashes':unwanted,'retained_shell_paste':kept,'pass':all(x['pass']for x in window_checks)and not unwanted and all(x['pass']for x in kept)})
report={'zip':str(a.zip),'zip_sha256':hashlib.sha256(a.zip.read_bytes()).hexdigest(),'source_board_sha256':hashlib.sha256(a.board.read_bytes()).hexdigest(),'gtp_sha256':hashlib.sha256(text.encode()).hexdigest(),'checks':checks,'pass':all(c['pass']for c in checks),'limitations':'Audits source-independent rectangular/rounded-rectangle paste windows against emitted G36 line/arc regions and duplicate D03 pad flashes at the listed no-paste copper-pad centers. Tests J406 signal-window geometry separately from its two intended shell-pad flashes. Does not prove full-board Gerber equivalence, arbitrary aperture macros, or manufacturing acceptability.'}
dest=a.report or a.zip.with_suffix('.critical-paste-audit.json');dest.write_text(json.dumps(report,indent=2));print(json.dumps({'report':str(dest),'pass':report['pass'],'checks':[{k:v for k,v in c.items()if k not in ['manual_windows']}for c in checks]},indent=2))

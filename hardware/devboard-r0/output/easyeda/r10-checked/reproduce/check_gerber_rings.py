#!/usr/bin/env python3
"""Read-only Gerber verification of U803 exact annuli and NPTH.
Supports the documented RS-274X subset emitted by EasyEDA for this board.
It does not claim whole-board manufacturing validation.
"""
import argparse,json,zipfile,re,math,hashlib
from pathlib import Path
CENTER=(61.,-62.);TOL=2e-5

def parse_region(block):
 pos=None;segments=[];points=[]
 for line in block.splitlines():
  m=re.search(r'G0([123])X(-?\d+)Y(-?\d+)(?:I(-?\d+)J(-?\d+))?D0([12])',line)
  if not m:continue
  g=int(m[1]);end=(int(m[2])/1e5,int(m[3])/1e5);action=int(m[6])
  if action==2:pos=end;points.append(end);continue
  assert pos is not None
  if g==1:segments.append({'kind':'line','start':pos,'end':end});points.append(end)
  else:
   c=(pos[0]+int(m[4])/1e5,pos[1]+int(m[5])/1e5);radius=math.dist(c,pos);a0=math.atan2(pos[1]-c[1],pos[0]-c[0]);a1=math.atan2(end[1]-c[1],end[0]-c[0]);theta=(a1-a0)%(2*math.pi)
   if g==2:theta=theta-2*math.pi if theta>1e-10 else -2*math.pi
   segments.append({'kind':'arc','start':pos,'end':end,'center':c,'radius':radius,'angle':theta})
   for i in range(1,65):
    t=a0+theta*i/64;points.append((c[0]+radius*math.cos(t),c[1]+radius*math.sin(t)))
  pos=end
 area=0
 for s in segments:
  x,y=s['start'];u,v=s['end'];area+=(x*v-u*y)/2
  if s['kind']=='arc':area+=s['radius']**2*(s['angle']-math.sin(s['angle']))/2
 return {'segments':segments,'points':points,'area':abs(area)}

def inside(p,poly):
 x,y=p;hit=False
 for a,b in zip(poly,poly[1:]+poly[:1]):
  if (a[1]>y)!=(b[1]>y)and x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:hit=not hit
 return hit

def flashes(text):
 apertures={m[1]:(m[2],m[3])for m in re.finditer(r'%ADD(\d+)([A-Za-z]+),([^*]+)\*%',text)};out=[];active=None
 for line in text.splitlines():
  m=re.search(r'G54D(\d+)\*',line)
  if m:active=m[1]
  m=re.search(r'X(-?\d+)Y(-?\d+)D03',line)
  if m:out.append({'x':int(m[1])/1e5,'y':int(m[2])/1e5,'aperture':active,'spec':apertures.get(active)})
 return out

def examine(text,ro,ri):
 regions=[parse_region(b)for b in re.findall(r'G36\*(.*?)G37\*',text,re.S)];sectors=[]
 for rr in regions:
  arcs=[s for s in rr['segments']if s['kind']=='arc']
  if not arcs or not all(math.dist(a['center'],CENTER)<TOL for a in arcs):continue
  radii=sorted(a['radius']for a in arcs)
  if len(arcs)==2 and abs(radii[0]-ri)<TOL and abs(radii[1]-ro)<TOL and all(abs(abs(a['angle'])-math.pi/2)<TOL for a in arcs):sectors.append(rr)
 fl=flashes(text);ghost=[f for f in fl if not(49<=f['x']<=211 and -161<=f['y']<=-49)]
 center_regions=[i for i,rr in enumerate(regions)if inside(CENTER,rr['points'])]
 expected=math.pi*(ro*ro-ri*ri);area=sum(s['area']for s in sectors)
 return {'sectors':len(sectors),'outer_radius_mm':ro,'inner_radius_mm':ri,'sector_area_sum_mm2':area,'expected_area_mm2':expected,'area_error_mm2':area-expected,'center_containing_regions':center_regions,'out_of_board_flashes':ghost,'pass':len(sectors)==4 and abs(area-expected)<1e-7 and not center_regions and not ghost}

def main():
 p=argparse.ArgumentParser();p.add_argument('zip',type=Path);p.add_argument('--report',type=Path);a=p.parse_args()
 with zipfile.ZipFile(a.zip)as z:
  assert z.testzip()is None
  read=lambda name:z.read(name).decode()
  cu=examine(read('Gerber_TopLayer.GTL'),.825,.525)
  pa=examine(read('Gerber_TopPasteMaskLayer.GTP'),.8025,.5475)
  np=read('Drill_NPTH_Through.DRL');tools={m[1]:float(m[2])for m in re.finditer(r'T(\d+)C([\d.]+)',np)};tool=None;holes=[]
  for l in np.splitlines():
   if re.fullmatch(r'T\d+',l):tool=l[1:]
   m=re.fullmatch(r'X(-?[\d.]+)Y(-?[\d.]+)',l)
   if m:holes.append({'center_mm':[float(m[1]),float(m[2])],'diameter_mm':tools[tool]})
  acoustic=[h for h in holes if math.dist(h['center_mm'],CENTER)<TOL];np_ok='TYPE=NON_PLATED'in np and len(holes)==7 and len(acoustic)==1 and abs(acoustic[0]['diameter_mm']-.6)<1e-9
  inner=[]
  for n in ['Gerber_InnerLayer1.G1','Gerber_InnerLayer2.G2']:
   s=read(n);declared=int(re.search(r'Copper Areas: (\d+)',s)[1]);regions=s.count('G36*');inner.append({'file':n,'declared_copper_areas':declared,'region_blocks':regions,'present':declared>0 and regions>0,'sha256':hashlib.sha256(s.encode()).hexdigest()})
 report={'zip':str(a.zip),'zip_sha256':hashlib.sha256(a.zip.read_bytes()).hexdigest(),'copper_ring':cu,'paste_ring':pa,'npth':{'holes':holes,'pass':np_ok},'inner_layers':inner,'pass':cu['pass']and pa['pass']and np_ok and all(v['present']for v in inner),'limitations':'Checks U803 annular sectors/center void/NPTH and presence of inner copper. Does not prove whole-board Gerber equality or DRC.'}
 dest=a.report or a.zip.with_suffix('.ring-audit.json');dest.write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
if __name__=='__main__':main()

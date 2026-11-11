"""Read-only r8 mechanical drilling/process inventory, no board writes."""
import pcbnew as P
import json,hashlib,math,itertools,collections,argparse
from pathlib import Path
root=Path(__file__).resolve().parents[3]
board_path=root/'hardware/devboard-r0/ESPaperPlay_Devboard.kicad_pcb'
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,default=Path(__file__).parent/'native-process-inventory.json',help='JSON output; use a temporary path for read-only comparison with the archived inventory')
args=parser.parse_args()
out=args.output.resolve()
if out.suffix.lower()!='.json' or out==board_path.resolve():
 raise ValueError('Output must be a separate JSON file, never the source PCB')
source_sha=hashlib.sha256(board_path.read_bytes()).hexdigest()
if source_sha!='1a4556d866cc1352a2c45b674c94d2f233edf28c3e003bd96c8f6caf1e630681':
 raise ValueError('Source PCB differs from the reviewed r8 baseline; review before changing this guard')
b=P.LoadBoard(str(board_path)); mm=lambda n:round(P.ToMM(n),6)
def xy(v):return [mm(v.x),mm(v.y)]
vs=[t for t in b.GetTracks() if t.GetClass()=='PCB_VIA']; ts=[t for t in b.GetTracks() if t.GetClass()!='PCB_VIA']
holes=[]
for v in vs:
 holes.append(dict(kind='via',id=v.m_Uuid.AsString(),net=v.GetNetname(),xy_mm=xy(v.GetPosition()),drill_mm=[mm(v.GetDrillValue())]*2,angle_deg=0,diameter_mm=mm(v.GetWidth(P.F_Cu))))
for fp in b.GetFootprints():
 for p in fp.Pads():
  if p.GetAttribute() not in [P.PAD_ATTRIB_PTH,P.PAD_ATTRIB_NPTH]:continue
  holes.append(dict(kind='pth' if p.GetAttribute()==P.PAD_ATTRIB_PTH else 'npth',id=p.m_Uuid.AsString(),reference=fp.GetReference(),pad=p.GetNumber(),net=p.GetNetname(),xy_mm=xy(p.GetPosition()),drill_mm=xy(p.GetDrillSize()),angle_deg=p.GetOrientation().AsDegrees(),copper_mm=xy(p.GetSize())))
def axis(h):
 dx,dy=h['drill_mm']; x,y=h['xy_mm']; a=math.radians(h['angle_deg']); r=min(dx,dy)/2
 ux=(max(dx,dy)-min(dx,dy))/2 if dx>dy else 0; uy=(max(dx,dy)-min(dx,dy))/2 if dy>dx else 0
 # Rotation sign doesn't affect axis aligned slots on this board.
 vx=ux*math.cos(a)+uy*math.sin(a); vy=-ux*math.sin(a)+uy*math.cos(a)
 return (x-vx,y-vy),(x+vx,y+vy),r
def distpt(p,a,b):
 vx=b[0]-a[0];vy=b[1]-a[1];vv=vx*vx+vy*vy
 t=max(0,min(1,((p[0]-a[0])*vx+(p[1]-a[1])*vy)/vv)) if vv else 0
 return math.hypot(p[0]-a[0]-t*vx,p[1]-a[1]-t*vy)
def edgegap(h,k):
 a,b,r=axis(h);c,d,s=axis(k)
 return min(distpt(a,c,d),distpt(b,c,d),distpt(c,a,b),distpt(d,a,b))-r-s
mins={}; low=[]
for h,k in itertools.combinations(holes,2):
 g=edgegap(h,k); key='/'.join(sorted([h['kind'],k['kind']]))
 if key not in mins or g<mins[key]['gap_mm']:mins[key]={'gap_mm':g,'a':h,'b':k}
 if g<.2-1e-6:low.append({'gap_mm':g,'a':h,'b':k})
for x in mins.values():x['gap_mm']=round(x['gap_mm'],6)
pths=[h for h in holes if h['kind']=='pth']; ordinary=[h for h in pths if h.get('reference')!='U301']
report=dict(source=str(board_path.relative_to(root)),source_sha256=hashlib.sha256(board_path.read_bytes()).hexdigest(),kicad=P.GetBuildVersion(),method='Read-only pcbnew. Nominal drilling geometry, circle/capsule axis distance; current slots are axis aligned. Does not model drilling tolerances or finished plating; DRC handles copper clearance separately.',counts=dict(tracks=len(ts),vias=len(vs),pth=len(pths),npth=sum(h['kind']=='npth' for h in holes)),track_width_counts={str(k):v for k,v in sorted(collections.Counter(mm(t.GetWidth()) for t in ts).items())},via_geometry_counts=[dict(diameter_mm=k[0],drill_mm=k[1],annular_ring_mm=round((k[0]-k[1])/2,6),count=v) for k,v in sorted(collections.Counter((mm(v.GetWidth(P.F_Cu)),mm(v.GetDrillValue())) for v in vs).items())],hole_min_gap_by_pair_type=mins,holes_below_0_2_gap=low,min_ordinary_pth_annular_mm=min(min((a-d)/2 for a,d in zip(h['copper_mm'],h['drill_mm'])) for h in ordinary),npth=[h for h in holes if h['kind']=='npth'],slots=[h for h in holes if h['drill_mm'][0]!=h['drill_mm'][1]],module_thermal_holes=[h for h in holes if h.get('reference')=='U301'])
report['source_board_sha256']=source_sha
report['review_status']='review_only_not_fabrication_release'
if hashlib.sha256(board_path.read_bytes()).hexdigest()!=source_sha:
 raise ValueError('Source PCB changed during read-only measurement')
out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:report[k] for k in ['source_sha256','counts','via_geometry_counts','min_ordinary_pth_annular_mm']},indent=2)); print('min hole gaps', {k:x['gap_mm'] for k,x in mins.items()}); print('holes below .2 gap',len(low))

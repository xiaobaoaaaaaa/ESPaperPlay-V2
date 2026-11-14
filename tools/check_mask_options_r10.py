#!/usr/bin/env python3
"""Read-only r10 mask expansion comparison; writes a separate JSON report."""
from pathlib import Path
import importlib.util,json,itertools,hashlib,collections,argparse
import pcbnew as P
from shapely.strtree import STRtree
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,default=ROOT/'build/dfm-r10/mask-options-recheck.json')
args=parser.parse_args()
report_path=args.output.resolve()
if report_path.suffix!='.json':raise ValueError('Output must be a separate JSON report')
spec=importlib.util.spec_from_file_location('stencil_geometry',ROOT/'tools/prepare_stencil_r9.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
p=ROOT/'hardware/devboard-r0/ESPaperPlay_Devboard.kicad_pcb';digest=lambda:hashlib.sha256(p.read_bytes()).hexdigest();before=digest();b=P.LoadBoard(str(p))
pads=[]
for f in b.GetFootprints():
 for pad in f.Pads():
  if pad.GetNumber() and pad.GetAttribute()==P.PAD_ATTRIB_SMD and pad.IsOnLayer(P.F_Mask):
   pads.append(dict(ref=f.GetReference(),pin=pad.GetNumber(),net=pad.GetNetname(),native=m.shape(pad,P.F_Mask),exp=P.ToMM(pad.GetSolderMaskExpansion(P.F_Mask))))
options={}
for name,extra in [('retain_existing',0),('zero_only_plus_0_025',.025),('zero_only_plus_0_050',.05)]:
 shapes=[r['native'].buffer(extra if r['exp']==0 else r['exp'],quad_segs=64) for r in pads];tree=STRtree(shapes);pairs=[]
 for i,s in enumerate(shapes):
  for j in tree.query(s.buffer(.31)):
   if i>=j:continue
   a,c=pads[i],pads[j]
   if (a['ref'],a['pin'])==(c['ref'],c['pin']) or (a['net'] and a['net']==c['net']):continue
   d=s.distance(shapes[j])
   if d<.31:pairs.append({'a':a['ref']+'.'+a['pin'],'b':c['ref']+'.'+c['pin'],'gap_mm':round(d,8)})
 mins={}
 for pair in sorted(pairs,key=lambda q:q['gap_mm']):
  r1=pair['a'].split('.')[0];r2=pair['b'].split('.')[0]
  if r1==r2 and r1 not in mins:mins[r1]=pair
 options[name]={'changed_pad_count':sum(r['exp']==0 for r in pads) if extra else 0,'global_minimum_pair':min(pairs,key=lambda q:q['gap_mm']),'minimum_within_each_footprint':mins,'pairs_below_0_10_mm':[r for r in pairs if r['gap_mm']<.09999],'pairs_below_0_13_mm':[r for r in pairs if r['gap_mm']<.12999],'different_net_near_pairs_tested':len(pairs)}
assert digest()==before
result={'date':'2026-11-14','source_board_sha256':before,'method':'Read-only native SMD pad geometry expanded by effective local mask clearance. For counterfactual options only pads with effective zero expansion change; existing nonzero local clearances retained. Full-board different-net pad pair test; geometrical result, not manufacturer-registration simulation or final plotted Gerber.','smd_mask_pad_objects':len(pads),'effective_expansion_counts_mm':dict(collections.Counter(str(r['exp']) for r in pads)),'nonzero_expansion_by_reference':{str(e):dict(collections.Counter(r['ref'] for r in pads if r['exp']==e)) for e in sorted(set(r['exp'] for r in pads)-{0})},'options':options,'recommendation':'Retain actual r10 mask settings for JLC LDI 1:1 process; do not blindly add 0.025 or 0.05 mm. Existing local offsets (including U101/U201 +0.05 and U803 +0.025, full list in nonzero_expansion_by_reference) require explicit retention in manufacturing notes. Generic ADI NSMD guidance is compatible with considering a local U203/U802 expansion, but no blanket expansion is a proven required correction; evaluate wettable sides/CAM before any change.','source_unchanged':True}
report_path.parent.mkdir(parents=True,exist_ok=True)
report_path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:{'minimum':v['global_minimum_pair'],'below_0_10':len(v['pairs_below_0_10_mm']),'below_0_13':len(v['pairs_below_0_13_mm'])} for k,v in options.items()},indent=2))

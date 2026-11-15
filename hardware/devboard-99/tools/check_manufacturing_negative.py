#!/usr/bin/env python3
"""Read original CAD; create rule-violation fixtures only in a separate scratch directory."""
from pathlib import Path
import json,hashlib,subprocess,shutil,argparse
import pcbnew as P
repo=Path(__file__).resolve().parents[3]
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--board',type=Path,required=True);ap.add_argument('--report-dir',type=Path,required=True);ap.add_argument('--work-dir',type=Path,default=repo/'build/pcb-99/validation-negative');args=ap.parse_args()
src=args.board.resolve()
out=args.report_dir.resolve();out.mkdir(exist_ok=True,parents=True)
scratch=args.work_dir.resolve();scratch.mkdir(exist_ok=True,parents=True)
if scratch==src.parent or scratch==out:raise SystemExit('Scratch directory must be separate from source and report directories')
inputs=[src,src.with_suffix('.kicad_pro'),src.with_suffix('.kicad_dru')]
hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in inputs}
b=P.LoadBoard(str(src));ids={}
for label,typ,x,diam,drill in [('undersized_through',P.VIATYPE_THROUGH,70,.45,.2),('blind',P.VIATYPE_BLIND,75,.6,.3),('micro',P.VIATYPE_MICROVIA,80,.6,.3)]:
 v=P.PCB_VIA(b);v.SetPosition(P.VECTOR2I(P.FromMM(x),P.FromMM(63)));v.SetWidth(P.FromMM(diam));v.SetDrill(P.FromMM(drill));v.SetViaType(typ);v.SetLayerPair(P.F_Cu,P.B_Cu if typ==P.VIATYPE_THROUGH else P.In1_Cu);v.SetNetCode(b.GetNetsByName()['GND'].GetNetCode());b.Add(v);ids[label]=v.m_Uuid.AsString()
p=scratch/'negative.kicad_pcb';P.SaveBoard(str(p),b)
for suffix in ['.kicad_pro','.kicad_dru']:shutil.copy2(src.with_suffix(suffix),p.with_suffix(suffix))
report=out/'native-drc.json';r=subprocess.run(['kicad-cli','pcb','drc','--format','json','--output',str(report),str(p)],capture_output=True,text=True)
(out/'native-drc.log').write_text(r.stdout+r.stderr)
j=json.loads(report.read_text());findings={}
for label,uid in ids.items():
 findings[label]=[v for v in j['violations'] if any(x.get('uuid')==uid for x in v.get('items',[]))]
checks={'undersized_through': all(any(v['type']==t for v in findings['undersized_through'])for t in ['drill_out_of_range','via_diameter']),'blind_rule_loaded':any(v['type']=='items_not_allowed' and 'Standard through vias only' in v['description']for v in findings['blind']),'micro_rule_loaded':any(v['type']=='items_not_allowed' and 'Standard through vias only' in v['description']for v in findings['micro'])}
result={'status':'PASS'if all(checks.values())else'FAIL','checks':checks,'added_via_UUIDs':ids,'findings':findings,'source_unchanged':all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in hashes.items()),'inputs':hashes,'native_exit_code':r.returncode,'scratch_directory':str(scratch),'scope':'Only disposable negative.kicad_pcb modified. The original project was read but not saved.'}
(out/'summary.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps(result,indent=2,ensure_ascii=False));raise SystemExit(0 if result['status']=='PASS' and result['source_unchanged']else 1)

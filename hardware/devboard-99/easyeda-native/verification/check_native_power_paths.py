#!/usr/bin/env python3
"""Read-only actual native24 power-path width/neck/R20 review; no live writes."""
import argparse,json
from pathlib import Path
import native_trace_path_metrics as pm

def self_test():
 from shapely.geometry import box
 pads=[{'id':'a','net':'N','layers':frozenset({1}),'g':box(-.1,-.1,.1,.1),'kind':'pad'}, {'id':'b','net':'N','layers':frozenset({1}),'g':box(4.9,-.1,5.1,.1),'kind':'pad'}]
 rule={'id':'test','native_net':'N','native_from':{'physical_pads':[{'id':'a'}]},'native_to':{'physical_pads':[{'id':'b'}]},'from':'A.1','to':'B.1','trunk_min_mm':.6,'narrow_allowance_mm':3,'review_R20_mohm':100}
 lines=[pm.segment((i,0),(i+1,0),.2,str(i),'N',1)for i in range(5)]
 row=pm.trace_path_audit(lines,pads,[],[rule],35)[0];assert abs(row['cumulative_neck_mm']-4.8)<1e-6 and row['neck_budget_pass']is False;assert abs(row['trace_R20_lower_bound_mohm']-17.24*4.8/(.2*35))<1e-7
 assert pm.trace_path_audit([lines[0],lines[-1]],pads,[],[rule],35)[0]['neck_budget_pass']is None
 shifted=[pm.segment((0,0),(2.5,0),.2,'s1','N',1),pm.segment((2.501,0),(5,0),.2,'s2','N',1)]
 assert pm.trace_path_audit(shifted,pads,[],[rule],35)[0]['status']=='TRACE_ONLY_PATH_MEASURED'
 shifted[-1]=pm.segment((2.8,0),(5,0),.2,'s2','N',1);assert pm.trace_path_audit(shifted,pads,[],[rule],35)[0]['neck_budget_pass']is None
 print(json.dumps({'self_test':'PASS','cases':['cumulative neck across primitive boundaries','R20 formula/units','missing LINE path cannot pass','real copper-edge overlap connects','real copper gap remains unmeasured']}))

def check(a):
 src,state,pads,items,lines,unparsed,evidence=pm.load_scene(a);rules=json.loads(a.rules.read_text())['path_rules']
 if len(rules)!=24:raise ValueError('Expected24 approved project review paths')
 rows=pm.trace_path_audit(lines,pads,items,rules,a.copper_um,a.width_tolerance)
 for r in rows:
  over=r.get('neck_budget_pass')is False or r.get('trace_R20_lower_bound_within_limit')is False
  r['review_classification']='GEOMETRIC_WIDTH_TARGET_DEVIATION'if over and r.get('trace_R20_lower_bound_within_limit')is True else'REQUIRES_RESISTANCE_REVIEW'if over else'TRACE_TARGET_METRICS_PASS'if r['status']=='TRACE_ONLY_PATH_MEASURED'else'UNMEASURED'
 return {'status':'ACTUAL_TRACE_BUDGET_REVIEW_NOT_AMPACITY_APPROVAL','inputs':{k:pm.digest(getattr(a,k))for k in ['source','state','archive','rules']},'method':'Actual native LINE graph, exact native SMD copper plus validated PTH/via contacts; verified overlapping copper may connect, arbitrary FILL/POURED never credited.','copper_thickness_um':a.copper_um,'width_quantization_tolerance_mm':a.width_tolerance,'counts':{'paths':len(rows),'measured':sum(r['status']=='TRACE_ONLY_PATH_MEASURED'for r in rows),'trace_R20_within_review_limit':sum(r.get('trace_R20_lower_bound_within_limit')is True for r in rows),'width_neck_goal_deviations':sum(r['review_classification']=='GEOMETRIC_WIDTH_TARGET_DEVIATION'for r in rows)},'path_rules':rows,'unparsed_pour_notes':unparsed,'limitations':['35um external copper is a reference calculation unless explicitly overridden with confirmed manufactured copper thickness.','Pad/via/contact resistance, parallel-current distribution and heating are not modeled. R20 is a trace-only lower bound; no current/temperature approval.','Width/neck limits are project targets, not manufacturer DRC minima. Accumulated below-target length never resets at split LINE boundaries.','Native DRC, net equivalence, actual CAM and loaded hardware tests remain separate checks.']}

def write_markdown(a,o):
 md=['Actual native power-path review','',f"Source `{a.source.name}` SHA256 `{o['inputs']['source']['sha256']}`.",'',f"Measured {o['counts']['measured']}/24 paths; R20 screening within review limit for {o['counts']['trace_R20_within_review_limit']}/24; {o['counts']['width_neck_goal_deviations']} project width/neck target deviations. These are trace-only metrics, not manufacturing or thermal release.",'','| Path | From → to | Min / target width mm | Exposed length mm | Below-target / allowance mm | R20 / review limit mΩ | Review |','|---|---|---:|---:|---:|---:|---|']
 for r in o['path_rules']:
  def f(k):return '—'if r.get(k)is None else f"{r[k]:.3f}"
  md.append(f"|{r['path_id']}|{r['from']} → {r['to']}|{f('selected_path_width_min_mm')} / {f('trunk_min_mm')}|{f('exposed_trace_length_mm')}|{f('cumulative_neck_mm')} / {f('neck_budget_mm')}|{f('trace_R20_lower_bound_mohm')} / {f('trace_R20_review_limit_mohm')}|{r['review_classification']}|")
 md+=['','All limits and terminal IDs are frozen in `power-path-rules.json`; actual positions and copper are read from the specified native snapshots and archive. Source corner geometry comes from the native library rather than rounded API pad rectangles.','']+o['limitations'];a.output.with_suffix('.md').write_text('\n'.join(md)+'\n')

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for k in ['source','state','archive','output']:p.add_argument('--'+k,type=Path)
 p.add_argument('--rules',type=Path,default=Path(__file__).with_name('power-path-rules.json'));p.add_argument('--copper-um',type=float,default=35);p.add_argument('--width-tolerance',type=float,default=.00025);p.add_argument('--self-test',action='store_true');a=p.parse_args()
 if a.self_test:self_test();return 0
 if not all(getattr(a,k)for k in ['source','state','archive','output']):p.error('--source/--state/--archive/--output required')
 if a.copper_um<=0 or a.width_tolerance<0:p.error('invalid copper thickness or width tolerance')
 try:o=check(a)
 except(ValueError,KeyError,TypeError,IndexError,OSError)as e:o={'status':'INPUT_OR_GEOMETRY_UNSUPPORTED','error':str(e)}
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(o,indent=2)+'\n')
 if 'path_rules'in o:write_markdown(a,o)
 print(json.dumps({'status':o['status'],'counts':o.get('counts'),'error':o.get('error'),'output':str(a.output)}))
 return 2 if 'error'in o else int(o['counts']['measured']!=24 or o['counts']['trace_R20_within_review_limit']!=24)
if __name__=='__main__':raise SystemExit(main())

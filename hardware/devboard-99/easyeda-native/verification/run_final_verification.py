#!/usr/bin/env python3
"""Run the complete read-only final native verification set against formal paths.

Writes reports/logs only. Never changes CAD, project properties, git or factory
orders. Nonzero checks remain nonzero in the overall result, including explicitly
reported project-target deviations; no report is promoted to manufacturing PASS.
"""
import argparse,collections,hashlib,importlib.metadata,json,math,subprocess,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,data):p.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
def unwrap_state(p):
 d=json.loads(p.read_text())
 if isinstance(d,dict):d=d.get('result',d)
 if isinstance(d,dict):d=d.get('components',d)
 if not isinstance(d,list):raise ValueError('Expected native component/pin state array')
 return d

def physical_check(files):
 sch=json.loads(files['schematic_netlist'].read_text());state=unwrap_state(files['state']);expected={};components=[]
 for c in sch['components'].values():
  ref=c['props']['Designator'];components.append(ref)
  for p in c['pinInfoMap'].values():expected[(ref,str(p['number']))]=p.get('net')or''
 actual=collections.defaultdict(list);ids=[]
 for c in state:
  for p in c['pins']:actual[(c['ref'],str(p['n']))].append(p.get('net')or'');ids.append(p['id'])
 errors=[]
 if set(components)!={c['ref']for c in state}:errors.append({'kind':'component_set'})
 if len(ids)!=len(set(ids)):errors.append({'kind':'duplicate_physical_pad_id'})
 for key in sorted(set(expected)|set(actual)):
  if key not in expected or key not in actual or any(n!=expected[key]for n in actual[key]):errors.append({'ref':key[0],'pin':key[1],'expected':expected.get(key),'actual':actual.get(key)})
 return {'status':'PASS_PHYSICAL_AND_LOGICAL_PIN_NETS'if not errors else'FAIL_PIN_NETS','components':len(state),'physical_pads':len(ids),'logical_pins':len(actual),'errors':errors,'inputs':{str(files[k]):sha(files[k])for k in['schematic_netlist','state']}}

def drc_check(files):
 pcb=json.loads(files['native_board_check'].read_text());sch=json.loads(files['schematic_drc'].read_text());errors=[]
 if not isinstance(pcb,dict)or not isinstance(pcb.get('drc'),list):errors.append('Unsupported native PCB DRC export; expected object.drc list')
 elif pcb['drc']:errors.append('Native PCB DRC export contains findings')
 if not isinstance(pcb,dict)or not isinstance(pcb.get('rules'),dict)or not pcb.get('rules'):errors.append('Native PCB rule readback is missing')
 if not isinstance(sch,list)or sch:errors.append('Native schematic DRC export must be an empty list')
 return {'status':'PASS_NATIVE_DRC_EXPORTS_EMPTY'if not errors else'FAIL_NATIVE_DRC_EXPORTS','errors':errors,'inputs':{str(files[k]):sha(files[k])for k in['native_board_check','schematic_drc']},'limits':['Read-only export check: a matching same-session native DRC execution and enabled/ignored-check evidence must be retained independently. An empty stale export alone does not prove DRC was rerun.']}

def classify_engineering_reviews(rows):
 """Classify explicit documented review findings; never turn a child error into
 a fabrication pass. Exact known via identity/position/distance is required.
 Other opens, unknown fields/errors, new return gaps and slots remain failures.
 """
 known=json.loads((HERE/'engineering-review-items.json').read_text())
 anchor=known['EPD_PAD_SCLK_return']
 critical_anchors=[anchor,known['TOUCH_IO_EN_static_return']]
 def matches_return(r,item):
  if not isinstance(r,dict):return False
  try:
   return (r.get('id')==item['signal_access_id'] and r.get('net')==item['net'] and
           r.get('GND_vertical_access')==item['ground_access_id'] and
           math.dist(r.get('xy_mm',[1e6,1e6]),item['xy_mm'])<=item['identity_tolerance_mm'] and
           abs(r.get('distance_center_mm',1e6)-item['measured_distance_mm'])<=item['identity_tolerance_mm'])
  except (ValueError,TypeError,OverflowError):return False
 hard=[];reviews=[]
 for row in rows:
  name=row['name'];report={}
  if row.get('report_written_this_run') and row.get('report'):
   try:report=json.loads(Path(row['report']).read_text())
   except Exception:pass
  only_review=False
  if name=='critical-routes' and report.get('status')in['PASS','FAIL']:
   no_physical_error=(report.get('full_native_schematic_pin_check',{}).get('pass')is True and
      report.get('SD_equivalent_channel_mapping',{}).get('pass')is True and
      all(key in report and not report[key]for key in['open_or_isolated_copper_nets','missing_required_nets','physical_shorts']) and
      bool(report.get('connectivity')) and all(c.get('pass')is True for c in report['connectivity'].values()))
   rr=report.get('return_over_2mm',[])
   recognized=[(r,item)for r in rr for item in critical_anchors if matches_return(r,item)]
   only_review=(no_physical_error and not report.get('errors') and not report.get('error') and
      row['returncode']==1 and bool(rr) and len(recognized)==len(rr) and
      len({r['id']for r,item in recognized})==len(rr))
   if only_review:
    for finding,item in recognized:reviews.append({'job':name,'kind':'DOCUMENTED_RETURN_DISTANCE_PREFERENCE',
      'finding':finding,'interpretation':item['interpretation']})
  elif name=='reference-planes' and report.get('status')=='GEOMETRIC_REFERENCE_REVIEW_REQUIRED':
   physical=report.get('physical_review_events',[]);numerical=report.get('numerical_scale_review_events',[])
   physical_known=bool(physical) and all(r.get('classification')=='TERMINAL_EXIT_WITHOUT_LOCAL_VERIFIED_RETURN_REVIEW' and
     r.get('net')==anchor['net'] and r.get('own_net_plated_access_in_void')==[anchor['signal_access_id']] and
     len(r.get('local_GND_return_access',[]))==1 and
     r['local_GND_return_access'][0].get('signal_access')==anchor['signal_access_id'] and
     r['local_GND_return_access'][0].get('ground_access')==anchor['ground_access_id'] and
     r['local_GND_return_access'][0].get('ground_access_verified_on_both_inner_planes')is True and
     abs(r['local_GND_return_access'][0].get('distance_center_mm',1e6)-anchor['measured_distance_mm'])<=anchor['identity_tolerance_mm']
     for r in physical)
   numeric_known=all(r.get('classification')=='CAM_QUANTIZATION_SCALE_REFERENCE_GAP_REVIEW' and
     0<=r.get('unreferenced_centerline_length_mm',1e6)<=known['numerical_residue_reporting_bound_mm']for r in numerical)
   only_review=(all(key in report and not report[key]for key in['errors','selected_nets_without_any_routed_LINE','selected_nets_absent_from_native']) and
      len(report.get('review_events',[]))==len(physical)+len(numerical) and numeric_known and
      (physical_known or not physical) and bool(physical or numerical) and
      bool(report.get('actual_reference_corridor_checks')) and all(c.get('pass')is True for c in report['actual_reference_corridor_checks']))
   if only_review:reviews.append({'job':name,'kind':'REPORTED_REFERENCE_PREFERENCE_AND_NUMERICAL_RESIDUES',
       'physical_findings':physical,'numerical_findings':numerical,'interpretation':'Original actual-CAM measurements and nonzero checker exit retained. This classification is not a claim that reference copper covers these intervals.'})
  if name=='power-paths' and report.get('path_rules'):
   deviations=[r for r in report['path_rules']if r.get('review_classification')=='GEOMETRIC_WIDTH_TARGET_DEVIATION']
   if deviations:reviews.append({'job':name,'kind':'PROJECT_POWER_WIDTH_NECK_TARGETS',
     'findings':[{k:r.get(k)for k in['path_id','net','selected_path_width_min_mm','trunk_min_mm','cumulative_neck_mm','neck_budget_mm','trace_R20_lower_bound_mohm','trace_R20_review_limit_mohm']}for r in deviations],
     'interpretation':'Project width/neck targets, not manufacturing spacing limits. Trace-only R20 does not establish ampacity or temperature.'})
  if name=='i2s-paths' and report.get('exposed_trace_skew_screening_mm'):
   deviations={k:v for k,v in report['exposed_trace_skew_screening_mm'].items()if v>report['skew_reference_mm']}
   if deviations:reviews.append({'job':name,'kind':'I2S_PROJECT_LENGTH_REFERENCE','actual_mm':deviations,
     'reference_mm':report['skew_reference_mm'],'interpretation':'Geometric length reference, not fabricated timing or SI qualification.'})
  if row['returncode'] and not only_review:hard.append({'job':name,'returncode':row['returncode'],'reported_status':row.get('reported_status'),'report':row.get('report'),'log':row.get('log')})
 return {'unresolved_check_failures':hard,'engineering_review_items':reviews,'classification_policy':{'path':str(HERE/'engineering-review-items.json'),'sha256':sha(HERE/'engineering-review-items.json')},
         'interpretation':'No child return code, original threshold or report is changed. Known engineering preferences are separated from physical/netlist/CAM failures; any unknown failure remains unresolved.'}

def build_plan(native,out,negative):
 audit=native/'audit';routing=audit/'pcb-routing';files={
 'source':native/'source/PCB-layout.epcb','state':routing/'final-routed-state.json','archive':native/'ESPaperPlay-99-Native-WIP.epro2','cam':routing/'NOT-FOR-MANUFACTURE-routed-cam.zip',
 'schematic_netlist':audit/'native-schematic.enet','pcb_netlist':routing/'native-pcb.enet','pin_map':audit/'native-pin-map.json','reference':audit/'reference-components.json','aliases':audit/'native-net-aliases.json','before_netlist':audit/'pcb-layout/native-pcb.enet',
 'native_board_check':routing/'native-board-check.json','schematic_drc':audit/'native-schematic-drc.json','page_uuids':audit/'page-uuids.json'}
 jobs=[];py=sys.executable
 def job(name,script,args,requires,report=None):jobs.append({'name':name,'argv':[py,str(script),*map(str,args)],'requires':requires,'report':str(out/report)if report else None})
 def builtin(name,fn,requires,report):jobs.append({'name':name,'builtin':fn,'requires':requires,'report':str(out/report)})
 base=['--source',files['source'],'--state',files['state'],'--archive',files['archive']];cam=[*base,'--zip',files['cam']]
 builtin('native-drc-exports','drc_check',['native_board_check','schematic_drc'],'native-drc-export-check.json')
 for name,key in [('schematic-logical-pins','schematic_netlist'),('pcb-logical-pins','pcb_netlist')]:job(name,ROOT/'tools/check_easyeda_native99.py',[files[key],files['pin_map'],files['reference'],'--aliases',files['aliases'],'--output',out/(name+'.json')],[key,'pin_map','reference','aliases'],name+'.json')
 builtin('physical-pad-nets','physical_check',['schematic_netlist','state'],'physical-pad-net-check.json')
 job('schematic-archive',ROOT/'tools/check_easyeda_native_archive.py',[native,'--output',out/'schematic-archive-coherence.json'],['archive','page_uuids'],'schematic-archive-coherence.json')
 job('pcb-footprint-archive',ROOT/'tools/check_easyeda_native_pcb_archive.py',[native,'--archive',files['archive'],'--output',out/'pcb-archive-coherence.json'],['archive','source'],'pcb-archive-coherence.json')
 for name,script in [('cam-self-test','check_native_cam_connectivity.py'),('power-self-test','check_native_power_paths.py')]:job(name,HERE/script,['--self-test'],[])
 job('reference-self-test',HERE/'check_native_reference_planes.py',['--self-test','--output',out/'reference-plane-self-test.json'],[],'reference-plane-self-test.json')
 job('signal-length-self-test',HERE/'check_native_signal_lengths.py',['--self-test','--output',out/'signal-length-self-test.json'],[],'signal-length-self-test.json')
 job('review-classifier-self-test',HERE/'test_native_review_classification.py',[],[])
 for name,script,args,required,report in[
 ('boundaries','check_native_routing_boundaries.py',base,['source','state','archive'],'boundaries.json'),
 ('special-cam','check_native_routed_special_cam.py',cam,['source','state','archive','cam'],'special-cam.json'),
 ('smd-paste','check_native_smd_paste.py',['--source',files['source'],'--state',files['state'],'--zip',files['cam']],['source','state','cam'],'smd-paste.json'),
 ('j501-cam','check_native_j501_cam.py',cam+(['--negative-tests']if negative else[]),['source','state','archive','cam'],'j501-cam-review.json'),
 ('cam-connectivity','check_native_cam_connectivity.py',cam,['source','state','archive','cam'],'cam-connectivity.json'),
 ('critical-routes','check_native_critical_routes.py',base+['--netlist',files['schematic_netlist'],'--before-netlist',files['before_netlist']],['source','state','archive','schematic_netlist','before_netlist'],'critical-routes.json'),
 ('reference-planes','check_native_reference_planes.py',cam+['--svg',out/'reference-planes.svg'],['source','state','archive','cam'],'reference-planes.json'),
 ('power-paths','check_native_power_paths.py',base,['source','state','archive'],'power-paths.json'),
 ('i2s-paths','check_native_i2s_paths.py',base,['source','state','archive'],'i2s-paths.json'),
 ('signal-lengths','check_native_signal_lengths.py',base,['source','state','archive'],'signal-lengths.json')]:
  flag='--report'if name in['special-cam','smd-paste']else'--output';job(name,HERE/script,[*args,flag,out/report],required,report)
 return files,jobs

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--native-dir',type=Path,default=HERE.parent);p.add_argument('--output-dir',type=Path);p.add_argument('--only',help='Comma-separated job names for focused reruns; absence runs all checks');p.add_argument('--plan-only',action='store_true');p.add_argument('--skip-j501-negative-tests',action='store_true',help='Skip only the repeated in-memory mutation suite, retaining all real CAM checks');a=p.parse_args()
 native=a.native_dir.resolve();out=(a.output_dir or native/'audit/pcb-routing/verification-run').resolve();files,jobs=build_plan(native,out,not a.skip_j501_negative_tests)
 names={j['name']for j in jobs}
 if a.only:
  selected=set(a.only.split(','))
  if selected-names:p.error('Unknown job names: '+','.join(sorted(selected-names)))
  jobs=[j for j in jobs if j['name']in selected]
 required={k for j in jobs for k in j['requires']};missing=[{'input':k,'path':str(files[k])}for k in sorted(required)if not files[k].is_file()]
 versions={}
 for package in['shapely','gerbonara']:
  try:versions[package]=importlib.metadata.version(package)
  except importlib.metadata.PackageNotFoundError:versions[package]=None
 if a.plan_only:
  print(json.dumps({'status':'PLAN_ONLY_NO_CHECKS_RUN','native_dir':str(native),'output_dir':str(out),'dependencies':versions,'missing_required_inputs':missing,'jobs':jobs},indent=2));return 0
 out.mkdir(parents=True,exist_ok=True);logs=out/'logs';logs.mkdir(exist_ok=True)
 if missing or any(v is None for v in versions.values())or int(versions.get('shapely','0').split('.')[0])<2:
  summary={'status':'PRECHECK_FAILED_NO_VALIDATION_RUN','missing_required_inputs':missing,'dependencies':versions};dump(out/'verification-summary.json',summary);print(json.dumps(summary));return 2
 # All source/footprint/page snapshots and formal helper/rule files are watched;
 # report writes cannot silently change any source evidence during the run.
 watch={files[k]for k in required}|{p for p in HERE.iterdir()if p.suffix in['.py','.json']}|{Path(j['argv'][1])for j in jobs if'argv'in j}
 if any(j['name']in['schematic-archive','pcb-footprint-archive']for j in jobs):watch|={p for p in(native/'source').rglob('*')if p.is_file()}
 before={str(f):sha(f)for f in sorted(watch)if f.is_file()};rows=[];changed=[]
 for n,j in enumerate(jobs,1):
  print(f'[{n}/{len(jobs)}] START {j["name"]}',flush=True);started=time.time();ns=time.time_ns();log=logs/(j['name']+'.log');report=Path(j['report'])if j['report']else None
  try:
   if 'builtin'in j:
    result=globals()[j['builtin']](files);dump(report,result);code=int(bool(result['errors']));log.write_text(json.dumps(result,indent=2)+'\n')
   else:
    with log.open('w')as stream:
     stream.write(json.dumps(j['argv'])+'\n');stream.flush();code=subprocess.run(j['argv'],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,check=False).returncode
   current_report=bool(report and report.exists()and report.stat().st_mtime_ns>=ns)
   if report and not current_report:code=code or 2
   status=None
   if current_report:
    try:status=json.loads(report.read_text()).get('status')
    except Exception:code=code or 2;status='INVALID_JSON_REPORT'
   rows.append({'name':j['name'],'returncode':code,'elapsed_seconds':round(time.time()-started,3),'log':str(log),'report':str(report)if report else None,'report_written_this_run':current_report,'reported_status':status})
  except Exception as e:
   rows.append({'name':j['name'],'returncode':2,'error':str(e),'log':str(log)});code=2
  print(f'[{n}/{len(jobs)}] END {j["name"]} exit={code} elapsed={time.time()-started:.1f}s',flush=True)
  changed=[name for name,digest in before.items()if not Path(name).exists()or sha(name)!=digest]
  if changed:break
 classification=classify_engineering_reviews(rows)
 status=('INPUT_CHANGED_ABORTED'if changed else'UNRESOLVED_CHECK_FAILURES'if classification['unresolved_check_failures']else
   ('SELECTED_CHECKS_WITH_RECORDED_ENGINEERING_REVIEWS'if a.only else'COMPLETE_GEOMETRY_CHECKS_WITH_RECORDED_ENGINEERING_REVIEWS')if classification['engineering_review_items']else'ALL_SELECTED_COMMANDS_SUCCEEDED_NOT_MANUFACTURING_RELEASE')
 summary={'status':status,'scope':'complete_set'if not a.only else'explicit_selected_subset','native_directory':str(native),'output_directory':str(out),'dependencies':versions,'python':sys.version,'input_and_checker_hashes':before,'changed_inputs':changed,'jobs':rows,'classification':classification,'all_checks_requested':[j['name']for j in jobs], 'limits':['No live DRC executed by this runner; same-session native exports and enabled/ignored-rule evidence remain required.','Nonzero geometry/project-target reviews are retained, not converted into fabricated board approval. Inspect every report, especially numerical residuals and documented project-target deviations.','No schematic/PCB/library source, project property, git state or factory order is changed. Final visual CAM review, assembly/manufacturing conditions and hardware tests remain separate.']}
 dump(out/'verification-summary.json',summary);print(summary['status'],flush=True);return int(bool(changed or any(r['returncode']for r in rows)))
if __name__=='__main__':raise SystemExit(main())

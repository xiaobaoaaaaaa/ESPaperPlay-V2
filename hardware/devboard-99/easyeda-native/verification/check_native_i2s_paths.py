"""Audit all I2S native terminals and six source-plan signal chains; no live calls."""
import argparse,json,math,collections
from pathlib import Path
from types import SimpleNamespace
import native_trace_path_metrics as pw
ng=pw.geo
digest=pw.digest
p=argparse.ArgumentParser(description=__doc__)
for k in ['source','state','archive','output']:p.add_argument('--'+k,type=Path,required=True)
p.add_argument('--rules',type=Path,default=Path(__file__).with_name('i2s-path-rules.json'));a=p.parse_args()
source,state,pads,items,loaded_lines,unparsed,evidence=pw.load_scene(a)
s=SimpleNamespace(src=source,state=state,pads=pads,items=items,args=SimpleNamespace(source=a.source,state=a.state,archive=a.archive,rules=a.rules))
plan=json.loads(a.rules.read_text())
nets=set(plan['nets'])
lines=[pw.segment((b['startX']*ng.MM,b['startY']*ng.MM),(b['endX']*ng.MM,b['endY']*ng.MM),b['width']*ng.MM,i,b['netName'],b['layerId'])for(k,i),b in s.src.items()if k=='LINE'and b.get('layerId')in ng.COPPER]
padbyref={p['ref']+'.'+str(p['pin']):p for p in s.pads};rules=[];counts={}
def rule(id,net,fr,to):
 return {'id':id,'native_net':net,'native_from':{'physical_pads':[{'id':padbyref[fr]['id']}]},'native_to':{'physical_pads':[{'id':padbyref[to]['id']}]},'from':fr,'to':to,'trunk_min_mm':.15,'narrow_allowance_mm':1000,'review_R20_mohm':10000}
for net in sorted(nets):
 pads=[p for p in s.pads if p['net']==net];counts[net]=[p['ref']+'.'+str(p['pin'])for p in pads]
 for q in pads[1:]:rules.append(rule(net+':'+q['id'],net,counts[net][0],q['ref']+'.'+str(q['pin'])))
chains=plan['signal_chains']
for c in chains:
 for n,leg in enumerate(c['legs']):rules.append(rule(c['name']+':'+str(n),leg['net'],leg['from'],leg['to']))
rows=pw.trace_path_audit(lines,s.pads,s.items,rules,35);missing=[r for r in rows if r['status']!='TRACE_ONLY_PATH_MEASURED'];byid={r['path_id']:r for r in rows};summary=[]
for c in chains:
 legs=[byid[c['name']+':'+str(i)]for i in range(len(c['legs']))];summary.append({'name':c['name'],'exposed_trace_length_mm':sum(r.get('exposed_trace_length_mm',0)for r in legs),'signal_vias_used':sorted({v for r in legs for v in r.get('via_ids',[])}),'legs':[{k:r[k]for k in ['net','from','to','status','exposed_trace_length_mm','via_ids','selected_path_source_ids','selected_path_width_min_mm','selected_path_width_max_mm']if k in r}for r in legs]})
# Actual pad-to-pad source resistor distance is bounded by original polyline length;
# graph exposed length excludes finite pad copper and package spans.
headers=[]
for net,mcu,hdr,receiver in [('I2S_BCLK','U301.20','J303.4','U801.2'),('I2S_WS','U301.7','J303.5','U801.5'),('MIC_DATA','U301.19','J303.6','U804.4'),('SPEAKER_DATA','U301.37','J303.7','U801.9')]:
 pid=padbyref[hdr]['id'];pt=padbyref[hdr]['g'].centroid;ends=[]
 for (k,i),b in s.src.items():
  if k!='LINE'or b.get('netName')!=net:continue
  for f in ['start','end']:
   q=(b[f+'X']*ng.MM,b[f+'Y']*ng.MM)
   if pt.distance(ng.Point(q))<.004:ends.append({'id':i,'end':f,'layer':b['layerId']})
 # Independently remove the header node and copper inside its envelope.
 # If MCU still reaches audio, merely having two endpoints at a header does
 # not prove that it is on the main path; never hard-code a zero stub then.
 netlines=[t for t in lines if t['net']==net];cut=padbyref[hdr]['g'].buffer(max(t['width']for t in netlines)/2+.01);trimmed=[]
 for t in netlines:
  result=t['center'].difference(cut);parts=list(result.geoms)if hasattr(result,'geoms')else[result]
  for j,part in enumerate(parts):
   if part.geom_type=='LineString'and part.length>1e-8:trimmed.append(pw.segment(part.coords[0],part.coords[-1],t['width'],t['id']+':header-cut:'+str(j),net,t['layer']))
 noheaderpads=[p for p in s.pads if p['id']!=pid];noheadervias=[i for i in s.items if i['kind']!='via'or not i['g'].intersects(cut)]
 bypass=pw.trace_path_audit(trimmed,noheaderpads,noheadervias,[rule('header-main:'+net,net,mcu,receiver)],35)[0]
 through=len(ends)==2 and bypass['status']=='NO_COMPLETE_LINE_CENTERLINE_PATH'
 headers.append({'net':net,'header':hdr,'center_incident_lines':ends,'through_header_proven':through,'without_header_path_status':bypass['status'],'topology':'MCU-to-audio trunk through header pad'if through else'REQUIRES_HEADER_BRANCH_REVIEW','dedicated_debug_leaf_length_mm':0.0 if through else None,'evidence':'Exactly2 actual center-incident LINE ends; removing header pad and intersecting local trace copper breaks MCU-to-audio path.'})
signals=[i for i in s.items if i['kind']=='via'and i['net']in nets];grounds=[i for i in s.items if i['net']=='GND'and(i['kind']=='via'or(i['kind']=='pad'and i['layers']==ng.ALL))];returns=[]
for v in signals:
 pt=v['g'].centroid;g=min(grounds,key=lambda q:pt.distance(q['g'].centroid));dist=pt.distance(g['g'].centroid);returns.append({'signal_via':v['id'],'net':v['net'],'xy_mm':[pt.x,pt.y],'return':g['id'],'return_kind':g['kind'],'distance_center_mm':dist,'le_1mm':dist<=1.00001,'le_2mm':dist<=2.00001})
returns.sort(key=lambda r:-r['distance_center_mm']);tot={r['name']:r['exposed_trace_length_mm']for r in summary};skews={'mic_clock_vs_ws_mm':abs(tot['AUDIO_BCLK_MIC']-tot['AUDIO_WS_MIC']),'amp_max_clock_ws_data_mm':max(tot[k]for k in ['AUDIO_BCLK_AMP','AUDIO_WS_AMP','SPEAKER_DATA'])-min(tot[k]for k in ['AUDIO_BCLK_AMP','AUDIO_WS_AMP','SPEAKER_DATA'])}
# Suppress irrelevant current/thermal fields from the reused geometry-path solver.
cleanrows=[{k:v for k,v in r.items()if k in ['path_id','net','from','to','status','exposed_trace_length_mm','selected_path_source_ids','via_ids','selected_path_width_min_mm','selected_path_width_max_mm']}for r in rows]
o={'status':'ACTUAL_ALL_I2S_TERMINALS_CONNECTED'if not missing else'ACTUAL_MISSING_PATHS','inputs':{k:digest(v)for k,v in vars(s.args).items()},'native_terminal_inventory':counts,'terminal_count':sum(map(len,counts.values())),'all_terminal_check_count':sum(len(v)-1 for v in counts.values()),'missing':missing,'path_checks':cleanrows,'signal_chains':summary,'debug_headers':headers,'debug_header_main_path_check_pass':all(h['through_header_proven']for h in headers),'exposed_trace_skew_screening_mm':skews,'skew_reference_mm':plan['geometric_skew_reference_mm'],'return_interconnects':returns,'return_over_1mm':[r for r in returns if not r['le_1mm']],'return_over_2mm':[r for r in returns if not r['le_2mm']],'limitations':['Exposed trace lengths omit inside-pad distance, component internal paths and vertical barrel length; do not treat these numbers as complete propagation delays.','MCU matrix, U801/U804 propagation and load/duty effects are not modeled or bench-qualified. Full timing must be checked at receiving pins at initial48kHz/32-bit stereo3.072MHz BCLK.','GND via/PTH proximity is read from actual copper source. Actual contact to both inner GND planes must also pass repour/DRC and CAM.','Native engine DRC and final CAM remain authoritative separate checks; unparsed POURED cache is not credited by this source geometry audit.']};o['source_to_series_actual_centerline_mm']={net:sum(math.hypot(b['endX']-b['startX'],b['endY']-b['startY'])*ng.MM for(k,i),b in source.items()if k=='LINE'and b.get('netName')==net)for net in ['AUDIO_BCLK_BUF','AUDIO_WS_BUF','AUDIO_DIN_BUF']};a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(o,indent=2)+'\n');print({'status':o['status'],'terminal_count':o['terminal_count'],'missing':len(missing),'chains':[(r['name'],round(r['exposed_trace_length_mm'],3),len(r['signal_vias_used']))for r in summary],'skews':skews,'signal_vias':len(signals),'return_over1':len(o['return_over_1mm']),'return_over2':len(o['return_over_2mm'])})

raise SystemExit(int(bool(missing)or bool(o['return_over_2mm'])or not o['debug_header_main_path_check_pass']))

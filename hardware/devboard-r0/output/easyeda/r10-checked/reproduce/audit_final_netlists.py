#!/usr/bin/env python3
"""Audit final live PCB/SCH netlists, assembly metadata, and allowed mechanical pins.
Read-only; no EDA calls. Fails loudly on unexpected electrical differences.
"""
import argparse,collections,hashlib,json,xml.etree.ElementTree as ET
from pathlib import Path
DNP={'J301','J302','J303','C501','C502','R108'}
HOLES={'H1','H2','H3','H4'}
def load_net(p):
 d=json.loads(p.read_text());return json.loads(d['result']['text']) if 'result'in d else d

def source_rows(text):
 states={}
 for line in text.splitlines():
  if not line.strip()or '||'not in line:continue
  hh,vv=line.split('||',1);h=json.loads(hh)
  vv=vv[:-1]if vv.endswith('|')else vv
  try:v=json.loads(vv)
  except json.JSONDecodeError:
   if not vv:v=''
   else:raise
  key=(h['type'],h.get('id'));prior=states.get(key)
  if prior is None or h.get('ticket',0)>=prior[0].get('ticket',0):states[key]=(h,v)
 return [(h,v)for h,v in states.values()if v!='']

def partitions(pinmap):
 groups=collections.defaultdict(set)
 for pin,net in pinmap.items():groups[net if net else ('NC',)+pin].add(pin)
 return {frozenset(v)for v in groups.values()}

def main():
 ap=argparse.ArgumentParser();ap.add_argument('pcb',type=Path);ap.add_argument('schematic',type=Path);ap.add_argument('--source-xml',type=Path,required=True);ap.add_argument('--footprints',type=Path,required=True);ap.add_argument('--pcb-source',type=Path);ap.add_argument('--metadata-synced',action='store_true',help='Require PCB Name=SCH Name and H1-H4 excluded from logical PCB export but physically preserved');ap.add_argument('--baseline-pcb-source',type=Path,help='Required with --metadata-synced: pre-metadata-sync PCB source, for hole geometry/identity preservation');ap.add_argument('--report',type=Path,required=True);a=ap.parse_args()
 if a.metadata_synced and not(a.pcb_source and a.baseline_pcb_source):ap.error('--metadata-synced requires --pcb-source and --baseline-pcb-source')
 pcb=load_net(a.pcb);sch=load_net(a.schematic)
 def index(d):
  out={}
  for uid,c in d['components'].items():
   ref=c['props']['Designator'];assert ref not in out,('Duplicate ref',ref);out[ref]=(uid,c)
  return out
 pr=index(pcb);sr=index(sch);source=ET.parse(a.source_xml);krefs={c.attrib['ref']:c.findtext('value')for c in source.findall('components/comp')};kp={(node.attrib['ref'],node.attrib['pin']):net.attrib['name']for net in source.findall('nets/net')for node in net}
 fps={x['uuid']:x['source']for x in json.loads(a.footprints.read_text())['result']}
 problems=[];properties=[];extra_pins=[];pin_mismatches=[];values=[];assembly=[];identities=[];names=[];sp={};pp={};npth_evidence=[]
 if set(sr)!=set(krefs):problems.append({'schematic_component_set_diff':{'missing':sorted(set(krefs)-set(sr)),'extra':sorted(set(sr)-set(krefs))}})
 if set(sr)-set(pr):problems.append({'pcb_missing_components':sorted(set(sr)-set(pr))})
 expected_extra=set()if a.metadata_synced else HOLES
 if set(pr)-set(sr)!=expected_extra:problems.append({'unexpected_pcb_only':sorted(set(pr)-set(sr)),'expected':sorted(expected_extra)})
 def blank_hole_evidence(ref,c):
  fp=c['props']['Footprint'];allpads=[(h,v)for h,v in source_rows(fps[fp])if h['type']=='PAD'];blanks=[(h,v)for h,v in allpads if str(v.get('num',''))==''];valid=bool(blanks)and all(v.get('plated')is False and (v.get('hole')or{}).get('width',0)>0 and not v.get('netName')for h,v in blanks)
  ev={'ref':ref,'footprint_uuid':fp,'blank_pad_count':len(blanks),'all_blank_pads_are_unplated_holes':valid,'pads':[{'id':h['id'],'num':v.get('num'),'plated':v.get('plated'),'hole':v.get('hole'),'net':v.get('netName')}for h,v in blanks]};npth_evidence.append(ev)
  if not valid:problems.append({'unproved_mechanical_exception':ref})
  return ev
 for ref,(su,sc)in sr.items():
  if ref not in pr:continue
  pu,pc=pr[ref];s=sc['props'];p=pc['props']
  identities.append({'ref':ref,'key_uid_equal':su==pu,'Unique ID':p.get('Unique ID')==s.get('Unique ID'),'Device':p.get('Device')==s.get('Device'),'Footprint':p.get('Footprint')==s.get('Footprint')})
  if not all(identities[-1][k]for k in ['key_uid_equal','Unique ID','Device','Footprint']):problems.append({'identity_mismatch':identities[-1]})
  val={'ref':ref,'kicad':krefs.get(ref),'schematic':s.get('Value'),'pcb':p.get('Value'),'all_match':krefs.get(ref)==s.get('Value')==p.get('Value')};values.append(val)
  if not val['all_match']:problems.append({'Value_mismatch':val})
  expected_bom='no'if ref in DNP else'yes';ass={'ref':ref,'expected_BOM':expected_bom,'pcb_BOM':p.get('Add into BOM'),'sch_BOM':s.get('Add into BOM'),'pcb_DNP':p.get('DNP','no'),'sch_DNP':s.get('DNP','no'),'pcb_to_PCB':p.get('Convert to PCB'),'sch_to_PCB':s.get('Convert to PCB')};assembly.append(ass)
  if p.get('Add into BOM')!=expected_bom or s.get('Add into BOM')!=expected_bom or (p.get('DNP','no')=='yes')!=(ref in DNP)or(s.get('DNP','no')=='yes')!=(ref in DNP)or p.get('Convert to PCB')!='yes'or s.get('Convert to PCB')!='yes':problems.append({'assembly_mismatch':ass})
  for key in ['Group ID','Channel ID','Reuse Block']:
   if p.get(key)!=s.get(key):problems.append({'hierarchy_metadata':{'ref':ref,'key':key,'pcb':p.get(key),'schematic':s.get(key)}})
  name={'ref':ref,'pcb':p.get('Name'),'schematic':s.get('Name'),'pcb_name_equals_value':p.get('Name')==s.get('Value'),'pcb_name_equals_schematic':p.get('Name')==s.get('Name')};names.append(name)
  if not name['pcb_name_equals_schematic'if a.metadata_synced else'pcb_name_equals_value']:problems.append({'unexpected_display_name':name})
  for key in sorted(set(p)|set(s)):
   if p.get(key)!=s.get(key):properties.append({'ref':ref,'property':key,'pcb':p.get(key),'schematic':s.get(key)})
  for num,pin in sc['pinInfoMap'].items():sp[(ref,num)]=pin.get('net','')
  for num,pin in pc['pinInfoMap'].items():
   if num not in sc['pinInfoMap']:
    ev={'ref':ref,'number':num,'net':pin.get('net','')};extra_pins.append(ev)
    if ref not in {'U803','J501'}or num!=''or pin.get('net',''):problems.append({'extra_electrical_pin':ev})
    else:blank_hole_evidence(ref,pc)
   else:pp[(ref,num)]=pin.get('net','')
  for num,pin in sc['pinInfoMap'].items():
   if num not in pc['pinInfoMap']or pin.get('net','')!=pc['pinInfoMap'][num].get('net',''):pin_mismatches.append({'ref':ref,'pin':num,'schematic':pin.get('net',''),'pcb':pc['pinInfoMap'].get(num,{}).get('net','MISSING')})
 for ref in sorted(set(pr)-set(sr)):
  uid,c=pr[ref];p=c['props'];blank_hole_evidence(ref,c)
  if p.get('Add into BOM')!='no'or any(num!=''or pin.get('net','')for num,pin in c['pinInfoMap'].items()):problems.append({'mechanical_component_unexpected':ref,'props':p,'pins':c['pinInfoMap']})
 if pin_mismatches:problems.append({'pin_name_mismatch_count':len(pin_mismatches)})
 kpart=partitions(kp);spart=partitions(sp);ppart=partitions(pp)
 if spart!=kpart:problems.append({'schematic_vs_kicad_partition_mismatch':True})
 if ppart!=spart:problems.append({'pcb_vs_schematic_partition_mismatch':True})
 if set(pp)!=set(sp)or set(sp)!=set(kp):problems.append({'pin_set_mismatch':True})
 physical_pins=[];physical_components=[];physical_holes=[];source_geometry_audit={}
 if a.pcb_source:
  rows=source_rows(a.pcb_source.read_text());attrs=collections.defaultdict(dict)
  for h,v in rows:
   if h['type']=='ATTR':attrs[v['parentId']][v['key']]=v['value']
  physical_components=[(h,v)for h,v in rows if h['type']=='COMPONENT']
  if a.metadata_synced:
   baseline=source_rows(a.baseline_pcb_source.read_text());baseline_attrs=collections.defaultdict(dict);baseline_components={h['id']:(h,v)for h,v in baseline if h['type']=='COMPONENT'}
   base_map={(h['type'],h.get('id')):v for h,v in baseline};live_map={(h['type'],h.get('id')):v for h,v in rows};geometric_changes=[];excluded_changes=collections.Counter()
   for key in set(base_map)|set(live_map):
    bv=base_map.get(key);lv=live_map.get(key)
    if key[0]=='COMPONENT':
     bv={k:x for k,x in(bv or{}).items()if k!='attrs'};lv={k:x for k,x in(lv or{}).items()if k!='attrs'}
    if bv==lv:continue
    if key[0]in{'ATTR','DOCHEAD','POURED'}:excluded_changes[key[0]]+=1
    else:geometric_changes.append({'type':key[0],'id':key[1]})
   source_geometry_audit={'all_nonmetadata_source_data_unchanged':not geometric_changes,'unexpected_changes':geometric_changes,'explicit_exclusions':{'ATTR':'metadata synchronized; Name/Value validated separately','DOCHEAD':'save state/version metadata','POURED':'derived copper-fill caches rebuilt after source import'},'changed_excluded_records':dict(excluded_changes),'baseline_type_counts':dict(collections.Counter(h['type']for h,v in baseline)),'final_type_counts':dict(collections.Counter(h['type']for h,v in rows))}
   if geometric_changes:problems.append({'source_geometry_or_rules_changed':geometric_changes})
   for h,v in baseline:
    if h['type']=='ATTR':baseline_attrs[v['parentId']][v['key']]=v['value']
   physical_ref_map={attrs[h['id']].get('Designator'):(h,v)for h,v in physical_components}
   if len(physical_components)!=len(sr)+len(HOLES)or set(physical_ref_map)!=set(sr)|HOLES:problems.append({'physical_component_set_mismatch':{'count':len(physical_components),'missing':sorted((set(sr)|HOLES)-set(physical_ref_map)),'extra':sorted(str(r)for r in set(physical_ref_map)-(set(sr)|HOLES))}})
   text_checks=[]
   for ref,(_,sc)in sr.items():
    if ref not in physical_ref_map:continue
    cid=physical_ref_map[ref][0]['id'];na=[v for h,v in rows if h['type']=='ATTR'and v.get('parentId')==cid and v.get('key')=='Name'];va=[v for h,v in rows if h['type']=='ATTR'and v.get('parentId')==cid and v.get('key')=='Value'];old_va=[v for h,v in baseline if h['type']=='ATTR'and v.get('parentId')==cid and v.get('key')=='Value']
    fpname=[v for h,v in source_rows(fps[sc['props']['Footprint']])if h['type']=='ATTR'and v.get('key')=='Name']
    name_display=na if na else fpname
    name_ok=len(name_display)==1 and not name_display[0].get('keyVisible')and not name_display[0].get('valueVisible')and(not na or na[0]['value']==sc['props']['Name'])
    good=name_ok and len(va)==len(old_va)==1 and va[0]==old_va[0]and va[0]['value']==sc['props']['Value']
    text_checks.append({'ref':ref,'hidden_Name_and_unchanged_Value_ATTR_verified':good,'Name_display_source':'explicit component override'if na else'footprint library (same-library-value override pruned by save)','Name_value_source':'PCB API netlist independently matched SCH','Value_ATTR_identical':len(va)==len(old_va)==1 and va[0]==old_va[0]})
    if not good:problems.append({'physical_Name_or_Value_ATTR_changed':ref})
   source_geometry_audit['Name_and_Value_ATTR_checks']=text_checks
   for ref in sorted(HOLES):
    if ref not in physical_ref_map:problems.append({'physical_hole_missing':ref});continue
    h,v=physical_ref_map[ref];cid=h['id'];p={**v.get('attrs',{}),**attrs[cid]};old=baseline_components.get(cid)
    if old is None:problems.append({'physical_hole_id_changed':ref});continue
    oh,ov=old;op={**ov.get('attrs',{}),**baseline_attrs[cid]}
    before_geom={k:x for k,x in ov.items()if k!='attrs'};after_geom={k:x for k,x in v.items()if k!='attrs'}
    ev={'ref':ref,'component_id':cid,'unique_id':p.get('Unique ID'),'footprint_uuid':p.get('Footprint'),'device_uuid':p.get('Device'),'placement':{k:v.get(k)for k in ['layerId','x','y','angle','locked']},'all_component_nonattribute_fields_identical':before_geom==after_geom,'identity_equal':all(p.get(k)==op.get(k)for k in ['Designator','Unique ID','Footprint','Device']),'BOM':p.get('Add into BOM'),'Convert to PCB':p.get('Convert to PCB')}
    if not ev['all_component_nonattribute_fields_identical']or not ev['identity_equal']or p.get('Add into BOM')!='no'or p.get('Convert to PCB')!='no':problems.append({'physical_hole_changed':ev})
    np=blank_hole_evidence(ref,{'props':p});pads=np['pads'];ev['npth_pads']=pads
    # epro2 rounds source dimensions to 0.0001 mil (2.54 nm).
    # Use the same 5 nm serialization allowance as the PCB geometry audit;
    # final Excellon hole diameters are independently checked at exactly 3.2 mm.
    if len(pads)!=1 or any(abs(z['hole']['width']*0.0254-3.2)>0.000005 or abs(z['hole'].get('height',z['hole']['width'])*0.0254-3.2)>0.000005 for z in pads):problems.append({'physical_hole_dimension_unexpected':ref,'pads':pads})
    def hole_nets(rr):
     found=[]
     for hh,vv in rr:
      if hh['type']=='PAD_NET':
       try:_,cc,nn,ss=json.loads(hh['id'])
       except(ValueError,TypeError):continue
       if cc==cid:found.append((hh['id'],vv))
     return sorted(found,key=lambda x:x[0])
    ev['pad_net_records_unchanged']=hole_nets(rows)==hole_nets(baseline)
    if not ev['pad_net_records_unchanged']:problems.append({'mechanical_pad_net_changed':ref})
    physical_holes.append(ev)
  for h,v in rows:
   if h['type']=='PAD_NET':
    _,cid,num,sub=json.loads(h['id']);ref=attrs[cid]['Designator']
    if ref in sr and num in sr[ref][1]['pinInfoMap']:
     expected=sr[ref][1]['pinInfoMap'][num]['net'];entry={'ref':ref,'number':num,'subpad':sub,'actual':v.get('padNet',''),'expected':expected};physical_pins.append(entry)
     if entry['actual']!=expected:problems.append({'physical_PAD_NET_mismatch':entry})
 files=[a.pcb,a.schematic,a.source_xml,a.footprints]+([a.pcb_source]if a.pcb_source else[])+([a.baseline_pcb_source]if a.baseline_pcb_source else[])
 report={'inputs':{str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in files},'status':'PASS'if not problems else'FAIL','problems':problems,'counts':{'kicad_components':len(krefs),'schematic_components':len(sr),'pcb_components':len(pr),'expected_pcb_mechanical_components':len(HOLES),'kicad_logical_pins':len(kp),'schematic_logical_pins':len(sp),'pcb_logical_pins':len(pp),'kicad_partitions':len(kpart),'schematic_partitions':len(spart),'pcb_partitions':len(ppart),'netted_physical_pin_records_verified':len(physical_pins)},'named_pin_nets_match':not pin_mismatches,'connectivity_partitions_equal':kpart==spart==ppart,'pin_net_differences':pin_mismatches,'values':values,'DNP_refs':sorted(DNP),'assembly':assembly,'identity':identities,'allowed_mechanical_exceptions':npth_evidence,'extra_pcb_pins':extra_pins,'display_Name_rule':'PCB Name equals actual Value; SCH Name is library symbol title. Preserved intentionally.','name_checks':names,'all_property_differences':properties,'property_difference_counts':dict(collections.Counter(x['property']for x in properties)),'limits':['This report checks exported metadata and logical connectivity, not a substitute for final geometry/DRC and manufacturing checks.','Mechanical exceptions are explicitly proven unplated holes, not omitted by name alone.','PCB Source PAD_NET check covers duplicate physical subpads when --pcb-source is supplied.']}
 report['metadata_synced_mode']=a.metadata_synced
 report['physical_mechanical_holes']=physical_holes
 report['physical_source_geometry_audit']=source_geometry_audit
 report['counts']['physical_source_components']=len(physical_components)
 report['counts']['physical_source_mechanical_holes_verified']=len(physical_holes)
 if a.metadata_synced:report['display_Name_rule']='Explicit metadata-synced mode: PCB Name equals SCH library name; independent Value continues to match original KiCad actual value. Mechanical H1-H4 excluded from logical export, physically verified against pre-sync PCB source.'
 a.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:report[k]for k in ['status','problems','counts','named_pin_nets_match','connectivity_partitions_equal','property_difference_counts']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()

#!/usr/bin/env python3
"""Read-only final assembly metadata invariant; Python standard library only."""
import argparse,collections,csv,hashlib,json,math
from pathlib import Path
DNP={'C501','C502','J301','J302','J303','R108'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def states(path):
 result={}
 for line in path.read_text().splitlines():
  if not line.strip():continue
  h,v=line.split('||',1);h=json.loads(h);v=v[:-1]if v.endswith('|')else v;v=json.loads(v)if v else None
  key=h['type'],h.get('id')
  if key not in result or h.get('ticket',0)>=result[key][0].get('ticket',0):result[key]=h,v
 return {k:v for k,(h,v)in result.items()if v not in ('',None)}
def source_components(path):
 rows=states(path);attrs=collections.defaultdict(dict)
 for (kind,pid),v in rows.items():
  if kind=='ATTR':attrs[v['parentId']][v['key']]=v['value']
 result={}
 for (kind,pid),v in rows.items():
  if kind!='COMPONENT':continue
  props={**v.get('attrs',{}),**attrs[pid]};ref=props['Designator'];assert ref not in result
  result[ref]={'id':pid,'props':props,'instance':{k:x for k,x in v.items()if k!='attrs'}}
 return result
def main():
 ap=argparse.ArgumentParser(description=__doc__)
 for name in ['baseline-netlist','final-netlist','baseline-pcb-source','final-pcb-source','population','report']:
  ap.add_argument('--'+name,type=Path,required=True)
 a=ap.parse_args();old=json.loads(a.baseline_netlist.read_text());new=json.loads(a.final_netlist.read_text())
 oldc={c['props']['Designator']:c for c in old['components'].values()};newc={c['props']['Designator']:c for c in new['components'].values()}
 before=source_components(a.baseline_pcb_source);after=source_components(a.final_pcb_source);pop={r['reference']:r for r in csv.DictReader(a.population.open())};problems=[];records=[]
 if set(before)!=set(after)or set(after)!=set(pop)or len(after)!=240:problems.append('Physical component reference set differs')
 if set(oldc)!=set(newc)or len(newc)!=236:problems.append('Electrical component reference set differs')
 for ref in sorted(set(before)&set(after)&set(pop)):
  b,c,r=before[ref],after[ref],pop[ref];p=c['props']
  row={'ref':ref,'Value':p.get('Value'),'population_Value':r['value'],'value_equal_to_baseline':p.get('Value')==b['props'].get('Value'),'all_instance_attributes_equal':c==b,'group':r['assembly_group'],'electrical_component_equal':newc.get(ref)==oldc.get(ref)}
  if not row['all_instance_attributes_equal']or not row['electrical_component_equal']or not row['value_equal_to_baseline']:problems.append({'component_metadata_changed':row})
  if ref in newc:
   if p.get('Value')!=r['value']:problems.append({'population_Value_mismatch':row})
   row['Value_representation']='Explicit electrical Value'
  elif ref in {'H1','H2','H3','H4'}:
   # Mechanical-only objects do not export an electrical Value in either
   # snapshot; match the explicit retained device type rather than invent one.
   try:device=json.loads(p.get('DeviceName','{}')).get('name')
   except json.JSONDecodeError:device=None
   row['Value_representation']='No explicit electrical Value; mechanical device type MountingHole_3.2mm_M3'
   row['mechanical_device_type']=device
   if p.get('Value')is not None or b['props'].get('Value')is not None or r['value']!='M3 NPTH' or device!='MountingHole:MountingHole_3.2mm_M3' or p.get('Add into BOM')!='no' or r['assembly_group']!='mechanical_hole_only':problems.append({'mechanical_value_representation_mismatch':row})
  if ref in newc:
   np=newc[ref]['props'];is_dnp=np.get('DNP','no')=='yes'
   if is_dnp!=(ref in DNP)or np.get('Add into BOM')!=('no'if ref in DNP else'yes'):problems.append({'DNP_BOM_mismatch':ref})
   if np.get('Candidate_MPN','')!=r['candidate_mpn']or np.get('Manufacturer','')!=r['manufacturer']or np.get('Value')!=r['value']:problems.append({'population_electrical_metadata_mismatch':ref})
  elif ref not in {'H1','H2','H3','H4'}or p.get('Convert to PCB')!='no':problems.append({'mechanical_exclusion_mismatch':ref})
  records.append(row)
 counts=dict(collections.Counter(r['assembly_group']for r in pop.values()))
 expected={'top_smd_reflow':203,'post_reflow_tht_hand_solder':23,'post_reflow_smd_connector_hand_solder':4,'do_not_populate':6,'mechanical_hole_only':4}
 if counts!=expected:problems.append({'assembly_counts_mismatch':counts})
 inputs=[a.baseline_netlist,a.final_netlist,a.baseline_pcb_source,a.final_pcb_source,a.population]
 report={'status':'PASS'if not problems else'FAIL','problems':problems,'inputs':{str(p):sha(p)for p in inputs},'physical_components':len(after),'electrical_components':len(newc),'all_240_instance_metadata_and_placement_unchanged':before==after,'all_236_electrical_component_properties_and_pin_maps_unchanged':oldc==newc,'electrical_Value_fields_verified':236,'mechanical_references_verified_by_DeviceName':4,'mechanical_Value_representation':'H1-H4 have no explicit electrical Value in either snapshot; native M3 NPTH resolves to retained MountingHole_3.2mm_M3 device type and mechanical-only BOM/sync flags.','assembly_counts':counts,'DNP_refs':sorted(DNP),'rows':records,'scope':'Final export metadata/placement invariant chained to the independent KiCad/assembly/paste audit; does not replace Gerber geometry checks.'}
 a.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({k:v for k,v in report.items()if k not in ['inputs','rows']},ensure_ascii=False,indent=2))
 if problems:raise SystemExit(1)
if __name__=='__main__':main()

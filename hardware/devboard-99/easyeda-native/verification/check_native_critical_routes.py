#!/usr/bin/env python3
"""Read-only native terminal/copper/return audit; accepts a fresh source/state/archive.
No live API, KiCad geometry, or runtime pour cache is used as connectivity proof.
Independent current and before-SD-swap native netlists are required CLI inputs.
Includes USB data nets and actual Top-Bottom PTH transfers as well as vias.
"""
import argparse,json,math,collections,hashlib
from pathlib import Path
from shapely.strtree import STRtree
import native_source_geometry as ng
H=Path(__file__).resolve().parent
USB_DATA={'USB_DM_MCU','USB_DM_PORT','USB_DP_MCU','USB_DP_PORT'}
SD_SIGNAL={n for s in ['CLK','CMD','D0','D1','D2','D3']for n in ['SD_'+s,'SD_'+s+'_BUS','SD_CARD_'+s]}
AUDIO={'AUDIO_BCLK_BUF','AUDIO_WS_BUF','AUDIO_DIN_BUF','I2S_BCLK_AUDIO','I2S_WS_AUDIO','I2S_DIN_AUDIO','MIC_SD_RAW','AUDIO_SD_BUF','AUDIO_OE_N','I2S_BCLK','I2S_WS','SPEAKER_DATA','MIC_DATA'}
EPD_MAIN={'EPD_SCLK','EPD_MOSI','EPD_CS','EPD_DC','EPD_RST_N','EPD_BUSY'}
SHARED={'I2C_AON_SCL','I2C_AON_SDA','SD_IO_EN','TOUCH_IO_EN'}
SD_EXPECTED={
'U701':{'1':'SD_IO_EN','2':'SD_D1_BUS','3':'SD_CARD_D1','4':'SD_IO_EN','5':'SD_D0_BUS','6':'SD_CARD_D0','7':'GND','8':'SD_CARD_CLK','9':'SD_CLK_BUS','10':'SD_IO_EN','11':'SD_CARD_CMD','12':'SD_CMD_BUS','13':'SD_IO_EN','14':'SD_3V3'},
'U706':{'1':'SD_IO_EN','2':'SD_D3_BUS','3':'SD_CARD_D3','4':'SD_IO_EN','5':'SD_D2_BUS','6':'SD_CARD_D2','7':'GND','8':'','9':'','10':'GND','11':'','12':'','13':'GND','14':'SD_3V3'}}
def sha(p):return {'path':str(p.resolve()),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def logical(path):
 d=json.loads(path.read_text());return {(c['props']['Designator'],str(p['number'])):p.get('net')or'' for c in d['components'].values()for p in c['pinInfoMap'].values()}
def islands(rows,tol):
 uf=list(range(len(rows)));tree=STRtree([i['g']for i in rows])
 def find(a):
  while uf[a]!=a:uf[a]=uf[uf[a]];a=uf[a]
  return a
 for n,a in enumerate(rows):
  for z in tree.query(a['g'].buffer(tol)):
   z=int(z);b=rows[z]
   if z>n and a['layers']&b['layers']and a['g'].distance(b['g'])<=tol:uf[find(n)]=find(z)
 groups={}
 for n,i in enumerate(rows):
  o=groups.setdefault(find(n),{'terminals':[],'copper_ids':[],'layers':set()});o['copper_ids'].append(i['id']);o['layers'].update(i['layers'])
  if i['kind']=='pad':o['terminals'].append({'ref':i['ref'],'pin':i['pin'],'physical_id':i['id']})
 return [{**x,'layers':sorted(x['layers'])}for x in groups.values()]
def run(a):
 source,state,pads,holes,extra,evidence=ng.load_inputs(a);items,holes,keepouts,board,ignored=ng.source_geometry(source,pads+extra,holes)
 # POUR outlines are routing obstacles, not proof of copper. POURED may be an
 # opaque cache; this audit deliberately leaves all plane connectivity to CAM.
 items=[i for i in items if i['kind']not in {'pour','poured'}]
 expected=logical(a.netlist);actual=collections.defaultdict(list)
 for c in state:
  for p in c['pins']:actual[(c['ref'],str(p['n']))].append((p.get('net')or'',p['id']))
 pin_errors=[]
 for key in sorted(set(expected)|set(actual)):
  if key not in expected or key not in actual or any(n!=expected.get(key)for n,_ in actual.get(key,[])):pin_errors.append({'ref':key[0],'pin':key[1],'expected':expected.get(key),'actual':actual.get(key)})
 sd_errors=[]
 for ref,ps in SD_EXPECTED.items():
  for pin,net in ps.items():
   if (ref,pin)not in actual or any(n!=net for n,_ in actual.get((ref,pin),[])):sd_errors.append({'ref':ref,'pin':pin,'expected':net,'actual':actual.get((ref,pin))})
 before=logical(a.before_netlist);changed={key for key in set(expected)|set(before)if expected.get(key)!=before.get(key)}
 allowed={('U701',n)for n in ['2','3','5','6','8','9','11','12']}|{('U706',n)for n in ['2','3','5','6']}
 pairs=[('2','3'),('5','6'),('9','8'),('12','11')];bijection=[]
 for ref in ['U701','U706']:
  old=sorted((before.get((ref,x)),before.get((ref,y)))for x,y in pairs);new=sorted((expected.get((ref,x)),expected.get((ref,y)))for x,y in pairs)
  bijection.append({'ref':ref,'old_channel_net_pairs':old,'new_channel_net_pairs':new,'same_pair_multiset':old==new})
 permutation_pass=changed==allowed and all(x['same_pair_multiset']for x in bijection)and not sd_errors
 native_nets={n for n in expected.values()if n};groups={'USB_data':USB_DATA,'SD_all':{n for n in native_nets if n.startswith('SD_')},'EPD_all':{n for n in native_nets if n.startswith('EPD_')},'I2S':AUDIO,'shared_bus_enable':SHARED}
 selected=set().union(*groups.values());required=USB_DATA|SD_SIGNAL|AUDIO|EPD_MAIN|SHARED
 missing_nets=sorted(required-native_nets);connectivity={};opens=[]
 for net in sorted(selected):
  rows=[i for i in items if i['net']==net];gg=islands(rows,a.contact_tolerance_mm)if rows else[];terminals=[i for i in rows if i['kind']=='pad'];ok=len(gg)==1 and bool(terminals)
  connectivity[net]={'pass':ok,'physical_terminal_count':len(terminals),'logical_terminal_count':len({(i['ref'],i['pin'])for i in terminals}),'copper_islands':len(gg),'islands':gg}
  if not ok:opens.append(net)
 return_nets=USB_DATA|SD_SIGNAL|AUDIO|EPD_MAIN|SHARED|{n for n in native_nets if n.startswith('EPD_BUF_')or n.startswith('EPD_PAD_')}
 ground=[i for i in items if i['net']=='GND'and i.get('anchor')and {15,16}.issubset(i['layers'])];returns=[]
 for v in items:
  if v['net']not in return_nets:continue
  incident={layer for r in items if r['net']==v['net']and r['kind']in{'line','arc','carc','poly'}and r['g'].distance(v['g'])<=a.contact_tolerance_mm for layer in r['layers']if layer in{1,2}}
  actual_pth_transfer=v['kind']=='pad'and v.get('anchor')and incident=={1,2}
  if v['kind']!='via'and not actual_pth_transfer:continue
  pt=v['g'].centroid;d,g=min((pt.distance(g['g'].centroid),g['id'])for g in ground);returns.append({'id':v['id'],'kind':v['kind'],'ref':v.get('ref'),'pin':v.get('pin'),'actual_routed_outer_layers':sorted(incident),'net':v['net'],'xy_mm':list(pt.coords[0]),'GND_vertical_access':g,'distance_center_mm':d,'preferred_le_1mm':d<=1.00001,'pass_le_2mm':d<=2.00001})
 returns.sort(key=lambda x:-x['distance_center_mm']);badreturns=[r for r in returns if not r['pass_le_2mm']]
 # Detect physical intersections involving any selected signal/support copper;
 # full manufacturing clearance/filled planes remain separate native DRC/CAM.
 tree=STRtree([i['g']for i in items]);shorts=[];seen=set()
 for n,i in enumerate(items):
  if i['net']not in selected:continue
  for z in tree.query(i['g']):
   z=int(z);j=items[z];pair=tuple(sorted((n,z)))
   if z==n or pair in seen or i['net']==j['net']or not i['layers']&j['layers']:continue
   seen.add(pair)
   if i['g'].intersection(j['g']).area>1e-9:shorts.append({'a':i['id'],'net_a':i['net'],'b':j['id'],'net_b':j['net']})
 status='PASS'if not(pin_errors or sd_errors or missing_nets or opens or badreturns or shorts)and permutation_pass else'FAIL'
 return {'status':status,'inputs':{k:sha(getattr(a,k))for k in ['source','state','archive','netlist','before_netlist']},'scope':{k:sorted(v)for k,v in groups.items()},'inventory':{'components':len(state),'physical_pads':len(pads),'native_logical_pins':len(actual),'expected_logical_pins':len(expected),'selected_nets':len(selected),'selected_physical_terminals':sum(x['physical_terminal_count']for x in connectivity.values()),'checked_signal_vias':sum(r['kind']=='via'for r in returns),'checked_actual_PTH_layer_transfers':sum(r['kind']=='pad'for r in returns)},'full_native_schematic_pin_check':{'pass':not pin_errors,'errors':pin_errors},'SD_equivalent_channel_mapping':{'pass':permutation_pass,'actual_expected_errors':sd_errors,'changed_logical_pins':[r+'.'+p for r,p in sorted(changed)],'allowed_changed_pins':[r+'.'+p for r,p in sorted(allowed)],'channel_pair_bijection':bijection,'intentional_U706_NC_pins':['8','9','11','12']},'connectivity':connectivity,'open_or_isolated_copper_nets':opens,'missing_required_nets':missing_nets,'physical_shorts':shorts,'return_scope':sorted(return_nets),'signal_returns':returns,'return_over_2mm':badreturns,'return_over_1mm_count':sum(not x['preferred_le_1mm']for x in returns),'max_return_distance_mm':max((x['distance_center_mm']for x in returns),default=0),'contact_tolerance_mm':a.contact_tolerance_mm,'limitations':['Source connectivity includes every terminal and all explicit copper fragments, including isolated traces/vias. No copper POUR outline or POURED cache is credited.','Ground via/PTH proximity proves only nearby plated vertical access. Actual connection to both inner GND planes requires native repour/DRC plus independent final CAM topology.','Full board clearance, assembly, thermal, impedance and functional timing qualification are separate checks.']}
def main():
 p=argparse.ArgumentParser(description=__doc__)
 for key in ['source','state','archive','output']:p.add_argument('--'+key,type=Path,required=True)
 p.add_argument('--netlist',type=Path,required=True);p.add_argument('--before-netlist',type=Path,required=True);p.add_argument('--contact-tolerance-mm',type=float,default=.0001);a=p.parse_args()
 try:r=run(a)
 except Exception as e:r={'status':'FAIL_INPUT_OR_UNMODELED_GEOMETRY','error':str(e)}
 a.output.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:r.get(k)for k in ['status','inventory','open_or_isolated_copper_nets','return_over_2mm','max_return_distance_mm','error']},ensure_ascii=False));return 0 if r['status']=='PASS'else 1
if __name__=='__main__':raise SystemExit(main())

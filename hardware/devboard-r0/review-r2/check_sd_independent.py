#!/usr/bin/env python3
"""Independent pin expectations transcribed from vendor functions; no generator imports."""
from pathlib import Path
import argparse,json,hashlib,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[3]
p=argparse.ArgumentParser();p.add_argument('--netlist',type=Path,default=ROOT/'hardware/devboard-r0/output/validation/peripheral-r2.net.xml');p.add_argument('--output',type=Path,default=Path(__file__).with_name('sd-independent-review.json'));a=p.parse_args()
r=ET.parse(a.netlist).getroot();actual={}
for net in r.findall('nets/net'):
 for n in net.findall('node'):
  name=net.get('name');actual[n.get('ref'),n.get('pin')]=None if name.startswith('unconnected-') else name.split('/')[-1]
e={
'U701':{'1':'SD_IO_EN','2':'SD_CLK_BUS','3':'SD_CARD_CLK','4':'SD_IO_EN','5':'SD_CMD_BUS','6':'SD_CARD_CMD','7':'GND','8':'SD_CARD_D0','9':'SD_D0_BUS','10':'SD_IO_EN','11':'SD_CARD_D1','12':'SD_D1_BUS','13':'SD_IO_EN','14':'SD_3V3'},
'U706':{'1':'SD_IO_EN','2':'SD_D2_BUS','3':'SD_CARD_D2','4':'SD_IO_EN','5':'SD_D3_BUS','6':'SD_CARD_D3','7':'GND','8':None,'9':None,'10':'GND','11':None,'12':None,'13':'GND','14':'SD_3V3'},
'J701':{'1':'SD_CARD_D2','2':'SD_CARD_D3','3':'SD_CARD_CMD','4':'SD_3V3','5':'SD_CARD_CLK','6':'GND','7':'SD_CARD_D0','8':'SD_CARD_D1','9':'SD_DETECT_CONTACT','10':'GND','SH':'GND'},
'R701':{'1':'SD_3V3','2':'SD_CARD_CMD'},'R702':{'1':'SD_3V3','2':'SD_CARD_D0'},'R703':{'1':'SD_3V3','2':'SD_CARD_D1'},'R704':{'1':'SD_3V3','2':'SD_CARD_D2'},'R705':{'1':'SD_3V3','2':'SD_CARD_D3'},
'R706':{'1':'SD_CARD_CLK','2':'GND'},'R708':{'1':'SD_CD_N','2':'SD_DETECT_CONTACT'},
'R710':{'1':'SD_CLK','2':'SD_CLK_BUS'},'R711':{'1':'SD_CMD','2':'SD_CMD_BUS'},'R712':{'1':'SD_D0','2':'SD_D0_BUS'},'R713':{'1':'SD_D1','2':'SD_D1_BUS'},'R714':{'1':'SD_D2','2':'SD_D2_BUS'},'R715':{'1':'SD_D3','2':'SD_D3_BUS'},
'C701':{'1':'SD_3V3','2':'GND'},'C702':{'1':'SD_3V3','2':'GND'},'C703':{'1':'SD_3V3','2':'GND'},'C704':{'1':'SD_CD_N','2':'GND'},'C705':{'1':'SD_3V3','2':'GND'},
'U702':{'1':'SD_CARD_CLK','2':'SD_CARD_CMD','3':'GND'},'U703':{'1':'SD_CARD_D0','2':'SD_CARD_D1','3':'GND'},'U704':{'1':'SD_CARD_D2','2':'SD_CARD_D3','3':'GND'},'U705':{'1':'SD_DETECT_CONTACT','2':'SD_3V3','3':'GND'}
}
fails=[]
for ref,pins in e.items():
 for pin,expect in pins.items():
  if (ref,pin) not in actual or actual[ref,pin]!=expect:fails.append({'ref':ref,'pin':pin,'expected':expect,'actual':actual.get((ref,pin),'MISSING')})
official={'1':'SEL1','2':'S1','3':'D1','4':'SEL2','5':'S2','6':'D2','7':'GND','8':'D3','9':'S3','10':'SEL3','11':'D4','12':'S4','13':'SEL4','14':'VDD'}
lib=next(x for x in r.findall('libparts/libpart') if x.get('part')=='TMUX1511PW')
libpins={x.get('num'):x.get('name') for x in lib.findall('pins/pin')}
if libpins!=official:fails.append({'library_pin_functions':libpins,'expected':official})
old=json.loads(Path(__file__).with_name('sd-nexperia-rejected-review.json').read_text())
report={'date':'2026-11-02','scope':'Independent SD pin and primary-source electrical review; not manufacturing approval','netlist':str(a.netlist.relative_to(ROOT)) if a.netlist.is_relative_to(ROOT) else str(a.netlist),'netlist_sha256':hashlib.sha256(a.netlist.read_bytes()).hexdigest(),'result':'PASS' if not fails else 'FAIL','pin_checks':sum(len(pins) for pins in e.values()),'components_checked':len(e),'failures':fails,'expected':e,'tmux_pin_functions_official':official,'tmux_actual_library_pin_functions':libpins,'connector':old['connector'],'switch':{'manufacturer':'Texas Instruments','mpn':'TMUX1511PWR','quantity':2,'source':'https://www.ti.com/lit/ds/symlink/tmux1511.pdf','revision':'SCDS390B, March2025','details':'See tmux1511-control-review.json for voltage boundaries, IOX/SEL leakage derivation and limitations. Two switches powered from SD_3V3; six SEL pins toSD_IO_EN; two unused SEL hardGND and corresponding S/D NC. Local C701/C705100n onSD_3V3.'},'resolved_issues':['Rejected Nexperia74CBTLV3245PW because its VSW absVCC+0.5 can be exceeded during unequal rail collapse. No TI evidence used for Nexperia part.','R223 external defaultLOW pull changed100k->10k: 6*2uA TMUX +1uA IOX =13uA, producing0.13V nominal, belowVILmax0.45V; do not count typical6Mohm internal pulls. Merged control sheet now uses10k.','TOUCH R215 same issue with4SEL:9uA leakage budget ->0.09V nominal10k; merged control+TOUCH notes use10k.'],'unclosed':['Hirose official catalog confirms A/B normally open, closed with card; standardKiCad9/10 maps nonpolar pair. Exact official mechanical drawing/letter orientation not visually confirmed because official download403; footprint remains candidate.','TMUX VDD1.5..1.65 V with3.3V signal is outside recommended operation range but belowabs6V; no all-rampHi-Z claim. Startup/shutdown/leakage need board measurements.','TCA9539 IIL specification requires validVCC; zero-VCC or brownout behavior is not proved by10k calculation.','SD20MHz target,4-bit signal integrity, cardpower pulses, ESD robustness and hot-remove/unmount handling require bench validation.'],'budget_notes':['Each10k select pull consumes330uA at3.3V while enabled.','TwoTMUX supply currents allocate140uA max in their stated table conditions, excluding loading.','Inserted-card detect with upstream100k consumes about33uA even whenSDpower isoff.'],'visual_review':'Final STORAGE_SD-preview.png inspected: no obvious overlapping signal labels, all spare no-connect marks and grouped SELs visible.'}
a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'result':report['result'],'pins':report['pin_checks'],'components':len(e),'failures':fails}))
raise SystemExit(bool(fails))

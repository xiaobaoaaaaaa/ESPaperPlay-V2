#!/usr/bin/env python3
"""Author the r2 SD interface in an explicit scratch directory."""
from pathlib import Path
import argparse
import importlib.util
import json
import re

REPO=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('h',REPO/'hardware/devboard-r0/tools/generate_power_schematic.py')
h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
h.GLOBAL.update({'SD_3V3','SD_EN','SD_IO_EN','SD_CD_N','SD_CLK','SD_CMD','SD_D0','SD_D1','SD_D2','SD_D3','SD_DETECT_CONTACT',
                 'SD_CARD_CLK','SD_CARD_CMD','SD_CARD_D0','SD_CARD_D1','SD_CARD_D2','SD_CARD_D3'})
EXPECTED={}
RFP='Resistor_SMD:R_0603_1608Metric'
CFP='Capacitor_SMD:C_0603_1608Metric'
def connect(s,ref,pins):
    s.connect(ref,pins);EXPECTED[ref]={str(k):v for k,v in pins.items()}
def passive(s,kind,ref,value,x,y,a,b,**kw):
    s.passive(kind,ref,value,x,y,a,b,**kw);EXPECTED[ref]={'1':a,'2':b}
def symbols():
    # Reuse the exact reviewed PW14 definition from the formal TOUCH sheet library.
    raw=(REPO/'hardware/devboard-r0/ESPaperPlay.kicad_sym').read_text()
    definition=h.block(raw,raw.index('(symbol "TMUX1511PW"'))
    definition=definition.replace('(symbol "TMUX1511PW"','(symbol "ESPaperPlay:TMUX1511PW"',1)
    h.CUSTOM['ESPaperPlay:TMUX1511PW']=definition
    h.LIBS['ESPaperPlay:TMUX1511PW']=definition

def sels(s,ref,pins,net):
    s.join_pins(ref,pins,net,1,5)
    for pin in pins[1:-1]:
        x,y,_=s.components[ref][pin]
        s.parts.append(f'(junction (at {h.n(x)} {h.n(y+h.mm(5))}) (diameter 0) '
                       f'(color 0 0 0 0) (uuid {h.q(s.unique("junction"))}))')
    EXPECTED[ref].update({pin:net for pin in pins})

def draw():
    s=h.Sheet('STORAGE_SD','MICROSD / 4-BIT BUS / INDEPENDENT SIGNAL ISOLATION',9)
    s.section('1  SIX-LINE BUS ISOLATION / SEPARATE SD_IO_EN CONTROL',14,12)
    s.text('Two TMUX1511PW on SD_3V3. IOX P13 controls isolation; P01 controls card power. Six bidirectional paths; no MCU-to-card bypass.',14,20,1.1)
    signals=['CLK','CMD','D0','D1','D2','D3']
    s.comp('ESPaperPlay:TMUX1511PW','U701','TI TMUX1511PW',55,60,
           prop_pos=(55,24,55,27),note='VDD is switched SD_3V3. All four used SEL pins connect SD_IO_EN, with existing R22310k pull-down on control page.')
    connect(s,'U701',{'14':'SD_3V3','7':'GND','1':False,'4':False,'10':False,'13':False,
        '2':'SD_CLK_BUS','3':'SD_CARD_CLK','5':'SD_CMD_BUS','6':'SD_CARD_CMD',
        '9':'SD_D0_BUS','8':'SD_CARD_D0','12':'SD_D1_BUS','11':'SD_CARD_D1'})
    sels(s,'U701',['1','4','10','13'],'SD_IO_EN')
    s.comp('ESPaperPlay:TMUX1511PW','U706','TI TMUX1511PW',128,60,
           prop_pos=(128,24,128,27),note='Only first two channels used. SEL3/4 tied GND, corresponding S/D pins NC. VDD follows card power, not AON.')
    connect(s,'U706',{'14':'SD_3V3','7':'GND','1':False,'4':False,'10':False,'13':False,
        '2':'SD_D2_BUS','3':'SD_CARD_D2','5':'SD_D3_BUS','6':'SD_CARD_D3',
        '9':None,'8':None,'12':None,'11':None})
    sels(s,'U706',['1','4'],'SD_IO_EN');sels(s,'U706',['10','13'],'GND')
    for i,name in enumerate(signals):
        x=181+43*(i%2);y=38+22*(i//2)
        passive(s,'R',f'R{710+i}','22R' if i==0 else '0R',x,y,'SD_'+name,'SD_'+name+'_BUS',angle=90,
                footprint=RFP,note='Initial source-series tuning position on MCU side. CLK starts22R; bidirectional CMD/DAT start0R. Tune after layout; no 40MHz guarantee.')
    s.comp('Connector:Micro_SD_Card_Det_Hirose_DM3AT','J701','Hirose DM3AT-SF-PEJM5',280,58,
           footprint='Connector_Card:microSD_HC_Hirose_DM3AT-SF-PEJM5',prop_pos=(280,33,280,36),
           note='Candidate matching KiCad footprint; mechanical sample/layout review still required. KiCad pads9/10 represent the nonpolar Hirose detection-contact pair A/B; exact physical A/B mapping remains a mechanical review item. Normally open; closes when inserted. SH pads all GND.')
    connect(s,'J701',{'1':'SD_CARD_D2','2':'SD_CARD_D3','3':'SD_CARD_CMD','4':'SD_3V3','5':'SD_CARD_CLK','6':'GND',
                     '7':'SD_CARD_D0','8':'SD_CARD_D1','9':'SD_DETECT_CONTACT','10':'GND','SH':'GND'})
    s.text('Physical card: 1 DAT2 / 2 DAT3 / 3 CMD / 4 VDD\n5 CLK / 6 GND / 7 DAT0 / 8 DAT1.\nNo 1.8V UHS mode. Begin at 400kHz init, then20MHz target.\nCD closes to GND on insertion; debounce in software.',224,85,1.0)
    s.section('2  CARD-SIDE PULL-UPS / DECOUPLING / DEFAULT DISCONNECT',14,100)
    for i,name in enumerate(['CMD','D0','D1','D2','D3']):
        passive(s,'R',f'R{701+i}','10k / 1%',26+58*i,118,'SD_3V3','SD_CARD_'+name,footprint=RFP,
                note='All five pull-ups stay on switched card power, including DAT1-3 when running1-bit mode.')
    passive(s,'R','R706','100k',26,157,'SD_CARD_CLK','GND',footprint=RFP,note='Weak card-side clock LOW while isolated; clock is not pulled up.')
    passive(s,'C','C701','100n / 10V',67,157,'SD_3V3','GND',footprint=CFP,note='Place next to U701 VDD pin14; follows switched card power.')
    passive(s,'C','C702','10u / 10V',106,157,'SD_3V3','GND',footprint='Capacitor_SMD:C_0805_2012Metric',note='Local card bulk; adds to C40622uF on POWER_DOMAINS. Validate effective capacitance and SD peak current.')
    passive(s,'C','C703','100n / 10V',145,157,'SD_3V3','GND',footprint=CFP,note='Place at card VDD/VSS contacts.')
    passive(s,'C','C705','100n / 10V',208,157,'SD_3V3','GND',footprint=CFP,note='Local U706 decoupling at VDD14.')
    s.text('SD_IO_EN (IOX P13): LOW isolates all six lines.\nR223=10k default pull-down on control page.\nConnect only after SD power has settled.',180,137,1.0)
    passive(s,'R','R708','100R',283,143,'SD_CD_N','SD_DETECT_CONTACT',angle=90,footprint=RFP,
            note='Mechanical detect series protection. Upstream R216100k toAON; CD is separate from card DAT3/CD pin2.')
    passive(s,'C','C704','10n / 10V',283,166,'SD_CD_N','GND',footprint=CFP,
            note='Nominal1ms with upstream100k. Mechanical debounce remains firmware responsibility; not a precise card-removal deadline.')
    s.flag('SD_3V3',166,146,'701')
    s.text('PWR_FLAG assumes R405 fitted.\nSD_3V3 is downstream of I_SD.',156,166,1.0)
    s.section('3  CONNECTOR-SIDE ESD / NO SUPPLY CLAMP RAIL',14,177)
    pairs=[('SD_CARD_CLK','SD_CARD_CMD'),('SD_CARD_D0','SD_CARD_D1'),('SD_CARD_D2','SD_CARD_D3'),('SD_DETECT_CONTACT','SD_3V3')]
    for i,(a,b) in enumerate(pairs):
        ref=f'U{702+i}';x=35+60*i
        s.comp('Power_Protection:TPD2E2U06DCK',ref,'TI TPD2E2U06DCKR',x,199,
               prop_pos=(x,184,x,187),note='Two parallel clamps to GND; IO1 pin1,IO2 pin2,GND pin3. Place near socket; short return. Does not certify board ESD performance or sustained power faults.')
        connect(s,ref,{'1':a,'2':b,'3':'GND'})
    s.text('ON: SD_IO_EN=0; enable SD_EN; wait validated rail-settle time; then SD_IO_EN=1 and initialize the card.\nOFF: block requests, flush/close/unmount, stop SDMMC; SD_IO_EN=0; then SD_EN=0. Never cut power on unmount timeout.\nTMUX: VDD<1.5V allows signal0..3.6V; ramps/functional behavior still need validation. Spare SELs LOW; spare S/D NC.\nSD power rail / GPIO hold / removal behavior / 4-bit20MHz signal integrity remain bench tests; no measured throughput claim.',14,214,0.95)
    return s

def save(s,out):
    s.save(out);file=out/(h.PROJECT+'.kicad_sch' if s.root else s.key+'.kicad_sch')
    file.write_text(file.read_text().replace('(date "2026-11-01")','(date "2026-11-02")').replace('(rev "r0 DRAFT")','(rev "r2 DRAFT")'))
def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();
    if a.output.exists() and any(a.output.iterdir()):
        raise SystemExit('Output must be an empty scratch directory; never overwrite the native project.')
    a.output.mkdir(parents=True,exist_ok=True)
    symbols();s=draw();save(s,a.output)
    root=h.Sheet('root','SD AUTHORING HARNESS',1,True)
    root.parts.append(f'''(sheet (at 30.48 50.8) (size 158.75 40.64)
        (stroke (width 0.254) (type default)) (fill (color 0 0 0 0)) (uuid {h.q(s.sheet_uuid)})
        {h.prop('Sheetname',s.key,30.48,48.26,justify='left')}
        {h.prop('Sheetfile',s.key+'.kicad_sch',30.48,93.98,justify='left')}
        (instances (project {h.q(h.PROJECT)} (path {h.q(root.path)} (page "9")))))''')
    save(root,a.output)
    defs='\n'.join(v.replace(h.q(k),h.q(k.split(':')[1]),1) for k,v in h.CUSTOM.items())
    (a.output/'sd.kicad_sym').write_text('(kicad_symbol_lib (version 20241209) (generator "kicad_symbol_editor")\n'+defs+'\n)\n')
    (a.output/'sym-lib-table').write_text('(sym_lib_table (version 7) (lib (name "ESPaperPlay") (type "KiCad") (uri "${KIPRJMOD}/sd.kicad_sym") (options "") (descr "SD isolation candidate")))\n')
    (a.output/(h.PROJECT+'.kicad_pro')).write_text(json.dumps({'meta':{'filename':h.PROJECT+'.kicad_pro','version':1}},indent=2)+'\n')
    (a.output/'expected-nets.json').write_text(json.dumps(EXPECTED,indent=2)+'\n')
    print(json.dumps({'components':len(EXPECTED),'pins':sum(len(x) for x in EXPECTED.values())}))
if __name__=='__main__':main()

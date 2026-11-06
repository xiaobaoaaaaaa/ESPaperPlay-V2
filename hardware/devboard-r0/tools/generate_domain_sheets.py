#!/usr/bin/env python3
"""Author editable peripheral-power / touch-isolation sheets in --output only.

Uses the existing project authoring helper without rewriting existing pages.
All timing, capacitance and connector selections remain design candidates.
"""
from pathlib import Path
import argparse
import importlib.util
import json

REPO = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('power_helper', REPO / 'hardware/devboard-r0/tools/generate_power_schematic.py')
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
h.GLOBAL.update({'EPD_EN', 'SD_EN', 'TOUCH_EN', 'AUDIO_EN', 'TOUCH_IO_EN',
                 'EPD_3V3', 'SD_3V3', 'TOUCH_3V3', 'MIC_3V3', 'AMP_SYS',
                 'I2C_AON_SDA', 'I2C_AON_SCL', 'TOUCH_RESET_N', 'TOUCH_INT',
                 'TP_RESET_N','TP_INT','TP_SDA','TP_SCL'})

EXPECT = {}
def connected(s, ref, pins):
    s.connect(ref, pins)
    EXPECT[ref] = {str(k): v for k, v in pins.items()}

def passive(s, kind, ref, value, x, y, a, b, **kw):
    s.passive(kind, ref, value, x, y, a, b, **kw)
    EXPECT[ref] = {'1': a, '2': b}

def symbols():
    # TI SLVSD76C p3, DBV top view. The ON pin must not float.
    h.custom('TPS22918DBV', [
        ('1','VIN','power_in',-12,4,0), ('3','ON','input',-12,-3,0),
        ('6','VOUT','power_out',12,4,180), ('5','QOD','passive',12,-3,180),
        ('2','GND','power_in',-4,-10,90), ('4','CT','passive',4,-10,90)],
        10,8,'Package_TO_SOT_SMD:SOT-23-6',
        'https://www.ti.com/lit/ds/symlink/tps22918.pdf')
    # TI SCDS390B p3, PW package only; INT is deliberately bidirectional.
    h.custom('TMUX1511PW', [
        ('14','VDD','power_in',0,18,270), ('7','GND','power_in',14,-13,180),
        ('2','S1','bidirectional',-14,10,0), ('3','D1','bidirectional',14,10,180),
        ('5','S2','bidirectional',-14,4,0), ('6','D2','bidirectional',14,4,180),
        ('9','S3','bidirectional',-14,-2,0), ('8','D3','bidirectional',14,-2,180),
        ('12','S4','bidirectional',-14,-8,0), ('11','D4','bidirectional',14,-8,180),
        ('1','SEL1','input',-9,-18,90), ('4','SEL2','input',-5,-18,90),
        ('10','SEL3','input',5,-18,90), ('13','SEL4','input',9,-18,90)],
        12,16,'Package_SO:TSSOP-14_4.4x5mm_P0.65mm',
        'https://www.ti.com/lit/ds/symlink/tmux1511.pdf')

def domains():
    s=h.Sheet('POWER_DOMAINS','PERIPHERAL POWER / FIVE SWITCHED DOMAINS',6)
    s.section('FIVE TPS22918 DOMAINS / COMPONENT VALUES ARE UNVALIDATED CANDIDATES',14,12)
    s.text('CT = 4.7nF / 25V; RQOD = 330R + internal RPD. 0R links measure downstream load only; switch IQ is upstream.',14,19,1.1)
    s.text('EPD/SD/TOUCH ON pulls: R212/R213/R214 on POWER_3V3_CONTROL. AUDIO_EN: R416 below. No reverse-current blocking.',14,24,1.1)
    rows=[('EPD','3V3_AON','EPD_3V3','EPD_EN','22u / 10V'),
          ('SD','3V3_AON','SD_3V3','SD_EN','22u / 10V'),
          ('TOUCH','3V3_AON','TOUCH_3V3','TOUCH_EN','4.7u / 10V'),
          ('MIC','3V3_AON','MIC_3V3','AUDIO_EN','1u / 10V'),
          ('AMP','SYS','AMP_SYS','AUDIO_EN','22u / 10V')]
    for i,(name,vin,vout,on,cout) in enumerate(rows):
        j=i+1; y=42+36*i; u=f'U{400+j}'
        s.text(f'{j}  {name}',14,y-10,1.35)
        s.comp('ESPaperPlay:TPS22918DBV',u,'TPS22918DBV',94,y,
               note='CANDIDATE; no current limit or reverse-current blocking claim; TI DBV pin table verified')
        connected(s,u,{'1':vin,'2':'GND','3':on,'4':f'{name}_CT','5':f'{name}_QOD','6':f'{name}_SW'})
        passive(s,'C',f'C{400+i*3+1}','1u / 10V',37,y+3,vin,'GND',
                note='Candidate local input bypass; coordinate with upstream converter and downstream bulk capacitance')
        passive(s,'C',f'C{400+i*3+2}','4.7n / 25V',150,y+3,f'{name}_CT','GND',
                note='Unvalidated timing candidate. TI table: approx 7.98ms rise at 3.3V; equation estimate 8.63ms')
        passive(s,'R',f'R{400+i*3+1}','330R / 1%',190,y+3,f'{name}_QOD',vout,
                note='QOD returns to LOAD side of current link. Remove this resistor too before external injection')
        passive(s,'R',f'R{400+i*3+2}',f'0R / I_{name}',221,y-8,f'{name}_SW',vout,angle=90,
                note='Removable load-current link, upstream-to-load direction. Rating/footprint TBD. Does not isolate QOD or signals')
        passive(s,'C',f'C{400+i*3+3}',cout,266,y+3,vout,'GND',
                note='Candidate downstream bulk; include peripheral capacitors when assessing inrush and discharge')
        s.connector(f'J{400+j}',f'{name}_PWR',302,y+3,[vout,'GND'])
        EXPECT[f'J{400+j}']={'1':vout,'2':'GND'}
    # One common external pull defines BOTH MIC and AMP switch defaults.
    passive(s,'R','R416','100k',154,210,'AUDIO_EN','GND',
            note='Populated hardware default for U404 and U405; GPIO4 high enables BOTH rails. No independent MIC/AMP power control')
    s.text('R416: both audio rails default OFF when GPIO4 is high impedance.\nSYS may remain alive with AON=0; measure AMP leakage in this state.',14,207,1.05)
    return s

def touch():
    s=h.Sheet('TOUCH_ISOLATION','GT911 FOUR-SIGNAL ISOLATION / DOMAIN TEST NOTES',7)
    s.section('1  TMUX1511PW: ALL FOUR SIGNALS ISOLATED / ACTIVE-HIGH SELECT',14,14)
    s.text('VDD, bypass, pull-ups and GT911 VCC all use TOUCH_3V3 AFTER R408 (I_TOUCH). Never power the switch from AON.',14,22,1.15)
    s.comp('ESPaperPlay:TMUX1511PW','U406','TMUX1511PW',117,72)
    connected(s,'U406',{'14':'TOUCH_3V3','7':'GND',
        '1':False,'4':False,'10':False,'13':False,
        '2':'I2C_AON_SDA','3':'TP_SDA','5':'I2C_AON_SCL','6':'TP_SCL',
        '9':'TOUCH_RESET_N','8':'TP_RESET_N','12':'TOUCH_INT','11':'TP_INT'})
    s.join_pins('U406',['1','4','10','13'],'TOUCH_IO_EN',1,5)
    # Explicit T-junctions are required at the two interior branch crossings.
    # Helper.join_pins only adds a junction at the center label branch.
    for pin in ['4','10']:
        x,y,_=s.components['U406'][pin]
        s.parts.append(f'(junction (at {h.n(x)} {h.n(y+h.mm(5))}) (diameter 0) '
                       f'(color 0 0 0 0) (uuid {h.q(s.unique("junction"))}))')
    EXPECT['U406'].update({k:'TOUCH_IO_EN' for k in ['1','4','10','13']})
    passive(s,'C','C416','100n / 10V',54,49,'TOUCH_3V3','GND',
            note='Local U406 decoupling; downstream of R408')
    passive(s,'C','C417','100n / 10V',277,49,'TOUCH_3V3','GND',
            note='GT911 interface local bypass; final panel capacitance unknown')
    passive(s,'R','R417','10k',188,49,'TOUCH_3V3','TP_SDA',
            note='Candidate: parallel with AON 4.7k only when switch is ON; include panel pull-ups in final calculation')
    passive(s,'R','R418','10k',229,49,'TOUCH_3V3','TP_SCL',
            note='Candidate: effective 4.7k || 10k = 3.20k before any panel pull-up')
    passive(s,'R','R419','100k',188,91,'TP_RESET_N','GND',
            note='Hold reset LOW while isolated; must obey full GT911 address-select/reset sequence after connecting signals')
    passive(s,'R','R420','100k',229,91,'TP_INT','GND',
            note='Weak default LOW only; MCU must actively drive address-selection phase then release INT to input')
    s.connector('J406','GT911_FUNCTIONAL_6PIN',300,83,
                ['GND','TOUCH_3V3','TP_RESET_N','TP_INT','TP_SDA','TP_SCL'])
    EXPECT['J406']={'1':'GND','2':'TOUCH_3V3','3':'TP_RESET_N','4':'TP_INT','5':'TP_SDA','6':'TP_SCL'}
    s.text('MCU / AON side\nGPIO10 SDA; GPIO13 SCL\nGPIO14 RESET; GPIO1 INT\nR210/R211: 4.7k to AON',14,68,1.1)
    s.text('R215 = 100k to GND on control sheet.\nAll SELs LOW: isolated; HIGH: connected.\nINT remains bidirectional for GT911 boot.',14,100,1.1)
    s.text('6-pin FUNCTIONAL mapping only.\nFPC pitch, contact side, latch and\nfootprint await actual sample.',258,105,1.1)
    s.flag('TOUCH_3V3',181,111,'406')
    s.text('PWR_FLAG: normal assembly with R408 fitted.\nERC does not model an open measurement link.',194,108,1.0)
    s.section('2  POWER / SIGNAL SEQUENCING AND MEASUREMENT',14,126)
    s.text('ON: keep TOUCH_IO_EN=0; power TOUCH; wait for valid rail; set MCU RESET/INT; connect TMUX; execute full GT911 reset.\nOFF: stop access and touch wake; set TOUCH_IO_EN=0; then TOUCH_EN=0. Do not reset IOX merely on one I2C error.\nStart I2C at 100kHz. Pull-up estimate is 3.20k with the present 4.7k and 10k; include actual panel resistors and capacitance.\nPowered-off protection: signal pins <=3.6V for VDD<1.5V; verify supply ramps and signal leakage with actual hardware.\nWith AON=0: R215 must pull SEL LOW even while TOUCH retains charge. GPIO hold/reset behavior is not a power guarantee.',14,135,1.1)
    s.section('3  LOAD-SWITCH REVIEW / MEASUREMENT LIMITS',14,167)
    s.text('Target for each low-voltage load rail: <0.2V within 1s after OFF. EPD high-voltage nodes are outside this target.\nCT=4.7nF: TI table ~8ms at 3.3V; formula ~8.6ms (3.3V), ~11.5ms (4.4V). Actual load turn-on and inrush need measurement.\nQOD=330R external plus internal RPD. Example only: 200uF, 355R, 3.3V -> 0.2V in ~0.20s with VIN still valid.\nInput loss weakens QOD; timing is not guaranteed at VIN=0. Do not backfeed a rail while QOD is discharging it.\nRemove measurement 0R only AFTER stopping the peripheral and isolating its signals. QOD remains connected on the load side.\nTOUCH: opening R408 also removes TMUX VDD; I2C pulls remain on that same isolated load rail. Verify residual voltage first.\nExternal rail injection requires upstream 0R AND QOD resistor removal, plus reviewed signal isolation; no direct supply paralleling.',14,176,1.05)
    s.text('Add actual EPD-driver / SD / audio capacitance before final CT and QOD selection.\nSYS -> AMP is a supply gate, not a 5V boost. No load switch provides fault-current limiting.\nRefs: TI SLVSD76C pp3,13-15; SCDS390B pp3-4,20-22. Values are NOT bench-validated.',14,215,1.0)
    return s

def main():
    p=argparse.ArgumentParser(); p.add_argument('--output',type=Path,required=True)
    args=p.parse_args(); args.output.mkdir(parents=True,exist_ok=True)
    if list(args.output.glob('*.kicad_sch')): raise SystemExit('Use an empty scratch output directory; never overwrite manual schematics.')
    symbols(); sheets=[domains(),touch()]
    for s in sheets:
        s.save(args.output)
        file=args.output/(s.key+'.kicad_sch')
        file.write_text(file.read_text().replace('(date "2026-11-01")','(date "2026-11-02")').replace('(rev "r0 DRAFT")','(rev "r1 DRAFT")'))
    (args.output/'expected-nets.json').write_text(json.dumps(EXPECT,indent=2)+'\n')
    custom='\n'.join(v.replace(h.q(k),h.q(k.split(':')[1]),1) for k,v in h.CUSTOM.items())
    (args.output/'domains.kicad_sym').write_text('(kicad_symbol_lib (version 20241209) (generator "kicad_symbol_editor")\n'+custom+'\n)\n')
    (args.output/'sym-lib-table').write_text('(sym_lib_table (version 7)\n'
        ' (lib (name "ESPaperPlay") (type "KiCad") (uri "${KIPRJMOD}/domains.kicad_sym") (options "") (descr "TPS22918 and TMUX1511 draft symbols")))\n')
    print(f'Wrote {len(sheets)} pages / {sum(len(s.components) for s in sheets)} components to {args.output}')

if __name__=='__main__': main()

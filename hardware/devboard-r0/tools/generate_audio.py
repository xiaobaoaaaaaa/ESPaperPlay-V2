#!/usr/bin/env python3
"""Author the r2 audio review page in an empty scratch output directory."""
from pathlib import Path
import argparse
import importlib.util
import json
import re

REPO=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('h',REPO/'hardware/devboard-r0/tools/generate_power_schematic.py')
h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
h.GLOBAL.update({'MIC_3V3','AMP_SYS','AUDIO_EN','AMP_SHUTDOWN','I2S_BCLK','I2S_WS','MIC_DATA','SPEAKER_DATA'})
EXPECTED={}
RFP='Resistor_SMD:R_0603_1608Metric'
CFP='Capacitor_SMD:C_0603_1608Metric'

def connect(s,ref,mapping):
    s.connect(ref,mapping);EXPECTED[ref]={str(k):v for k,v in mapping.items()}

def passive(s,kind,ref,val,x,y,a,b,**kw):
    kw.setdefault('footprint',RFP if kind=='R' else CFP)
    s.passive(kind,ref,val,x,y,a,b,**kw);EXPECTED[ref]={'1':a,'2':b}

def custom_symbols():
    # KiCad geometry/pin map retained; ADI pin table says EP is not internally
    # connected and must be connected to GND. Model thermal pad as passive,
    # instead of the standard library's unspecified pin-17 ERC type.
    raw=h.standard('Audio:MAX98357A')
    name='MAX98357AETE_REVIEWED'
    raw=raw.replace('"Audio:MAX98357A"',h.q('ESPaperPlay:'+name),1)
    raw=raw.replace('(symbol "MAX98357A_', '(symbol "'+name+'_')
    for match in re.finditer(r'\(pin unspecified ',raw):
        pin=h.block(raw,match.start())
        if '(number "17"' in pin:
            raw=raw.replace(pin,pin.replace('(pin unspecified ','(pin passive ',1),1)
            break
    else:raise ValueError('Expected MAX98357A unspecified EP17 not found')
    h.CUSTOM['ESPaperPlay:'+name]=raw;h.LIBS['ESPaperPlay:'+name]=raw
    # Nexperia 74LVC125A Rev12 pp3/6; do NOT substitute TI SN74LVC125A
    # solely by family name: the selected Nexperia part explicitly specifies Ioff.
    h.custom('74LVC125APW_NEXPERIA',[
        ('14','VCC','power_in',0,22,270),('7','GND','power_in',14,-18,180),
        ('2','1A','input',-14,12,0),('3','1Y','tri_state',14,12,180),
        ('5','2A','input',-14,4,0),('6','2Y','tri_state',14,4,180),
        ('9','3A','input',-14,-4,0),('8','3Y','tri_state',14,-4,180),
        ('12','4A','input',-14,-12,0),('11','4Y','tri_state',14,-12,180),
        ('1','~{1OE}','input',-8,-22,90),('4','~{2OE}','input',-4,-22,90),
        ('10','~{3OE}','input',4,-22,90),('13','~{4OE}','input',8,-22,90)],
        12,20,'Package_SO:TSSOP-14_4.4x5mm_P0.65mm',
        'https://assets.nexperia.com/documents/data-sheet/74LVC125A.pdf')
    # PUI official drawing p6: 7 pads, different from the former ICS-43434.
    h.custom('DMM-4026-B-I2S-R',[
        ('3','VDD','power_in',0,16,270),('4','GND','power_in',0,-16,90),
        ('5','WS','input',-13,6,0),('6','SCK','input',-13,0,0),
        ('1','LR','input',13,-4,180),('2','CONFIG','input',13,-10,180),
        ('7','SD','tri_state',13,8,180)],11,12,'',
        'https://api.puiaudio.com/filename/DMM-4026-B-I2S-R.pdf')
    # TI SCES223U p3: DBV five-pin package (not 6-pad SON variants).
    h.custom('SN74LVC1G125DBV_AUDIO',[
        ('5','VCC','power_in',0,10,270),('3','GND','power_in',0,-10,90),
        ('2','A','input',-9,2,0),('1','~{OE}','input',-9,-4,0),
        ('4','Y','tri_state',9,2,180)],7,8,
        'Package_TO_SOT_SMD:SOT-23-5',
        'https://www.ti.com/lit/ds/symlink/sn74lvc1g125.pdf')
    h.custom('SN74LVC1G14DBV_AUDIO',[
        ('5','VCC','power_in',0,10,270),('3','GND','power_in',0,-10,90),
        ('2','A_ST','input',-9,2,0),('1','NC','no_connect',-9,-4,0),
        ('4','Y_INV','output',9,2,180)],7,8,
        'Package_TO_SOT_SMD:SOT-23-5',
        'https://www.ti.com/lit/ds/symlink/sn74lvc1g14.pdf')

def draw_audio():
    s=h.Sheet('AUDIO','AUDIO / I2S INPUT ISOLATION / MONO PLAYBACK + MIC',10)
    s.section('1  FOUR MCU OUTPUTS / AUDIO_EN HARDWARE DISABLE',14,14)
    s.comp('ESPaperPlay:74LVC125APW_NEXPERIA','U801','Nexperia 74LVC125APW',74,57,
        prop_pos=(74,21,74,24),note='Exact manufacturer required: Nexperia Ioff-specified 74LVC125APW,118. All four /OE pins are linked. VCC on switched MIC domain.')
    connect(s,'U801',{'14':'MIC_3V3','7':'GND','2':'I2S_BCLK','3':'AUDIO_BCLK_BUF',
        '5':'I2S_WS','6':'AUDIO_WS_BUF','9':'SPEAKER_DATA','8':'AUDIO_DIN_BUF',
        '12':'AMP_SHUTDOWN','11':'AUDIO_SD_BUF','1':False,'4':False,'10':False,'13':False})
    s.join_pins('U801',['1','4','10','13'],'AUDIO_OE_N',1,4)
    for pin in ['4','10']:
        x,y,_=s.components['U801'][pin]
        s.parts.append(f'(junction (at {h.n(x)} {h.n(y+h.mm(4))}) (diameter 0) '
                       f'(color 0 0 0 0) (uuid {h.q(s.unique("junction"))}))')
    EXPECTED['U801'].update({p:'AUDIO_OE_N' for p in ['1','4','10','13']})
    for ref,y,a,b in [('R808',44,'AUDIO_BCLK_BUF','I2S_BCLK_AUDIO'),
                      ('R809',59,'AUDIO_WS_BUF','I2S_WS_AUDIO'),
                      ('R810',74,'AUDIO_DIN_BUF','I2S_DIN_AUDIO')]:
        passive(s,'R',ref,'22R',134,y,a,b,angle=90,
            note='Initial damping value, place close to U801 output. Validate edges and total I2S setup/hold.')
    s.comp('ESPaperPlay:SN74LVC1G14DBV_AUDIO','U805','TI SN74LVC1G14DBVR',42,105,
        prop_pos=(42,85,42,88),note='Schmitt inverter with Ioff. AUDIO_EN LOW actively raises all four OE pins before normal MIC rail decay. R416 already defaults GPIO4 LOW. Active edge avoids a 100k pull-up violating U801 input slew constraints.')
    connect(s,'U805',{'1':None,'2':'AUDIO_EN','3':'GND','4':'AUDIO_OE_N','5':'MIC_3V3'})
    passive(s,'C','C806','100n / 10V',91,106,'MIC_3V3','GND',
        note='U805 local decoupling; same switched rail as U801.')
    passive(s,'C','C801','100n / 10V',134,106,'MIC_3V3','GND',note='Place at U801 supply pins, not at remote power switch.')
    s.text('AUDIO_EN=0: U805 actively disables all outputs while MIC rail is valid.\nAt VCC=0, use the selected vendor Ioff specification; not zero leakage.\nR306 already pulls MCU AMP_SHUTDOWN low; R416 pulls AUDIO_EN low.',14,121,1.0)

    s.section('2  MAX98357A / SYS SUPPLY / LEFT CHANNEL / 6dB',175,14)
    s.comp('ESPaperPlay:MAX98357AETE_REVIEWED','U802','MAX98357AETE+T',237,57,
        prop_pos=(237,29,237,32),note='TQFN16+EP17. Gain=6dB via VDD. SD_MODE selects LEFT, not hardware stereo mixing. EP connects GND for thermal path.')
    connect(s,'U802',{'1':'I2S_DIN_AUDIO','2':'AMP_SYS','3':False,'4':'AMP_SD_MODE',
        '5':None,'6':None,'7':'AMP_SYS','8':'AMP_SYS','9':'AMP_OUTP','10':'AMP_OUTN',
        '11':False,'12':None,'13':None,'14':'I2S_WS_AUDIO','15':False,'16':'I2S_BCLK_AUDIO','17':False})
    s.join_pins('U802',['3','17'],'GND',1,3)
    EXPECTED['U802'].update({p:'GND' for p in ['3','11','15','17']})
    passive(s,'C','C802','100n / 10V',186,44,'AMP_SYS','GND',note='Place immediately at VDD7/8.')
    passive(s,'C','C803','10u / 10V',302,108,'AMP_SYS','GND',
        footprint='Capacitor_SMD:C_0805_2012Metric',note='Local bulk in addition to C415=22u at switch; use effective capacitance for startup/inrush tests.')
    passive(s,'R','R806','2.00k / 1%',224,87,'AUDIO_SD_BUF','AMP_SD_MODE',angle=90,
        note='ADI-recommended current limiting when 3.3V I/O exceeds low VDD; this is NOT complete power-off isolation.')
    for ref,net,x in [('R802','I2S_BCLK_AUDIO',180),('R803','I2S_WS_AUDIO',211),('R804','I2S_DIN_AUDIO',242),('R805','AMP_SD_MODE',273)]:
        passive(s,'R',ref,'100k',x,112,net,'GND',note='Load-side default low when U801 disabled. SD_MODE has an additional internal approximately 100k pull-down.')
    # Two current-rated zero-ohm options can later be replaced with qualified EMI beads.
    passive(s,'R','R811','0R / SPK_P',285,47,'AMP_OUTP','SPK_P',angle=90,footprint='',
        note='Speaker pulse-current rating/footprint TBD; optional qualified ferrite replacement only after EMI/current review.')
    passive(s,'R','R812','0R / SPK_N',285,67,'AMP_OUTN','SPK_N',angle=90,footprint='',
        note='Differential output; never connect either speaker terminal to GND.')
    s.comp('Connector_Generic:Conn_01x02','J801','SPEAKER / 8R CANDIDATE',310,83,
        footprint='',prop_pos=(285,75,285,78),note='Functional BTL connector; exact MPN/footprint and speaker/lead current rating TBD. Neither terminal may be grounded.')
    s.connect('J801',{'1':'SPK_P','2':'SPK_N'})
    EXPECTED['J801']={'1':'SPK_P','2':'SPK_N'}
    s.text('BTL speaker: neither terminal is ground. 8 ohm is a candidate, not a frozen speaker BOM.\nNo 5V boost or 3W guarantee; evaluate output/THD/pop at lowest battery and USB transitions.',175,128,1.0)

    s.section('3  PUI I2S MIC CANDIDATE / DATA RETURN ISOLATION',14,141)
    s.comp('ESPaperPlay:DMM-4026-B-I2S-R','U803','DMM-4026-B-I2S-R',64,173,
        prop_pos=(64,145,64,148),note='PUI public catalogue candidate; lifecycle/supply to confirm before BOM freeze. Exact 7-pad footprint/acoustic hole pending. LR=LOW selects LEFT; CONFIG=LOW required at power-up.')
    connect(s,'U803',{'1':'GND','2':'GND','3':'MIC_3V3','4':'GND','5':'I2S_WS_AUDIO','6':'I2S_BCLK_AUDIO','7':'MIC_SD_RAW'})
    passive(s,'C','C804','100n / 10V',20,169,'MIC_3V3','GND',note='PUI pin table requires local 0.1uF at VDD3.')
    passive(s,'C','C805','1u / 10V',20,200,'MIC_3V3','GND',note='Local bulk candidate; review Wi-Fi/EPD noise and power-ramp behavior.')
    s.comp('ESPaperPlay:SN74LVC1G125DBV_AUDIO','U804','TI SN74LVC1G125DBVR',128,172,
        prop_pos=(128,151,128,154),note='AON-powered return buffer, overvoltage-tolerant input and explicit Ioff at VCC=0. Prevent direct MIC residual supply injection into an unpowered MCU input.')
    connect(s,'U804',{'1':'GND','2':'MIC_SD_RAW','3':'GND','4':'MIC_DATA','5':'3V3_AON'})
    passive(s,'R','R813','100k',93,203,'MIC_SD_RAW','GND',note='PUI p6 required SD pull-down releases the tri-state slot; place before the return buffer.')
    passive(s,'C','C808','100n / 10V',140,203,'3V3_AON','GND',note='Local U804 decoupling; included in AON sleep-current budget.')
    s.text('PUI pin map: 1 LR, 2 CONFIG, 3 VDD, 4 GND, 5 WS, 6 SCK, 7 SD.\nBoth control straps LOW. Footprint is NOT the old six-pad ICS-43434.\nAON return buffer remains powered during deep sleep; budget its ICC/leakage.',14,218,1.0)

    s.section('4  FIRST BRING-UP CONTRACT / NOT MEASURED',175,149)
    s.text('Start at 48kHz, two 32-bit I2S slots, BCLK=64fs=3.072MHz.\nPUI: 24-bit data / 18-bit precision; LEFT slot. 20ms is a datasheet startup\nreference only; discard initial frames with measured settling margin.\n32/44.1/48kHz are the candidate shared set; 32k is at the MIC clock floor.\nThe old 16kHz firmware profile is NOT valid for this microphone candidate.\nSoftware mixes/resamples playback into LEFT; no automatic stereo average.\n\nON: hold AMP_SHUTDOWN low and clocks/data low; enable AUDIO_EN;\nwait for both rails; establish clocks/zeros; discard settling frames; unmute.\nOFF: mute first, finish audio, stop BCLK without leaving BCLK running\nwith LRCLK absent; drive signals low, then AUDIO_EN=0.\nMIC/AMP discharge rates differ: measure SD_MODE injection and pops.\nMute/stop before opening R411/R414. Never inject external rail power\nwithout reviewing QOD, buffer paths and supply disconnection.\n\nU801/U805 use the MIC rail; U804 remains on AON. Each adds leakage.\nDynamic clocks and pull-down currents belong in the active audio budget.\nActual speaker, MIC lifecycle, acoustic port and EMI remain review gates.',175,159,1.0)
    s.flag('MIC_3V3',311,146,'801');s.flag('AMP_SYS',311,162,'802')
    s.text('Flags: R411/R414 fitted.\nNot a power-fault model.',284,177,0.9)
    return s

def save(sheet,out):
    sheet.save(out)
    p=out/((h.PROJECT if sheet.root else sheet.key)+'.kicad_sch')
    p.write_text(p.read_text().replace('(date "2026-11-01")','(date "2026-11-02")').replace('(rev "r0 DRAFT")','(rev "r2 DRAFT")'))

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();
    if a.output.exists() and any(a.output.iterdir()):
        raise SystemExit('Output must be an empty scratch directory; never overwrite the native project.')
    a.output.mkdir(parents=True,exist_ok=True)
    custom_symbols();s=draw_audio();save(s,a.output)
    root=h.Sheet('root','AUDIO AUTHORING HARNESS',1,True)
    sx,sy,w,ht=h.mm(25),h.mm(50),h.mm(125),h.mm(32)
    root.parts.append(f'''(sheet (at {sx} {sy}) (size {w} {ht}) (stroke (width 0.254) (type default)) (fill (color 0 0 0 0))
      (uuid {h.q(s.sheet_uuid)}) {h.prop('Sheetname',s.key,sx,sy-2.54,justify='left')}
      {h.prop('Sheetfile',s.key+'.kicad_sch',sx,sy+ht+2.54,justify='left')}
      (instances (project {h.q(h.PROJECT)} (path {h.q(root.path)} (page "10")))))''')
    save(root,a.output)
    definitions='\n'.join(v.replace(h.q(k),h.q(k.split(':')[1]),1) for k,v in h.CUSTOM.items())
    (a.output/'audio.kicad_sym').write_text('(kicad_symbol_lib (version 20241209) (generator "kicad_symbol_editor")\n'+definitions+'\n)\n')
    (a.output/'sym-lib-table').write_text('(sym_lib_table (version 7) (lib (name "ESPaperPlay") (type "KiCad") (uri "${KIPRJMOD}/audio.kicad_sym") (options "") (descr "r2 audio symbols")))\n')
    (a.output/(h.PROJECT+'.kicad_pro')).write_text(json.dumps({'meta':{'filename':h.PROJECT+'.kicad_pro','version':1}},indent=2)+'\n')
    (a.output/'expected-nets.json').write_text(json.dumps(EXPECTED,indent=2)+'\n')
    print(f'Wrote AUDIO page with {len(EXPECTED)} physical components')

if __name__=='__main__':main()

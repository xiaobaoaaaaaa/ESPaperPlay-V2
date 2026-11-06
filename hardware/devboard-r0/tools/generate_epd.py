#!/usr/bin/env python3
"""Author the EPD r2 sheet into an empty scratch directory. Never overwrite native edits."""
from pathlib import Path
import argparse,importlib.util,json,re
REPO=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('h',REPO/'hardware/devboard-r0/tools/generate_power_schematic.py')
h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
NETS={'EPD_3V3','EPD_SCLK','EPD_MOSI','EPD_CS','EPD_DC','EPD_RST_N','EPD_BUSY',
      'EPD_GDR','EPD_RESE','EPD_SW','EPD_FLY','EPD_VSHR','EPD_PREVGH','EPD_PREVGL','EPD_VSH1','EPD_VSL','EPD_VCOM','EPD_VDD_INT',
      'EPD_PAD_SCLK','EPD_PAD_MOSI','EPD_PAD_CS','EPD_PAD_DC','EPD_PAD_RST_N','EPD_PAD_BUSY',
      'EPD_BUF_SCLK','EPD_BUF_MOSI','EPD_BUF_CS','EPD_BUF_DC','EPD_BUF_RST_N'}
h.GLOBAL.update(NETS - {'EPD_SW'})  # Local to this sheet; the power sheet has a distinct switch node.
EXPECT={}
RF='Resistor_SMD:R_0603_1608Metric';CF='Capacitor_SMD:C_0805_2012Metric'

def connect(s,ref,m):
    s.connect(ref,m);EXPECT[ref]={str(k):v for k,v in m.items()}
def passive(s,kind,ref,value,x,y,a,b,**kw):
    s.passive(kind,ref,value,x,y,a,b,**kw);EXPECT[ref]={'1':a,'2':b}
def ds(s,url):
    s.parts[-1]=re.sub(r'(\(property "Datasheet" )"[^"]*"',lambda m:m[1]+h.q(url),s.parts[-1])

def symbols():
    pin_names=['NC','GDR','RESE','NC','VSHR','TSCL','TSDA','BS1','BUSY','RES_N','D/C','CS_N','SCL','SDA','VDDIO','VCI','VSS','VDD_INT','VPP','VSH1','VGH','VSL','VGL','VCOM']
    h.custom('GDEY075T7_24PIN',[(str(i+1),name,'passive',-15,23-i*2,0) for i,name in enumerate(pin_names)],13,25,'',
             'https://www.good-display.cn/companyfile/1506.html')
    pins=[('20','VCC','power_in',0,17,270),('10','GND','power_in',0,-17,90),
          ('1','~{OE1}','input',-14,-11,0),('19','~{OE2}','input',-14,-13,0)]
    for i in range(8):
        pins.extend([(str(2+i),f'A{i+1}','input',-14,13-3*i,0),(str(18-i),f'Y{i+1}','tri_state',14,13-3*i,180)])
    h.custom('SN74LVC1G125DBV',[('1','~{OE}','input',-10,-3,0),('2','A','input',-10,3,0),('3','GND','power_in',0,-10,90),('4','Y','tri_state',10,3,180),('5','VCC','power_in',0,10,270)],8,8,'Package_TO_SOT_SMD:SOT-23-5','https://www.ti.com/lit/ds/symlink/sn74lvc1g125.pdf')
    h.custom('SN74LVC541APW',pins,12,15,'Package_SO:TSSOP-20_4.4x6.5mm_P0.65mm','https://www.ti.com/lit/ds/symlink/sn74lvc541a.pdf')

def make_sheet():
    s=h.Sheet('EPD_DISPLAY','EPD REFERENCE BOOST / 24-PIN PANEL / DOMAIN BUFFERS',8)
    s.section('1  GOOD DISPLAY p38 BOOST TOPOLOGY / CANDIDATE PARTS',14,13)
    s.text('3.3V input only. Panel-generated HV: no external supply injection. Values are reference starting points, not measured.',14,20,1.0)
    passive(s,'C','C603','4.7u / 25V',25,45,'EPD_3V3','GND',footprint=CF)
    s.comp('Device:L','L601','10uH / >=1A target',65,36,angle=90,footprint='',
           note='MPN/footprint TBD. Reference figure says 10uH 1A; table references NR3015 500mA(max). Verify saturation, RMS, DCR and actual boost peaks.',prop_pos=(65,29,65,32))
    connect(s,'L601',{'1':'EPD_3V3','2':'EPD_SW'})
    s.comp('Transistor_FET:Si1308EDL','Q601','Vishay Si1308EDL-T1-GE3',69,65,
           footprint='Package_TO_SOT_SMD:SOT-323_SC-70',prop_pos=(79,63,79,66),
           note='Actual Vishay part only. 1G/2S/3D; 30V; Rds_on max185mOhm at Vgs2.5V. Not the legacy TECH PUBLIC same-name part.')
    ds(s,'https://www.vishay.com/docs/63399/si1308edl.pdf')
    connect(s,'Q601',{'1':'EPD_GDR','2':'EPD_RESE','3':'EPD_SW'})
    passive(s,'R','R601','1M / 1%',26,87,'EPD_GDR','GND',footprint=RF)
    passive(s,'R','R602','0.47R / 1%',73,92,'EPD_RESE','GND',footprint='',
            note='Kelvin sense at Q601 source and ground return. Package/pulse rating TBD; use measured peak current to qualify.')
    for ref,x,y,k,a in [('D601',135,36,'EPD_FLY','EPD_PREVGL'),('D602',135,60,'GND','EPD_FLY'),('D603',135,85,'EPD_PREVGH','EPD_SW')]:
        s.comp('Diode:MBR0530',ref,'onsemi MBR0530',x,y,angle=90,footprint='Diode_SMD:D_SOD-123',prop_pos=(x+9,y-2,x+9,y+1),
               note='onsemi MBR0530/D Rev2: 30V,500mA,Vf max430mV at500mA/25C. Pin1 cathode, pin2 anode. Do not substitute legacy vendor by name alone.')
        ds(s,'https://www.onsemi.com/download/data-sheet/pdf/mbr0530-d.pdf')
        connect(s,ref,{'1':k,'2':a})
    passive(s,'C','C602','4.7u / 50V',114,109,'EPD_FLY','EPD_SW',angle=90,footprint=CF,
            note='Flying capacitor, NOT to ground. Effective capacitance and peak difference voltage require verification.')
    s.text('D601: A=VGL, K=FLY; D602: A=FLY, K=GND; D603: A=SW, K=VGH.\nQ601 source is RESE, not direct GND. Keep SW/FLY loops compact.\nHV MLCC: X5R/X7R, effective capacitance at bias must be qualified.',14,118,1.0)
    s.section('2  PANEL PINS / STORAGE AND DECOUPLING',176,13)
    s.comp('ESPaperPlay:GDEY075T7_24PIN','J601','EPD FPC 24 x 0.5mm',297,67,prop_pos=(297,33,297,36),
           note='Functional physical pin map only; exact connector MPN/contact side/footprint TBD against actual sample. Mechanical hold-down pads are not signal pins 25/26.')
    connect(s,'J601',{'1':None,'2':'EPD_GDR','3':'EPD_RESE','4':None,'5':'EPD_VSHR','6':None,'7':None,
        '8':'GND','9':'EPD_PAD_BUSY','10':'EPD_PAD_RST_N','11':'EPD_PAD_DC','12':'EPD_PAD_CS',
        '13':'EPD_PAD_SCLK','14':'EPD_PAD_MOSI','15':'EPD_3V3','16':'EPD_3V3','17':'GND',
        '18':'EPD_VDD_INT','19':None,'20':'EPD_VSH1','21':'EPD_PREVGH','22':'EPD_VSL','23':'EPD_PREVGL','24':'EPD_VCOM'})
    caps=[('C601','4.7u / 50V','EPD_VSHR',183,39),('C604','4.7u / 50V','EPD_PREVGH',223,39),
          ('C605','1u / 25V','EPD_3V3',183,66),('C606','1u / 25V','EPD_VDD_INT',223,66),
          ('C607','4.7u / 50V','EPD_VSH1',183,93),('C608','4.7u / 50V','EPD_VSL',223,93),
          ('C609','4.7u / 50V','EPD_PREVGL',183,120),('C610','1u / 50V','EPD_VCOM',223,120)]
    for ref,val,net,x,y in caps:passive(s,'C',ref,val,x,y,net,'GND',footprint=CF,note='Panel reference nominal capacitance. X5R/X7R effective value/voltage derating to verify.')
    s.text('BS1=0: 4-wire SPI, write-only SDI in this board.\nNC 1/4/19; unused external-temp pins6/7 left open.\nVDD18 is INTERNAL: C606 only; never short to3.3V.\n24 signal contacts; retention pads depend on connector.',259,106,1.0)
    s.section('3  FIVE MCU OUTPUTS / EPD-SUPPLIED Ioff BUFFER',14,140)
    s.comp('ESPaperPlay:SN74LVC541APW','U601','TI SN74LVC541APWR',62,181,prop_pos=(62,150,62,153),
           note='Five write-only MCU signals. Inputs tolerate5.5V; Ioff specified at VCC=0. Output supply follows EPD_3V3. No guarantee of high-Z throughout rail ramp.')
    connect(s,'U601',{'1':'GND','19':'GND','20':'EPD_3V3','10':'GND',
        '2':'EPD_SCLK','3':'EPD_MOSI','4':'EPD_CS','5':'EPD_DC','6':'EPD_RST_N',
        '7':'GND','8':'GND','9':'GND','18':'EPD_BUF_SCLK','17':'EPD_BUF_MOSI','16':'EPD_BUF_CS',
        '15':'EPD_BUF_DC','14':'EPD_BUF_RST_N','13':None,'12':None,'11':None})
    passive(s,'C','C611','100n / 10V',24,166,'EPD_3V3','GND',footprint='Capacitor_SMD:C_0603_1608Metric')
    s.flag('EPD_3V3',22,201,'601')
    s.text('Flag: R402 populated, normal RUN only.\nUnused buffer inputs tied low; outputs NC.',14,210,0.95)
    for i,name in enumerate(['SCLK','MOSI','CS','DC','RST_N']):
        passive(s,'R',f'R{603+i}','33R',128,159+i*11,f'EPD_BUF_{name}',f'EPD_PAD_{name}',angle=90,footprint=RF,
                note='Series damping candidate at buffer output. Tune from actual FPC signal integrity; no rate guarantee.')
    s.section('4  DEFAULTS / BUSY RETURN',171,140)
    for i,(net,a,b) in enumerate([('EPD_SCLK','EPD_SCLK','GND'),('EPD_MOSI','EPD_MOSI','GND'),('EPD_CS','3V3_AON','EPD_CS'),('EPD_DC','EPD_DC','GND'),('EPD_RST_N','EPD_RST_N','GND')]):
        x=180+(i%3)*38;y=158+(i//3)*27
        passive(s,'R',f'R{608+i}','100k',x,y,a,b,footprint=RF,note='MCU-side hardware default during reset/high-Z. CS high, all other write signals low.')
    passive(s,'R','R613','100k',256,185,'EPD_PAD_RST_N','GND',footprint=RF,note='Panel reset held low if buffer output is high-Z.')
    s.comp('ESPaperPlay:SN74LVC1G125DBV','U602','TI SN74LVC1G125DBVR',292,163,
           prop_pos=(292,137,292,140),note='AON-supplied BUSY buffer; protects MCU domain when panel retains charge. Ioff at AON=0; no rail-ramp guarantee.')
    ds(s,'https://www.ti.com/lit/ds/symlink/sn74lvc1g125.pdf')
    connect(s,'U602',{'1':'GND','2':'EPD_PAD_BUSY','3':'GND','4':'EPD_BUSY','5':'3V3_AON'})
    passive(s,'R','R614','100k',298,185,'EPD_PAD_BUSY','GND',footprint=RF,
            note='Domain OFF/unplugged -> BUSY low (busy/invalid), never ready. Software must qualify the rail state first.')
    passive(s,'C','C612','100n / 10V',159,183,'3V3_AON','GND',footprint='Capacitor_SMD:C_0603_1608Metric')
    s.text('Before ON: CS=1, RESET=0, CLK/MOSI/DC=0; wait valid rail, then reset panel.\nBefore OFF: finish refresh, sleep panel, hold safe signals; disable EPD supply.\nBuffers do not replace reset timing or leakage/ramp testing. BUSY low while OFF is invalid.\nNo SDI readback. Check +/-HV, gate/current-sense and FPC before connecting the panel.',168,205,0.95)
    return s

def save(s,out):
    s.save(out);p=out/(h.PROJECT+'.kicad_sch' if s.root else s.key+'.kicad_sch')
    p.write_text(p.read_text().replace('(date "2026-11-01")','(date "2026-11-02")').replace('(rev "r0 DRAFT")','(rev "r2 DRAFT")'))

def main():
    a=argparse.ArgumentParser();a.add_argument('--output',type=Path,required=True);args=a.parse_args();
    if args.output.exists() and any(args.output.iterdir()):
        raise SystemExit('Output must be an empty scratch directory; never overwrite the native project.')
    args.output.mkdir(parents=True,exist_ok=True)
    symbols();s=make_sheet();save(s,args.output)
    root=h.Sheet('root','EPD AUTHORING HARNESS',1,True)
    root.parts.append(f'''(sheet (at 30.48 50.8) (size 158.75 40.64) (stroke (width 0.254) (type default)) (fill (color 0 0 0 0)) (uuid {h.q(s.sheet_uuid)}) {h.prop('Sheetname',s.key,30.48,48.26,justify='left')} {h.prop('Sheetfile',s.key+'.kicad_sch',30.48,93.98,justify='left')} (instances (project {h.q(h.PROJECT)} (path {h.q(root.path)} (page "8")))))''')
    save(root,args.output)
    (args.output/(h.PROJECT+'.kicad_pro')).write_text(json.dumps({'meta':{'filename':h.PROJECT+'.kicad_pro','version':1}},indent=2)+'\n')
    defs='\n'.join(v.replace(h.q(k),h.q(k.split(':')[1]),1) for k,v in h.CUSTOM.items())
    (args.output/'epd.kicad_sym').write_text('(kicad_symbol_lib (version 20241209) (generator "kicad_symbol_editor")\n'+defs+'\n)\n')
    (args.output/'sym-lib-table').write_text('(sym_lib_table (version 7) (lib (name "ESPaperPlay") (type "KiCad") (uri "${KIPRJMOD}/epd.kicad_sym") (options "") (descr "EPD r2 symbols")))\n')
    (args.output/'expected-nets.json').write_text(json.dumps(EXPECT,indent=2)+'\n')
    print('Wrote EPD sheet with',len(s.components),'symbols')
if __name__=='__main__':main()

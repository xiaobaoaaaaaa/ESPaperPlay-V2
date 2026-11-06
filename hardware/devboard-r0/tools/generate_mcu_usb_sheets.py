#!/usr/bin/env python3
"""Author MCU/USB review sheets into a scratch output, never over hardware sources."""
from pathlib import Path
import argparse
import importlib.util
import json
import re

REPO = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('power_helpers', REPO/'hardware/devboard-r0/tools/generate_power_schematic.py')
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)

# Physical WROOM-1 module pad numbers, independently checked against Espressif
# WROOM-1/1U datasheet v1.8 Table 3-1; these are NOT ESP32-S3 chip pin numbers.
MODULE_PINS = {
 '1':('GND','GND'), '2':('3V3','3V3_AON'), '3':('EN','MCU_EN'),
 '4':('IO4','AUDIO_EN'), '5':('IO5','KEY_MINUS_N'), '6':('IO6','AMP_SHUTDOWN'),
 '7':('IO7','I2S_WS'), '8':('IO15','EPD_MOSI'), '9':('IO16','EPD_SCLK'),
 '10':('IO17','EPD_CS'), '11':('IO18','EPD_DC'), '12':('IO8','EPD_RST_N'),
 '13':('USB_D-','USB_DM_MCU'), '14':('USB_D+','USB_DP_MCU'),
 '15':('IO3',None), '16':('IO46',None), '17':('IO9','EPD_BUSY'),
 '18':('IO10','I2C_AON_SDA'), '19':('IO11','MIC_DATA'), '20':('IO12','I2S_BCLK'),
 '21':('IO13','I2C_AON_SCL'), '22':('IO14','TOUCH_RESET_N'),
 '23':('IO21','POWER_KEY_N'), '24':('IO47','SD_D0'), '25':('IO48','SD_D1'),
 '26':('IO45',None), '27':('IO0','BOOT_N'), '28':('IO35',None),
 '29':('IO36',None), '30':('IO37',None), '31':('IO38','SD_CLK'),
 '32':('IO39','SD_CMD'), '33':('IO40','SD_D3'), '34':('IO41','SD_D2'),
 '35':('IO42','IOX_RESET_N'), '36':('RXD0','KEY_PLUS_N'),
 '37':('TXD0','SPEAKER_DATA'), '38':('IO2','VBUS_SENSE_N'),
 '39':('IO1','TOUCH_INT'), '40':('GND','GND'), '41':('GND','GND'),
}
CROSS_SHEET = {v[1] for v in MODULE_PINS.values() if v[1]} - {'MCU_EN','BOOT_N','KEY_MINUS_N','KEY_PLUS_N','POWER_KEY_N'}
h.GLOBAL.update(CROSS_SHEET | {'KEY_PLUS_N','KEY_MINUS_N','POWER_KEY_N'})
h.GLOBAL.update({'EPD_3V3','SD_3V3','MIC_3V3','AMP_SYS','SD_CD_N','USB_VBUS','VIN_5V','BENCH_5V','USB_5V_PROTECTED'})
RFP='Resistor_SMD:R_0603_1608Metric'
CFP='Capacitor_SMD:C_0603_1608Metric'

def check_library():
    raw=h.standard('RF_Module:ESP32-S3-WROOM-1')
    names={}
    for m in re.finditer(r'\(pin (?:input|output|bidirectional|power_in|passive) ',raw):
        b=h.block(raw,m.start())
        names[re.search(r'\(number "([^"]+)"',b)[1]]=re.search(r'\(name "([^"]+)"',b)[1]
    assert names=={p:v[0] for p,v in MODULE_PINS.items()}, names

def draw_mcu():
    check_library()
    s=h.Sheet('MCU_CORE','ESP32-S3 N16R8 / RESET / USER KEYS',4)
    s.section('1  MCU / N16R8 PHYSICAL PAD MAPPING',18,17)
    s.comp('RF_Module:ESP32-S3-WROOM-1','U301','ESP32-S3-WROOM-1-N16R8',76,78,
        note='16 MB Quad Flash / 8 MB Octal PSRAM; pads 28-30 cannot be used. Standard symbol verified against official datasheet v1.8 Table 3-1.',
        prop_pos=(76,46,76,49))
    s.connect('U301',{p:v[1] for p,v in MODULE_PINS.items()})
    s.text('NC: GPIO3 / 45 / 46 (straps); GPIO35 / 36 / 37 (PSRAM).\nDo not substitute WROOM-1-N16R16V: pad voltage differs.\nPads 24 / 25 = GPIO47 / 48, respectively.\nAntenna at PCB edge; final keepout per module land pattern.',18,118,1.15)
    s.text('LOCAL BYPASS',122,35,1.3)
    s.passive('C','C301','10u / 10V',135,58,'3V3_AON','GND',footprint='Capacitor_SMD:C_0805_2012Metric',note='X5R. Place near module pad 2. Verify effective capacitance under DC bias.')
    s.passive('C','C302','100n / 10V',135,91,'3V3_AON','GND',footprint=CFP,note='Place immediately beside module pad 2.')
    s.section('2  DEBUG FUNCTION HEADERS / LOAD CIRCUITS PENDING',18,145)
    debug=[('J301','EPD_DEBUG',42,['EPD_3V3','GND','EPD_SCLK','EPD_MOSI','EPD_CS','EPD_DC','EPD_RST_N','EPD_BUSY']),
           ('J302','SD_DEBUG',87,['SD_3V3','GND','SD_CLK','SD_CMD','SD_D0','SD_D1','SD_D2','SD_D3','SD_CD_N']),
           ('J303','AUDIO_DEBUG',132,['MIC_3V3','AMP_SYS','GND','I2S_BCLK','I2S_WS','MIC_DATA','SPEAKER_DATA','AMP_SHUTDOWN'])]
    for ref,value,x,nets in debug:
        s.comp(f'Connector_Generic:Conn_01x{len(nets):02d}',ref,value,x,177,
            footprint=f'Connector_PinHeader_2.54mm:PinHeader_1x{len(nets):02d}_P2.54mm_Vertical',
            note='Temporary function/debug interface. No external power injection. Connect peripherals only with the owning supply enabled. Replace with final interface after circuit review.',
            prop_pos=(x,159,x,162))
        s.connect(ref,{str(i+1):n for i,n in enumerate(nets)})
    s.passive('R','R306','100k',150,121,'AMP_SHUTDOWN','GND',footprint=RFP,note='Default hardware mute at MCU reset. Final amplifier must define compatible active-low shutdown polarity.')
    s.text('DEBUG: no external power injection; connect loads only with their domain ON.\nAudio: MIC_3V3 and AMP_SYS are different supplies; check module voltage.\nFinal EPD / SD / audio drivers and their off-state isolation remain pending.\nModule pads 1 / 40 / 41 (EPAD) to GND; PCB antenna keepout required.',18,202,1.0)
    s.section('3  MAINTENANCE RESET / DOWNLOAD',163,17)
    s.passive('R','R301','10k',184,43,'3V3_AON','MCU_EN',footprint=RFP)
    s.passive('C','C303','1u / 10V',218,43,'MCU_EN','GND',footprint=CFP)
    s.comp('Switch:SW_Push','SW301','RESET',265,43,prop_pos=(265,36,265,38.5),note='Maintenance only. Pulls EN low; not the user power key.')
    s.connect('SW301',{'1':'MCU_EN','2':'GND'})
    s.passive('R','R302','10k',184,79,'3V3_AON','BOOT_N',footprint=RFP)
    s.comp('Switch:SW_Push','SW302','BOOT',265,79,prop_pos=(265,72,265,74.5),note='Hold BOOT then pulse RESET for ROM recovery. Do not fit a large capacitor on GPIO0.')
    s.connect('SW302',{'1':'BOOT_N','2':'GND'})
    s.text('EN: 10k / 1uF initial RC; validate actual power ramp.\nBOOT: pull-up only, no large capacitor.\nGPIO43 / 44 are assigned: no always-connected UART0.\nNative USB Serial/JTAG is the default recovery/debug path.',164,100,1.15)
    s.section('4  USER KEYS / SOFTWARE DEBOUNCE',163,132)
    for ref,net,x in [('R303','POWER_KEY_N',176),('R304','KEY_PLUS_N',224),('R305','KEY_MINUS_N',272)]:
        s.passive('R',ref,'47k',x,153,'3V3_AON',net,footprint=RFP)
    for ref,value,net,x in [('SW303','POWER / IO21','POWER_KEY_N',176),('SW304','PLUS / IO44','KEY_PLUS_N',224),('SW305','MINUS / IO5','KEY_MINUS_N',272)]:
        s.comp('Switch:SW_Push',ref,value,x,181,prop_pos=(x,173,x,176),note='Local board button to GND; software debounce. External enclosure cable requires separate ESD review.')
        s.connect(ref,{'1':net,'2':'GND'})
    s.text('IO21 is the normal sleep/wake key. EN is a separate service control.\nI2C pull-ups and IOX_RESET_N pull-down live on POWER_3V3_CONTROL.\nEPD / SD / touch / audio signals are global labels to their owning sheets.',163,197,1.05)
    return s

def draw_usb():
    s=h.Sheet('USB_INPUT','USB-C DEVICE / ESD / 5V SOURCE SELECTION',5)
    s.section('1  USB-C DEVICE / NO PD / NO HOST POWER',18,17)
    s.comp('Connector:USB_C_Receptacle_USB2.0_16P','J501','USB-C USB2 16P',42,62,
        footprint='',prop_pos=(42,34,42,37),note='Mechanical receptacle MPN and footprint TBD. Verify real A/B pin mapping and shield tabs before PCB release. USB device/sink only, no VBUS sourcing.')
    s.connect('J501',{'A1':'GND','A4':'USB_VBUS','A5':'USB_CC1','A6':'USB_DP_PORT','A7':'USB_DM_PORT','A8':None,'A9':'USB_VBUS','A12':'GND',
        'B1':'GND','B4':'USB_VBUS','B5':'USB_CC2','B6':'USB_DP_PORT','B7':'USB_DM_PORT','B8':None,'B9':'USB_VBUS','B12':'GND','SH':'GND'})
    s.comp('Power_Protection:TPD2E2U06DCK','U502','TI TPD2E2U06DCKR',119,62,
        prop_pos=(119,48,119,51),note='CC1 / CC2 ESD clamp to GND. Does not provide sustained CC-to-VBUS overvoltage protection.')
    s.connect('U502',{'1':'USB_CC1','2':'USB_CC2','3':'GND'})
    s.passive('R','R501','5.1k 1%',42,112,'USB_CC1','GND',footprint=RFP,note='Independent Rd on CC1; never tie CC1 and CC2 together.')
    s.passive('R','R502','5.1k 1%',96,112,'USB_CC2','GND',footprint=RFP,note='Independent Rd on CC2; no PD or CC current sensing in this revision.')
    s.text('CC1 / CC2 each have their own Rd.\nA6+B6 = D+; A7+B7 = D-.\nShield bonded to local GND at connector; final EMC review required.',18,132,1.0)
    s.section('2  DATA ESD / MCU-SIDE MATCHING',163,17)
    s.comp('Power_Protection:TPD2E2U06DCK','U501','TI TPD2E2U06DCKR',193,53,
        prop_pos=(193,34,193,37),note='Parallel clamp at receptacle; short ground return. IO1=DP and IO2=DM. No VBUS clamp rail or cross-source rail backfeed path.')
    s.connect('U501',{'1':'USB_DP_PORT','2':'USB_DM_PORT','3':'GND'})
    s.passive('R','R503','22R',254,46,'USB_DP_PORT','USB_DP_MCU',angle=90,footprint=RFP,note='Place close to MCU; tune from signal integrity results, initial 22 ohm per Espressif guidance.')
    s.passive('R','R504','22R',254,76,'USB_DM_PORT','USB_DM_MCU',angle=90,footprint=RFP,note='Matched routing with R503; no stubs on final differential pair.')
    s.passive('C','C501','TUNE / DNP',296,46,'USB_DP_MCU','GND',dnp=True,footprint=CFP,note='Unpopulated initial build. Do not assume a capacitance without USB signal-integrity measurement.')
    s.passive('C','C502','TUNE / DNP',296,84,'USB_DM_MCU','GND',dnp=True,footprint=CFP,note='Unpopulated initial build. Matched footprint to C501 near MCU.')
    s.text('USB_DM_MCU -> GPIO19 / module pad13.\nUSB_DP_MCU -> GPIO20 / module pad14.\nTarget 90 ohm differential; short pair, continuous GND return.\nUSB default 100mA; firmware authorization precedes any 500mA mode.\nCC resistors do not negotiate PD, or authorize 1.5A / 3A.\nNo ESD / USB compliance claim until board-level validation.',163,110,1.1)
    s.section('3  USB BRANCH PROTECTION / SINGLE-SHUNT SOURCE SELECT',18,156)
    s.comp('Device:Polyfuse','F501','MF-MSMF110/16X-2',47,181,angle=90,
        footprint='Fuse:Fuse_1812_4532Metric',note='Bourns: 1.10A hold / 2.20A trip at 23C; 16V; 0.58A hold at 85C. Fault protection, not a precision 1.1A current limit. Validate thermal derating.')
    s.connect('F501',{'1':'USB_VBUS','2':'USB_5V_PROTECTED'})
    s.comp('Diode:SMAJ6.0A','D501','AOS SMAJ6.0A',99,183,angle=270,
        footprint='Diode_SMD:D_SMA',prop_pos=(120,180,120,183),note='AOS unidirectional TVS: pad1 cathode to protected USB, pad2 anode to GND. VRWM6V, VC max10.3V @38.8A pulse, 25C. 6V leakage bound800uA. Not sustained OVP.')
    s.parts[-1]=re.sub(r'(\(property \"Datasheet\" )\"[^\"]*\"',r'\1'+h.q('https://www.aosmd.com/sites/default/files/res/datasheets/SMAJ6.0A.pdf'),s.parts[-1])
    s.connect('D501',{'1':'USB_5V_PROTECTED','2':'GND'})
    s.passive('C','C503','100n / 16V',150,184,'USB_VBUS','GND',footprint=CFP,note='USB port-side bypass. Include BQ input 4.7u and all other port-visible capacitance in USB inrush budget.')
    s.comp('Connector_Generic:Conn_01x03','J502','ONE SHUNT: USB / BENCH',249,176,
        footprint='Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical',prop_pos=(249,162,249,165),
        note='One removable shunt only: 1-2 USB, 2-3 bench, all open isolated. Never fit both shunts. Bench supply regulated 5V with current limit; mechanical selection is not automatic reverse-current protection.')
    s.connect('J502',{'1':'USB_5V_PROTECTED','2':'VIN_5V','3':'BENCH_5V'})
    s.text('1-2 USB  /  2-3 BENCH  /  OPEN = input disconnected.\nVIN_5V goes to charger; protected USB is sensed before J502.\nOne shunt. Known regulated 5V, CURRENT-LIMITED bench input.',192,189,1.05)
    s.text('PTC / TVS protect the USB branch only; no sustained OVP or automatic source ORing.\nTVS leakage / overshoot, fault current, VBUS inrush and cable drop require tests.\nMechanical USB connector MPN / footprint and environmental current ratings are release gates.',18,207,1.05)
    return s

def save_sheet(sheet,out):
    sheet.save(out)
    p=out/(h.PROJECT+'.kicad_sch' if sheet.root else sheet.key+'.kicad_sch')
    p.write_text(p.read_text().replace('(date "2026-11-01")','(date "2026-11-02")').replace('(rev "r0 DRAFT")','(rev "r1 DRAFT")'))

def root_for(sheets):
    r=h.Sheet('root','MCU / USB AUTHORING REVIEW',1,True)
    r.section('AUTHORING HARNESS / NOT THE FINAL BOARD ROOT',18,20)
    r.text('Root UUID and project name match ESPaperPlay_Devboard for integration.',18,32)
    for i,c in enumerate(sheets):
        sx,sy,w,ht=h.mm(25+145*(i%2)),h.mm(57+70*(i//2)),h.mm(125),h.mm(32)
        r.parts.append(f'''(sheet (at {sx} {sy}) (size {w} {ht})
          (stroke (width 0.254) (type default)) (fill (color 0 0 0 0))
          (uuid {h.q(c.sheet_uuid)})
          {h.prop('Sheetname',c.key,sx,sy-2.54,justify='left')}
          {h.prop('Sheetfile',c.key+'.kicad_sch',sx,sy+ht+2.54,justify='left')}
          (instances (project {h.q(h.PROJECT)} (path {h.q(r.path)} (page {h.q(c.page)})))))''')
    return r

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    if list(args.output.glob('*.kicad_sch')): raise SystemExit('Use an empty scratch output directory; never overwrite manual schematics.')
    sheets=[draw_mcu(),draw_usb()]
    for s in [root_for(sheets),*sheets]:save_sheet(s,args.output)
    (args.output/'mcu-pin-map.json').write_text(json.dumps(MODULE_PINS,indent=2)+'\n')
    (args.output/'global-nets.json').write_text(json.dumps(sorted(h.GLOBAL),indent=2)+'\n')
    (args.output/(h.PROJECT+'.kicad_pro')).write_text(json.dumps({'meta':{'filename':h.PROJECT+'.kicad_pro','version':1}},indent=2)+'\n')

if __name__=='__main__':main()

#!/usr/bin/env python3
"""Check the native platform netlist against physical-pad and domain contracts.

This does not import drawing generators or their generated expected-net files.
ERC is required separately; assertions do not simulate switch/diode behavior.
"""
import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import check_power_netlist as power

# WROOM-1/1U v1.8 Table 3-1, physical module pads (not chip pad numbers).
MCU = {
    '1':'GND','2':'3V3_AON','3':'MCU_EN','4':'AUDIO_EN','5':'KEY_MINUS_N',
    '6':'AMP_SHUTDOWN','7':'I2S_WS','8':'EPD_MOSI','9':'EPD_SCLK',
    '10':'EPD_CS','11':'EPD_DC','12':'EPD_RST_N','13':'USB_DM_MCU',
    '14':'USB_DP_MCU','15':None,'16':None,'17':'EPD_BUSY',
    '18':'I2C_AON_SDA','19':'MIC_DATA','20':'I2S_BCLK','21':'I2C_AON_SCL',
    '22':'TOUCH_RESET_N','23':'POWER_KEY_N','24':'SD_D0','25':'SD_D1',
    '26':None,'27':'BOOT_N','28':None,'29':None,'30':None,'31':'SD_CLK',
    '32':'SD_CMD','33':'SD_D3','34':'SD_D2','35':'IOX_RESET_N',
    '36':'KEY_PLUS_N','37':'SPEAKER_DATA','38':'VBUS_SENSE_N',
    '39':'TOUCH_INT','40':'GND','41':'GND',
}
EXPECTED = {
    'U301': MCU,
    'J101': {'1':'BENCH_5V','2':'GND'},
    'C101': {'1':'VIN_5V','2':'GND'},
    'R301': {'1':'3V3_AON','2':'MCU_EN'},
    'C303': {'1':'MCU_EN','2':'GND'},
    'R302': {'1':'3V3_AON','2':'BOOT_N'},
    'SW301': {'1':'MCU_EN','2':'GND'},
    'SW302': {'1':'BOOT_N','2':'GND'},
    'SW303': {'1':'POWER_KEY_N','2':'GND'},
    'SW304': {'1':'KEY_PLUS_N','2':'GND'},
    'SW305': {'1':'KEY_MINUS_N','2':'GND'},
    'R306': {'1':'AMP_SHUTDOWN','2':'GND'},
    'J501': {'A1':'GND','A4':'USB_VBUS','A5':'USB_CC1','A6':'USB_DP_PORT',
        'A7':'USB_DM_PORT','A8':None,'A9':'USB_VBUS','A12':'GND',
        'B1':'GND','B4':'USB_VBUS','B5':'USB_CC2','B6':'USB_DP_PORT',
        'B7':'USB_DM_PORT','B8':None,'B9':'USB_VBUS','B12':'GND','SH':'GND'},
    'J502': {'1':'USB_5V_PROTECTED','2':'VIN_5V','3':'BENCH_5V'},
    'F501': {'1':'USB_VBUS','2':'USB_5V_PROTECTED'},
    'D501': {'1':'USB_5V_PROTECTED','2':'GND'},
    'U501': {'1':'USB_DP_PORT','2':'USB_DM_PORT','3':'GND'},
    'U502': {'1':'USB_CC1','2':'USB_CC2','3':'GND'},
    'R501': {'1':'USB_CC1','2':'GND'}, 'R502': {'1':'USB_CC2','2':'GND'},
    'R503': {'1':'USB_DP_PORT','2':'USB_DP_MCU'},
    'R504': {'1':'USB_DM_PORT','2':'USB_DM_MCU'},
    'C501': {'1':'USB_DP_MCU','2':'GND'}, 'C502': {'1':'USB_DM_MCU','2':'GND'},
    'C503': {'1':'USB_VBUS','2':'GND'},
    'R416': {'1':'AUDIO_EN','2':'GND'},
    # TI TMUX1511 PW (14 pins), four independent switches; all SEL pins tied.
    'U406': {'1':'TOUCH_IO_EN','2':'I2C_AON_SDA','3':'TP_SDA',
        '4':'TOUCH_IO_EN','5':'I2C_AON_SCL','6':'TP_SCL','7':'GND',
        '8':'TP_RESET_N','9':'TOUCH_RESET_N','10':'TOUCH_IO_EN',
        '11':'TP_INT','12':'TOUCH_INT','13':'TOUCH_IO_EN','14':'TOUCH_3V3'},
    'R417': {'1':'TOUCH_3V3','2':'TP_SDA'},
    'R418': {'1':'TOUCH_3V3','2':'TP_SCL'},
    'R419': {'1':'TP_RESET_N','2':'GND'},
    'R420': {'1':'TP_INT','2':'GND'},
    'C416': {'1':'TOUCH_3V3','2':'GND'},
    'C417': {'1':'TOUCH_3V3','2':'GND'},
    'J406': {'1':'GND','2':'TOUCH_3V3','3':'TP_RESET_N',
        '4':'TP_INT','5':'TP_SDA','6':'TP_SCL'},
}
for ref,net in [('R303','POWER_KEY_N'),('R304','KEY_PLUS_N'),('R305','KEY_MINUS_N')]:
    EXPECTED[ref]={'1':'3V3_AON','2':net}
for ref in ['C301','C302']:
    EXPECTED[ref]={'1':'3V3_AON','2':'GND'}
for ref,nets in {
    'J301':['EPD_3V3','GND','EPD_SCLK','EPD_MOSI','EPD_CS','EPD_DC','EPD_RST_N','EPD_BUSY'],
    'J302':['SD_3V3','GND','SD_CLK','SD_CMD','SD_D0','SD_D1','SD_D2','SD_D3','SD_CD_N'],
    'J303':['MIC_3V3','AMP_SYS','GND','I2S_BCLK','I2S_WS','MIC_DATA','SPEAKER_DATA','AMP_SHUTDOWN'],
}.items():
    EXPECTED[ref]={str(i+1):net for i,net in enumerate(nets)}

# TI TPS22918 DBV: VIN1/GND2/ON3/CT4/QOD5/VOUT6.
DOMAINS=[('EPD','3V3_AON','EPD_3V3','EPD_EN'),
         ('SD','3V3_AON','SD_3V3','SD_EN'),
         ('TOUCH','3V3_AON','TOUCH_3V3','TOUCH_EN'),
         ('MIC','3V3_AON','MIC_3V3','AUDIO_EN'),
         ('AMP','SYS','AMP_SYS','AUDIO_EN')]
for i,(name,vin,rail,en) in enumerate(DOMAINS):
    EXPECTED[f'U{401+i}']={'1':vin,'2':'GND','3':en,'4':name+'_CT','5':name+'_QOD','6':name+'_SW'}
    EXPECTED[f'R{401+3*i}']={'1':name+'_QOD','2':rail}
    EXPECTED[f'R{402+3*i}']={'1':name+'_SW','2':rail}
    EXPECTED[f'C{401+3*i}']={'1':vin,'2':'GND'}
    EXPECTED[f'C{402+3*i}']={'1':name+'_CT','2':'GND'}
    EXPECTED[f'C{403+3*i}']={'1':rail,'2':'GND'}
    EXPECTED[f'J{401+i}']={'1':rail,'2':'GND'}

GLOBAL={'GND','3V3_AON','SYS','VIN_5V','BENCH_5V','USB_5V_PROTECTED',
        'I2C_AON_SDA','I2C_AON_SCL','IOX_RESET_N','VBUS_SENSE_N',
        'EPD_EN','SD_EN','SD_IO_EN','TOUCH_EN','TOUCH_IO_EN','SD_CD_N',
        'TOUCH_RESET_N','TOUCH_INT','USB_DP_MCU','USB_DM_MCU','AUDIO_EN',
        'EPD_3V3','SD_3V3','TOUCH_3V3','MIC_3V3','AMP_SYS'}

def verify(netlist, erc_path):
    result=power.verify(netlist,erc_path)
    root=ET.parse(netlist).getroot()
    nets={};actual={};types={}
    for net in root.findall('./nets/net'):
        name=net.attrib['name'];nets[name]=set()
        for node in net.findall('node'):
            key=(node.attrib['ref'],node.attrib['pin'])
            actual[key]=name;types[key]=node.attrib.get('pintype','');nets[name].add(key)
    count=0
    for ref,pins in EXPECTED.items():
        for pin,want in pins.items():
            count+=1;key=(ref,pin);got=actual.get(key)
            if want is None:
                assert got and got.rsplit('/',1)[-1].startswith('unconnected-') and 'no_connect' in types[key],(key,got)
            else:
                assert got and got.rsplit('/',1)[-1]==want,(key,want,got)
                if want in GLOBAL:assert got==want,('local instead of global',key,got)
    for name in GLOBAL:
        matches=[n for n in nets if n.rsplit('/',1)[-1]==name]
        assert matches==[name],('split cross-sheet net',name,matches)
    comps={c.attrib['ref']:c for c in root.findall('./components/comp')}
    for ref in ['C501','C502']:
        assert comps[ref].find("property[@name='dnp']") is not None,ref+' must remain DNP'
    assert comps['U301'].findtext('value')=='ESP32-S3-WROOM-1-N16R8'
    for ref,value in [('R306','10k'),('R416','10k')]:
        assert comps[ref].findtext('value')==value and comps[ref].find("property[@name='dnp']") is None,ref
    for i in range(5):
        assert comps[f'C{402+3*i}'].findtext('value')=='4.7n / 50V'
        assert comps[f'R{401+3*i}'].findtext('value')=='330R / 1%'
    assert actual[('J502','1')]!=actual[('J502','2')]!=actual[('J502','3')]
    assert actual[('J502','1')]!=actual[('J502','3')], 'USB and bench sources shorted'
    assert actual[('U301','18')]!=actual[('J406','5')], 'SDA bypasses isolation switch'
    assert actual[('U301','21')]!=actual[('J406','6')], 'SCL bypasses isolation switch'
    assert actual[('U301','22')]!=actual[('J406','3')], 'RESET bypasses isolation switch'
    assert actual[('U301','39')]!=actual[('J406','4')], 'INT bypasses isolation switch'
    result['critical_pin_connections']+=count
    result['checks'] += ['N16R8 physical pads and reserved memory/strap pads',
        'USB A/B data copies and independent CC pull-downs','ESD and unidirectional TVS polarity',
        'three distinct source-selector nets','protected USB branch detection',
        'five load switches, CT and load-side QOD','four touch signals and all four SEL pins',
        'downstream touch power and pull-ups','audio enable and shutdown default pulls']
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument('netlist',type=Path);p.add_argument('--erc',type=Path,required=True)
    args=p.parse_args()
    print(json.dumps(verify(args.netlist,args.erc),indent=2))

if __name__=='__main__':main()

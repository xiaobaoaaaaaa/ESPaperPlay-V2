#!/usr/bin/env python3
"""Verify critical electrical contracts in KiCad's actual XML netlist.

Independent of the drawing generator: usable after manual schematic edits.
These assertions complement ERC; they do not model DNP assembly or hardware.
"""
import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET

EXPECTED = {
    'U101': {'1':'BAT_NTC','2':'BAT_PROT','3':'BAT_PROT','4':'CHG_CE_N',
        '5':'USB_EN2','6':'USB_EN1','7':'PGOOD_N','8':'GND','9':'CHG_N',
        '10':'SYS_RAW','11':'SYS_RAW','12':'CHG_ILIM','13':'VIN_5V',
        '14':'CHG_TMR','15':None,'16':'CHG_ISET','17':'GND'},
    'U201': {'1':'MAIN_EN','2':'REG_MODE','3':'GND','4':'REG_FB','5':'REG_PG',
        '6':'3V3_REG','7':'SW_L2','8':'GND','9':'SW_L1','10':'SYS'},
    'U202': {'1':'IOX_INT_N','2':'GND','3':'IOX_RESET_N','4':'EPD_EN',
        '5':'SD_EN','6':'TOUCH_EN','7':'PGOOD_N','8':'CHG_N','9':'SD_CD_N',
        '10':'USB_EN1','11':'CHARGE_ALLOW','12':'GND','13':'TOUCH_IO_EN',
        '14':'USB_EN2','15':'FUEL_ALERT_N','16':'SD_IO_EN','17':'IOX_SP14',
        '18':'IOX_SP15','19':'IOX_SP16','20':'IOX_SP17','21':'GND',
        '22':'I2C_AON_SCL','23':'I2C_AON_SDA','24':'3V3_AON'},
    'U203': {'1':'GND','2':'BAT_PROT','3':'BAT_PROT','4':'GND','5':'FUEL_ALERT_N',
        '6':'GND','7':'GAUGE_SCL','8':'GAUGE_SDA','9':'GND'},
    'Q101': {'1':'CHG_GATE','2':'GND','3':'CHG_CE_N'},
    'Q201': {'1':'VBUS_GATE','2':'GND','3':'VBUS_SENSE_N'},
    'R101': {'1':'SYS_RAW','2':'SYS'},
    'R102': {'1':'BAT_PACK_P','2':'BAT_PROT'},
    'R106': {'1':'SYS_RAW','2':'CHG_CE_N'},
    'R107': {'1':'CHG_GATE','2':'GND'},
    'R108': {'1':'CHARGE_ALLOW','2':'CHG_GATE'},
    'R109': {'1':'USB_EN1','2':'GND'}, 'R110': {'1':'USB_EN2','2':'GND'},
    'R201': {'1':'3V3_REG','2':'REG_FB'}, 'R202': {'1':'REG_FB','2':'GND'},
    'R203': {'1':'3V3_REG','2':'3V3_AON'},
    'C202': {'1':'3V3_REG','2':'GND'}, 'C204': {'1':'BAT_PROT','2':'GND'},
    'L201': {'1':'SW_L1','2':'SW_L2'},
    'J202': {'1':'MAIN_EN_PULL','2':'MAIN_EN','3':'GND'},
    'R217': {'1':'I2C_AON_SCL','2':'GAUGE_SCL'},
    'R218': {'1':'I2C_AON_SDA','2':'GAUGE_SDA'},
    'R220': {'1':'3V3_AON','2':'VBUS_SENSE_N'},
    'R221': {'1':'USB_5V_PROTECTED','2':'VBUS_GATE'}, 'R222': {'1':'VBUS_GATE','2':'GND'},
}

def verify(netlist, erc_path):
    tree=ET.parse(netlist).getroot()
    actual={}; types={}; net_members={}
    for net in tree.findall('./nets/net'):
        name=net.attrib['name']; members=set()
        for node in net.findall('node'):
            key=(node.attrib['ref'],node.attrib['pin'])
            assert key not in actual, f'Duplicate pin {key}'
            actual[key]=name.rsplit('/',1)[-1]; types[key]=node.attrib.get('pintype','')
            members.add(key)
        net_members[name]=members
    count=0
    for ref,pins in EXPECTED.items():
        for pin,want in pins.items():
            key=(ref,pin); count+=1
            got=actual.get(key)
            if want is None:
                assert got and got.startswith('unconnected-') and 'no_connect' in types[key], (key,got)
            else: assert got==want, f'{key}: expected {want}, got {got}'
    comps={c.attrib['ref']:c for c in tree.findall('./components/comp')}
    assert comps['R108'].find("property[@name='dnp']") is not None, 'CHG_ARM must be DNP'
    assert comps['R222'].findtext('value')=='47k', 'VBUS release resistor changed; review unplug delay'
    # r0-r2 left DLA unassigned; r3 reviewed the asymmetric manufacturer land.
    # Native pad IDs/metadata are checked by check_bom_footprints.py.
    assert comps['U201'].findtext('footprint') in (
        None, '', 'ESPaperPlay:TI_DLA0010A_VSON-HR_2x3mm_P0.5mm'
    ), 'Unreviewed TPS63802 DLA footprint'
    # A named net must not split silently across child sheets.
    for common in ['BAT_PROT','SYS','3V3_AON','USB_EN1','USB_EN2','CHARGE_ALLOW','PGOOD_N','CHG_N','VBUS_SENSE_N']:
        matches=[name for name in net_members if name.rsplit('/',1)[-1]==common]
        assert matches==[common], (common,matches)
    erc=json.loads(erc_path.read_text())
    violations=[v for sheet in erc['sheets'] for v in sheet.get('violations',[])]
    assert not violations, f'ERC has {len(violations)} violations (including exclusions)'
    return {'result':'PASS','critical_pin_connections':count,
        'components':len(comps),'nets':len(net_members),'erc_violations':len(violations),
        'checks':['stacked charger pins','feedback before measurement link',
                  'charge inhibit on chip side','DNP charge arm','cross-sheet control nets',
                  'battery-powered gauge','VBUS isolation topology']}

def main():
    p=argparse.ArgumentParser()
    p.add_argument('netlist',type=Path)
    p.add_argument('--erc',type=Path,required=True)
    args=p.parse_args()
    print(json.dumps(verify(args.netlist,args.erc),indent=2))

if __name__=='__main__': main()

#!/usr/bin/env python3
"""Check the exported r2 netlist against reviewed physical-pin contracts.

The contract is retained as review data, separately from the authoring scripts.
This verifies connections and assembly properties, not timing or analog behavior.
"""
import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import check_platform_netlist as platform

def main():
    p=argparse.ArgumentParser()
    p.add_argument('netlist',type=Path)
    p.add_argument('--erc',type=Path,required=True)
    p.add_argument('--contract',type=Path,default=Path(__file__).with_name('peripheral-pin-contract.json'))
    args=p.parse_args()
    result=platform.verify(args.netlist,args.erc)
    contract=json.loads(args.contract.read_text())
    root=ET.parse(args.netlist).getroot()
    actual={};types={};nets={}
    for net in root.findall('./nets/net'):
        name=net.attrib['name'];nets[name]=set()
        for node in net.findall('node'):
            key=(node.attrib['ref'],node.attrib['pin'])
            actual[key]=name;types[key]=node.attrib.get('pintype','');nets[name].add(key)
    count=0
    for ref,pins in contract['connections'].items():
        for pin,want in pins.items():
            count+=1;key=(ref,pin);got=actual.get(key)
            if want is None:
                assert got and got.rsplit('/',1)[-1].startswith('unconnected-') and 'no_connect' in types[key],(key,got)
            else:assert got and got.rsplit('/',1)[-1]==want,(key,want,got)
    for name in contract['global_nets']:
        matches=[n for n in nets if n.rsplit('/',1)[-1]==name]
        assert matches==[name],('split cross-sheet net',name,matches)
    comps={c.attrib['ref']:c for c in root.findall('./components/comp')}
    for ref,value in contract.get('values',{}).items():
        assert comps[ref].findtext('value')==value,(ref,value,comps[ref].findtext('value'))
    for ref in contract.get('dnp',[]):
        assert comps[ref].find("property[@name='dnp']") is not None,(ref,'must be DNP')
    for ref in contract.get('footprint_tbd',[]):
        assert comps[ref].findtext('footprint') in (None,''),(ref,'requires separately reviewed footprint')
    for left,right in contract['distinct_pins']:
        a=tuple(left);b=tuple(right)
        assert actual[a]!=actual[b],('unexpected isolation bypass / rail short',a,b,actual[a])
    assert actual[('U202','16')]=='SD_IO_EN'
    assert actual[('R223','1')]=='SD_IO_EN' and actual[('R223','2')]=='GND'
    assert comps['R223'].findtext('value')=='10k' and comps['R223'].find("property[@name='dnp']") is None
    assert comps['R215'].findtext('value')=='10k' and comps['R215'].find("property[@name='dnp']") is None
    result['critical_pin_connections']+=count+2  # P13 already checked by inherited power contract.
    result['checks']+=contract['checks']+['SD I/O independent of supply enable, with retained R223 pull-down']
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
